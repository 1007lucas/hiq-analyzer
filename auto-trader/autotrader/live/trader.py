"""실전/페이퍼 매매 루프 (LiveTrader).

TradingCore 에 '실제 시계'와 '실제 시세'를 연결하는 드라이버입니다.
판단은 전부 코어가 하고, 여기서는 언제 무엇을 코어에 알려 줄지만 결정합니다.

하루 일정 (정규장 09:00~15:30 기준, 특수 개장일은 달력에 따라 이동)
  08:40        준비: 일봉 수집 → core.start_day (오늘의 계획 수립)
  09:00+지연   개장 확인(실제로 거래가 일어나는지) → core.on_open
  장중         poll_interval 마다 감시 종목 시세 → core.on_price
  15:15        core.on_close (종가 청산)
  15:35        core.end_day (평가금 기록, 일일 요약 알림)

안전 원칙
* 달력만 믿지 않습니다. 거래량이 실제로 변하는지 확인한 뒤에만 장이 열렸다고 판단합니다
  (임시 공휴일, 개장 지연일에 엉뚱한 주문을 내지 않기 위해).
* 시세 조회 실패, 브로커 오류는 그 종목/그 순간만 건너뛰고 루프는 계속됩니다.
* 재시작해도 코어가 당일 진행 상황을 기억하므로 같은 주문을 두 번 내지 않습니다.
"""

from __future__ import annotations

import logging
import time as _time
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Protocol

from ..brokers.base import Broker, BrokerError, MarketData
from ..config import ScheduleConfig, parse_hhmm
from ..control import BotLock, pop_commands, set_stop
from ..core import TradingCore
from ..market_calendar import REGULAR_CLOSE, REGULAR_OPEN, MarketCalendar, Session
from ..models import Bar, Quote, now_kst
from ..strategies.base import EntryKind, ExitKind

log = logging.getLogger("autotrader.live")

MODE_LABELS = {
    "paper": "페이퍼(가상 매매)",
    "kis-mock": "한국투자증권 모의투자",
    "kis-live": "한국투자증권 실전투자",
}


class Clock(Protocol):
    def now(self) -> datetime: ...
    def sleep(self, seconds: float) -> None: ...


class RealClock:
    def now(self) -> datetime:
        return now_kst()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            _time.sleep(seconds)


class StopRequested(Exception):
    """외부에서 루프 종료를 요청함."""


def _minutes_between(a: time, b: time) -> timedelta:
    return timedelta(hours=b.hour - a.hour, minutes=b.minute - a.minute, seconds=b.second - a.second)


class LiveTrader:
    PREP_LEAD = timedelta(minutes=20)            # 개장 몇 분 전에 준비를 시작할지
    END_DELAY = timedelta(minutes=5)             # 폐장 몇 분 뒤에 마감 처리할지
    END_GRACE = timedelta(minutes=60)            # 폐장 후 이 시간 안에 켜면 그날 마감 처리는 수행
    CLOSE_AUCTION = timedelta(minutes=10)        # 폐장 전 종가 단일가 시간 (이때는 즉시 체결이 안 됨)
    NOT_LIVE_ALERT_AFTER = timedelta(minutes=10) # 개장 시각이 이만큼 지나도 거래가 없으면 알림
    SLEEP_CHUNK = 20.0                           # 긴 대기 중에도 이 간격으로 깨어나 명령/정지 요청 확인
    QUOTE_FAIL_ALERT_POLLS = 30                  # 시세 조회가 연속으로 이만큼 실패하면 알림
    ERROR_ALERT_INTERVAL = timedelta(minutes=10)
    HISTORY_RETRIES = 3

    def __init__(
        self,
        *,
        core: TradingCore,
        market: MarketData,
        broker: Broker,
        calendar: MarketCalendar,
        schedule: ScheduleConfig,
        mode: str,
        data_dir: Path,
        clock: Clock | None = None,
        notify: Callable[[str], None] | None = None,
        kill_switch: Callable[[], bool] | None = None,
        lock: BotLock | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> None:
        self.core = core
        self.market = market
        self.broker = broker
        self.calendar = calendar
        self.schedule = schedule
        self.mode = mode
        self.data_dir = Path(data_dir)
        self.clock: Clock = clock or RealClock()
        self._notify_fn = notify
        self._kill_switch = kill_switch
        self.lock = lock
        self._stop_requested = stop_requested

        # 설정의 시각은 평소(09:00~15:30) 기준 → 개장/폐장 시각과의 간격으로 바꿔 특수 개장일에도 적용
        self._deadline_offset = _minutes_between(REGULAR_OPEN, parse_hhmm(schedule.open_entry_deadline))
        self._close_offset = _minutes_between(parse_hhmm(schedule.close_exit_time), REGULAR_CLOSE)

        self._trading_day_cache: dict[date, bool] = {}
        self._vol_seen: dict[str, float] = {}
        self._live_day: date | None = None           # 실제 거래가 확인된 날짜
        self._live_since: datetime | None = None
        self._saw_not_live = False
        self._not_live_alerted = False
        self._quote_fail_polls = 0
        self._last_error_alert: datetime | None = None
        self._account_warned: set[tuple[date, str]] = set()

    # ------------------------------------------------------------------ #
    # 메인 루프
    # ------------------------------------------------------------------ #
    def run(self, max_days: int | None = None) -> None:
        """매매 루프. Ctrl+C(KeyboardInterrupt) 또는 stop_requested 가 True 가 될 때까지 계속됩니다.

        max_days : 이만큼의 거래일을 처리하면 반환 (테스트/1회 실행용). None = 무한.
        """
        self._startup()
        done = 0
        try:
            while True:
                self._housekeeping()
                now = self.clock.now()
                today = now.date()
                sess = self._session(today)
                if sess is not None and not self._day_done(today) and now < sess.close + self.END_GRACE:
                    try:
                        self._run_day(sess)
                    except StopRequested:
                        raise
                    except Exception as e:  # noqa: BLE001 - 예상 못 한 오류에도 봇은 살아 있어야 함
                        log.exception("매매 루프 오류")
                        self._error_alert(f"⚠️ 매매 루프에서 오류가 발생했습니다: {e}. 1분 뒤 이어서 진행합니다.")
                        self._sleep(60.0)
                        continue
                    done += 1
                    if max_days is not None and done >= max_days:
                        return
                    continue
                nxt = self._next_session(today)
                wake = nxt.open - self.PREP_LEAD
                self._info(f"다음 거래일은 {nxt.day:%Y-%m-%d} 입니다. {wake:%m월 %d일 %H:%M} 까지 대기합니다.")
                self._sleep_until(wake)
        except StopRequested:
            self._info("종료 요청을 받아 매매 루프를 멈춥니다.")

    def _startup(self) -> None:
        core = self.core
        self._info(
            f"자동매매 시작 — 모드: {MODE_LABELS.get(self.mode, self.mode)}, 전략: {core.strategy.name} "
            f"{dict(core.strategy.params)}, 종목 {len(core.universe)}개, 운용자금 {core.capital_base:,.0f}원"
        )
        core.recover_pending()
        self._notify(
            f"🤖 자동매매 봇 시작 ({MODE_LABELS.get(self.mode, self.mode)})\n"
            f"전략 {core.strategy.name} · 종목 {len(core.universe)}개 · 봇 평가금 {core.equity():,.0f}원"
        )

    # ------------------------------------------------------------------ #
    # 하루
    # ------------------------------------------------------------------ #
    def _run_day(self, sess: Session) -> None:
        core = self.core
        day = sess.day
        resumed = core.day is not None and core.day.day == day

        # 1) 준비
        self._sleep_until(sess.open - self.PREP_LEAD)
        core.start_day(day, self._load_histories(day))
        self._check_account(day)
        if not resumed:
            self._announce_plan(sess)
        self._vol_seen = {}
        self._live_since = None
        self._saw_not_live = False
        self._not_live_alerted = False
        self._quote_fail_polls = 0

        # 2) 개장 대기
        self._sleep_until(sess.open + timedelta(seconds=self.schedule.entry_delay_sec))

        # 3) 장중
        close_exit_at = sess.close - self._close_offset
        entry_deadline = sess.open + self._deadline_offset
        while True:
            remaining = (close_exit_at - self.clock.now()).total_seconds()
            if remaining <= 0:
                break
            self._housekeeping()
            if not self._killed():
                d = core.day
                if d is not None and not d.opened:
                    self._try_open(sess, entry_deadline)
                else:
                    self._poll_once()
            remaining = (close_exit_at - self.clock.now()).total_seconds()
            if remaining <= 0:
                break
            self._sleep(min(self.schedule.poll_interval_sec, remaining))

        # 4) 종가 청산 (단일가 시간 전까지 팔리지 않은 종목은 재시도)
        d = core.day
        if d is not None and d.opened and not self._killed():
            auction_at = sess.close - self.CLOSE_AUCTION
            self._close_exits()
            while core.has_pending_close_exits() and self.clock.now() < auction_at:
                self._sleep(self.schedule.poll_interval_sec)
                if self._killed():
                    break
                self._close_exits()
            if core.has_pending_close_exits():
                self._alert("⚠️ 종가 청산 대상 중 팔리지 않은 종목이 있습니다. 내일 다시 시도합니다.")

        # 5) 마감
        self._sleep_until(sess.close + self.END_DELAY)
        closes: dict[str, float] = {}
        highs: dict[str, float] = {}
        if self._live_day == day:
            for sym, q in self._quotes(self._tracked()).items():
                if q.price > 0 and q.open > 0:
                    closes[sym] = q.price
                    highs[sym] = max(q.high, q.price)
        core.end_day(closes, highs)
        self._daily_summary(sess)

    def _try_open(self, sess: Session, entry_deadline: datetime) -> None:
        """실제로 장이 열렸는지 확인하고, 열렸으면 코어의 개장 처리를 실행합니다."""
        core = self.core
        now = self.clock.now()
        quotes = self._quotes(self._tracked())
        if not self._market_live(sess.day, quotes):
            self._saw_not_live = True
            if not self._not_live_alerted and now >= sess.open + self.NOT_LIVE_ALERT_AFTER:
                self._not_live_alerted = True
                self._alert(
                    "⏳ 개장 시각이 지났지만 거래가 확인되지 않습니다 (휴장일이거나 개장이 늦어지는 날일 수 있습니다). "
                    "거래가 시작되면 자동으로 진행합니다."
                )
            return
        if self._live_since is None:
            self._live_since = now

        # 봇이 장 시작을 직접 지켜본 경우(개장 지연일)에는 '실제 개장 시점' 기준으로 시가 매수 허용 여부를 판단
        if self._saw_not_live:
            allow_entries = (now - self._live_since) <= self._deadline_offset
        else:
            allow_entries = now <= entry_deadline

        prices: dict[str, float] = {}
        opens: dict[str, float] = {}
        for sym, q in quotes.items():
            if q.price > 0 and q.open > 0 and not q.halted:
                prices[sym] = q.price
                opens[sym] = q.open
        if not prices:
            return
        if not allow_entries:
            self._info("봇이 개장 후 늦게 시작되어 오늘의 '시가 매수'는 건너뜁니다 (청산과 돌파 감시는 수행).")
        core.on_open(prices, opens, allow_entries=allow_entries)

        d = core.day
        if d is not None and d.opened and not allow_entries:
            # 늦게 켠 경우: 이미 돌파가 지나간 종목을 뒤늦게 사지 않도록 오늘은 포기
            for sym, q in quotes.items():
                lv = core.watch_levels(sym)
                if lv.breakout > 0 and q.high >= lv.breakout:
                    core.skip_entry_today(sym, f"봇 시작 전에 이미 목표가({lv.breakout:,.0f}원)를 돌파함")

    def _poll_once(self) -> None:
        core = self.core
        symbols = core.watched_symbols()
        if not symbols:
            return
        ok = 0
        for sym in symbols:
            try:
                q = self.market.get_quote(sym)
            except BrokerError as e:
                log.debug("시세 조회 실패 (%s): %s", sym, e)
                continue
            ok += 1
            if q.halted or q.price <= 0 or q.open <= 0:
                continue        # 거래정지 또는 오늘 아직 거래 없음
            core.on_price(sym, q.price, q.open)
        if ok == 0:
            self._quote_fail_polls += 1
            if self._quote_fail_polls == self.QUOTE_FAIL_ALERT_POLLS:
                self._alert(
                    "🚨 시세 조회가 계속 실패하고 있습니다. 이 상태에서는 손절 등 장중 판단을 할 수 없습니다. "
                    "네트워크와 API 상태를 확인해 주세요."
                )
        else:
            if self._quote_fail_polls >= self.QUOTE_FAIL_ALERT_POLLS:
                self._alert("✅ 시세 조회가 다시 정상화되었습니다.")
            self._quote_fail_polls = 0

    def _close_exits(self) -> None:
        core = self.core
        prices: dict[str, float] = {}
        for sym, q in self._quotes(list(core.positions)).items():
            if q.price > 0 and q.open > 0 and not q.halted:
                prices[sym] = q.price
        core.on_close(prices)

    # ------------------------------------------------------------------ #
    # 장 상태 판단
    # ------------------------------------------------------------------ #
    def _session(self, day: date) -> Session | None:
        """그날 정규장이 열리면 Session, 아니면 None. 오늘에 한해 증권사 휴장일 API 를 우선합니다."""
        if day.weekday() >= 5:
            return None
        open_ = self._trading_day_cache.get(day)
        if open_ is None:
            api: bool | None = None
            if day == self.clock.now().date():
                try:
                    api = self.market.is_trading_day(day)
                except Exception as e:  # noqa: BLE001 - 휴장일 조회 실패 시 내장 달력으로 판단
                    log.warning("휴장일 조회 실패, 내장 달력으로 판단합니다: %s", e)
                    api = None
            open_ = self.calendar.is_trading_day(day) if api is None else bool(api)
            if day == self.clock.now().date():
                self._trading_day_cache = {day: open_}
        return self.calendar.session_assuming_open(day) if open_ else None

    def _next_session(self, after: date) -> Session:
        d = self.calendar.next_trading_day(after)
        return self.calendar.session_assuming_open(d)

    def _day_done(self, day: date) -> bool:
        d = self.core.day
        return d is not None and d.day == day and d.ended

    def _market_live(self, day: date, quotes: dict[str, Quote]) -> bool:
        """오늘 실제로 거래가 일어나고 있는지.

        (1) 오늘 날짜의 일봉이 생겼거나 (2) 누적 거래량이 직전 확인 때와 달라졌으면 '열림'.
        휴장일에는 시세 API 가 전 거래일 값을 그대로 돌려주므로 둘 다 성립하지 않습니다.
        """
        if self._live_day == day:
            return True
        candidates = [q for q in quotes.values() if q.price > 0 and q.open > 0 and q.volume > 0 and not q.halted]
        if not candidates:
            return False
        live = False
        for q in candidates:
            prev = self._vol_seen.get(q.symbol)
            if prev is not None and q.volume != prev:
                live = True
            self._vol_seen[q.symbol] = q.volume
        if not live:
            sym = candidates[0].symbol
            try:
                bars = self.market.get_daily_bars(sym, day, day)
            except BrokerError as e:
                log.debug("개장 확인용 일봉 조회 실패 (%s): %s", sym, e)
                bars = []
            live = any(b.date == day and b.volume > 0 for b in bars)
        if live:
            self._live_day = day
        return live

    # ------------------------------------------------------------------ #
    # 데이터 수집
    # ------------------------------------------------------------------ #
    def _tracked(self) -> list[str]:
        core = self.core
        return list(core.universe) + [s for s in core.positions if s not in core.universe]

    def _load_histories(self, day: date) -> dict[str, list[Bar]]:
        need = self.core.strategy.warmup + 10
        start = day - timedelta(days=int(need * 1.6) + 30)
        end = day - timedelta(days=1)
        out: dict[str, list[Bar]] = {}
        failed: list[str] = []
        for sym in self._tracked():
            bars: list[Bar] | None = None
            for attempt in range(self.HISTORY_RETRIES):
                try:
                    bars = self.market.get_daily_bars(sym, start, end)
                    break
                except BrokerError as e:
                    log.warning("일봉 조회 실패 (%s, %d/%d): %s", sym, attempt + 1, self.HISTORY_RETRIES, e)
                    self._sleep(2.0 * (attempt + 1))
            if bars is None:
                failed.append(sym)
                continue
            out[sym] = [b for b in bars if b.date < day]
        if failed:
            self._alert(
                f"⚠️ 일봉 데이터를 받지 못한 종목이 있어 오늘은 해당 종목을 새로 매수하지 않습니다: {', '.join(failed)}"
            )
        return out

    def _quotes(self, symbols: list[str]) -> dict[str, Quote]:
        out: dict[str, Quote] = {}
        for sym in symbols:
            try:
                out[sym] = self.market.get_quote(sym)
            except BrokerError as e:
                log.debug("시세 조회 실패 (%s): %s", sym, e)
        return out

    def _check_account(self, day: date) -> None:
        """증권사 계좌의 실제 보유 수량이 봇 장부보다 적으면 알립니다 (자동으로 고치지는 않습니다)."""
        core = self.core
        if not core.positions:
            return
        try:
            acct = self.broker.get_account()
        except Exception as e:  # noqa: BLE001 - 계좌 조회 실패는 경고만
            log.warning("계좌 조회 실패: %s", e)
            return
        if acct is None:
            return
        for sym, pos in core.positions.items():
            bp = acct.positions.get(sym)
            have = bp.qty if bp is not None else 0
            if have < pos.qty and (day, sym) not in self._account_warned:
                self._account_warned.add((day, sym))
                self._alert(
                    f"⚠️ {core.name_of(sym)}: 계좌 보유 수량({have}주)이 봇 장부({pos.qty}주)보다 적습니다. "
                    f"직접 매도하셨다면 'forget {sym}' 명령으로 봇 장부를 정리해 주세요."
                )

    # ------------------------------------------------------------------ #
    # 명령 / 정지
    # ------------------------------------------------------------------ #
    def _killed(self) -> bool:
        if self._kill_switch is None:
            return False
        try:
            return bool(self._kill_switch())
        except Exception:  # noqa: BLE001 - 확인 실패 시 안전하게 '정지'
            return True

    def _housekeeping(self) -> None:
        if self.lock is not None:
            self.lock.heartbeat()
        if self._stop_requested is not None and self._stop_requested():
            raise StopRequested()
        for cmd in pop_commands(self.data_dir, self.mode):
            try:
                self._handle_command(cmd["cmd"], cmd["args"])
            except Exception as e:  # noqa: BLE001 - 잘못된 명령 하나가 봇을 죽이지 않도록
                log.exception("명령 처리 오류")
                self._alert(f"⚠️ 명령({cmd['cmd']}) 처리 중 오류: {e}")

    def _handle_command(self, cmd: str, args: dict) -> None:
        core = self.core
        if cmd == "resume":
            core.resume()
            self._alert("▶️ 사용자 요청으로 신규 매수 중단을 해제했습니다.")
        elif cmd == "forget":
            sym = str(args.get("symbol", "")).upper()
            qty = args.get("qty")
            price = args.get("price")
            ok = core.forget_position(
                sym,
                qty=int(qty) if qty is not None else None,
                price=float(price) if price is not None else None,
                reason="사용자 요청으로 장부 정리",
            )
            if not ok:
                self._alert(f"⚠️ 장부 정리 실패: 봇 장부에 {sym} 포지션이 없거나 가격을 알 수 없습니다.")
        elif cmd == "liquidate":
            d = core.day
            if not core.positions:
                self._alert("ℹ️ 청산 요청: 봇이 보유한 종목이 없습니다.")
            elif d is None or not d.opened or d.ended or self._live_day != d.day:
                self._alert("⚠️ 청산 요청은 장중에만 처리할 수 있습니다. 요청을 취소합니다.")
                return
            else:
                prices = {s: q.price for s, q in self._quotes(list(core.positions)).items() if q.price > 0 and q.open > 0}
                n = core.liquidate_all("사용자 청산 요청", prices)
                self._alert(f"🧹 사용자 요청으로 {n}개 종목의 청산 주문을 냈습니다.")
            set_stop(self.data_dir, True)
            self._alert("⏸ 청산 요청 처리 후 긴급 정지 상태로 전환했습니다. 다시 매매하려면 'resume' 명령을 실행하세요.")

    # ------------------------------------------------------------------ #
    # 대기
    # ------------------------------------------------------------------ #
    def _sleep(self, seconds: float) -> None:
        remaining = float(seconds)
        while remaining > 0:
            chunk = min(self.SLEEP_CHUNK, remaining)
            self.clock.sleep(chunk)
            remaining -= chunk
            self._housekeeping()

    def _sleep_until(self, when: datetime) -> None:
        while True:
            remaining = (when - self.clock.now()).total_seconds()
            if remaining <= 0:
                return
            self._sleep(min(remaining, self.SLEEP_CHUNK))

    # ------------------------------------------------------------------ #
    # 알림 / 기록
    # ------------------------------------------------------------------ #
    def _announce_plan(self, sess: Session) -> None:
        core = self.core
        d = core.day
        if d is None:
            return
        buys_open, buys_break, sells_open, sells_close, notes = [], [], [], [], []
        for sym, sd in d.symbols.items():
            name = core.name_of(sym)
            held = sym in core.positions
            entry, exit_ = sd.plan.entry, sd.plan.exit
            if exit_ is not None and held:
                (sells_open if exit_.kind == ExitKind.OPEN else sells_close).append(name)
            if entry is not None and (not held or (exit_ is not None and exit_.kind == ExitKind.OPEN)):
                if not sd.cooldown and not sd.entry_blocked:
                    (buys_open if entry.kind == EntryKind.OPEN else buys_break).append(name)
            if sd.note:
                notes.append(f"{name}: {sd.note}")
        lines = [f"📋 {sess.day:%m/%d} 오늘의 계획 (개장 {sess.open:%H:%M})"]
        if sells_open:
            lines.append("시가 매도: " + ", ".join(sells_open))
        if sells_close:
            lines.append("종가 매도: " + ", ".join(sells_close))
        if buys_open:
            lines.append("시가 매수 후보: " + ", ".join(buys_open))
        if buys_break:
            lines.append("돌파 매수 대기: " + ", ".join(buys_break))
        if len(lines) == 1:
            lines.append("예정된 매매 없음 (보유 종목 손절·익절 감시만 수행)")
        if core.halted:
            lines.append("※ 최대 낙폭 한도 초과로 신규 매수 중단 상태입니다 ('resume' 으로 해제)")
        if self._killed():
            lines.append("※ 긴급 정지(STOP) 상태입니다 — 주문을 내지 않습니다")
        for n in notes:
            lines.append("· " + n)
        self._alert("\n".join(lines))

    def _daily_summary(self, sess: Session) -> None:
        core = self.core
        snap = core.snapshot()
        today = sess.day.isoformat()
        trades = [o for o in core.store.orders(limit=200) if o.get("day") == today and (o.get("filled_qty") or 0) > 0]
        realized = sum(float(o.get("pnl") or 0.0) for o in trades if o.get("side") == "sell")
        lines = [
            f"📊 {sess.day:%m/%d} 마감 요약",
            f"봇 평가금 {snap['equity']:,.0f}원 (오늘 {snap['day_return']:+.2%}, 누적 {snap['total_return']:+.2%})",
            f"현금 {snap['cash']:,.0f}원 · 오늘 체결 {len(trades)}건 · 실현손익 {realized:+,.0f}원",
        ]
        if snap["positions"]:
            lines.append("보유: " + ", ".join(f"{p['name']} {p['qty']}주({p['pnl_pct']:+.1%})" for p in snap["positions"]))
        else:
            lines.append("보유 종목 없음")
        if self._live_day != sess.day:
            lines.append("※ 오늘은 거래가 확인되지 않았습니다 (휴장으로 판단)")
        self._alert("\n".join(lines))

    def _info(self, msg: str) -> None:
        log.info(msg)
        self.core.store.log_event("info", msg, self.clock.now())

    def _notify(self, msg: str) -> None:
        if self._notify_fn is None:
            return
        try:
            self._notify_fn(msg)
        except Exception:  # noqa: BLE001 - 알림 실패가 매매를 막으면 안 됨
            log.exception("알림 전송 실패")

    def _alert(self, msg: str) -> None:
        log.info(msg)
        self.core.store.log_event("alert", msg, self.clock.now())
        self._notify(msg)

    def _error_alert(self, msg: str) -> None:
        now = self.clock.now()
        if self._last_error_alert is None or now - self._last_error_alert >= self.ERROR_ALERT_INTERVAL:
            self._last_error_alert = now
            self._alert(msg)
        else:
            log.warning(msg)

"""LiveTrader 테스트 — 가짜 시계와 가짜 시세로 하루를 통째로 돌려 봅니다."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from autotrader.brokers.base import BrokerError, MarketData
from autotrader.brokers.paper import PaperBroker
from autotrader.config import CostConfig, RiskConfig, ScheduleConfig
from autotrader.control import enqueue_command
from autotrader.core import TradingCore
from autotrader.live import LiveTrader
from autotrader.market_calendar import MarketCalendar
from autotrader.models import KST, AccountSnapshot, Bar, BrokerPosition, Quote
from autotrader.state import MemoryStore, SqliteStore
from autotrader.strategies.base import DayPlan, EntryKind, EntryRule, ExitKind, ExitRule

from conftest import ScriptedStrategy

MON = date(2024, 3, 4)
TUE = date(2024, 3, 5)
NO_COST = CostConfig(commission_rate=0.0, sell_tax_rate=0.0, slippage_rate=0.0)
BUY_OPEN = DayPlan(entry=EntryRule(EntryKind.OPEN, note="t"))


def at(day: date, hh: int, mm: int, ss: int = 0) -> datetime:
    return datetime.combine(day, time(hh, mm, ss), tzinfo=KST)


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.t = start
        self.slept = 0.0

    def now(self) -> datetime:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += timedelta(seconds=seconds)
        self.slept += seconds


class FakeMarket(MarketData):
    """paths[day][symbol] = [(HH:MM, price), ...] 로 장중 가격 경로를 흉내 냅니다.

    * 그날 경로가 없으면 = 휴장 (전 거래일 값만 돌려줌, 거래량 변화 없음)
    * 첫 경로 시각 이전 = 아직 거래 없음 (open 0)
    """

    def __init__(self, clock: FakeClock, history: dict[str, list[Bar]], paths: dict[date, dict[str, list[tuple[str, float]]]]):
        self.clock = clock
        self.history = history
        self.paths = paths
        self.fail: set[str] = set()
        self.fail_all = False
        self.trading_day_answer: bool | None = None
        self.daily_includes_today = True
        self.quote_calls = 0

    def _points(self, symbol: str, now: datetime) -> list[tuple[datetime, float]]:
        pts = self.paths.get(now.date(), {}).get(symbol, [])
        out = []
        for hhmm, price in pts:
            hh, mm = map(int, hhmm.split(":"))
            t = at(now.date(), hh, mm)
            if t <= now:
                out.append((t, price))
        return out

    def get_quote(self, symbol: str) -> Quote:
        self.quote_calls += 1
        if self.fail_all or symbol in self.fail:
            raise BrokerError("boom")
        now = self.clock.now()
        prev_close = self.history[symbol][-1].close
        pts = self._points(symbol, now)
        if not pts:
            last = self.history[symbol][-1]
            if now.date() in self.paths and symbol in self.paths[now.date()]:
                return Quote(symbol, prev_close, 0, 0, 0, prev_close, 0.0, time=now)     # 개장 전
            # 휴장일: 전 거래일 값 그대로
            return Quote(symbol, last.close, last.open, last.high, last.low, prev_close, 12345.0, time=now)
        prices = [p for _, p in pts]
        vol = 1000.0 + (now - pts[0][0]).total_seconds()
        return Quote(symbol, prices[-1], prices[0], max(prices), min(prices), prev_close, vol, time=now)

    def get_daily_bars(self, symbol: str, start: date, end: date) -> list[Bar]:
        if self.fail_all or symbol in self.fail:
            raise BrokerError("boom")
        bars = [b for b in self.history[symbol] if start <= b.date <= end]
        now = self.clock.now()
        if self.daily_includes_today and start <= now.date() <= end:
            pts = self._points(symbol, now)
            if pts:
                prices = [p for _, p in pts]
                bars.append(Bar(now.date(), prices[0], max(prices), min(prices), prices[-1], 500.0))
        return bars

    def is_trading_day(self, day: date) -> bool | None:
        return self.trading_day_answer


def flat_history(price: float = 10_000.0, last: date = date(2024, 3, 1), n: int = 5) -> list[Bar]:
    days = [last - timedelta(days=i) for i in range(n)][::-1]
    return [Bar(d, price, price, price, price, 1000.0) for d in days]


class Rig:
    def __init__(self, tmp_path, start: datetime, paths, *, strategy=None, universe=("A",), risk=None,
                 store=None, schedule=None, calendar=None, history=None, broker=None):
        self.tmp = tmp_path
        self.clock = FakeClock(start)
        self.history = history or {s: flat_history() for s in universe}
        self.market = FakeMarket(self.clock, self.history, paths)
        self.alerts: list[str] = []
        self.killed = False
        self.broker = broker or PaperBroker()
        self.store = store or MemoryStore()
        self.core = TradingCore(
            strategy=strategy or ScriptedStrategy(default=BUY_OPEN),
            universe=universe,
            risk=risk or RiskConfig(capital=10_000_000, max_positions=3, position_pct=0.3, cash_reserve_pct=0.0,
                                    stop_loss_pct=0.05, daily_loss_limit_pct=0.0),
            costs=NO_COST,
            broker=self.broker,
            store=self.store,
            clock=self.clock.now,
            notify=self.alerts.append,
            kill_switch=lambda: self.killed,
        )
        self.trader = LiveTrader(
            core=self.core,
            market=self.market,
            broker=self.broker,
            calendar=calendar or MarketCalendar(variable_holidays={}, special_sessions={}),
            schedule=schedule or ScheduleConfig(entry_delay_sec=30, poll_interval_sec=10),
            mode="paper",
            data_dir=tmp_path,
            clock=self.clock,
            notify=self.alerts.append,
            kill_switch=lambda: self.killed,
        )

    def orders(self):
        return [o for o in self.store.orders() if (o["filled_qty"] or 0) > 0]


# --------------------------------------------------------------------------- #
def test_full_day_open_entry_stop_loss_and_summary(tmp_path):
    paths = {MON: {"A": [("09:00", 10_000), ("10:00", 10_200), ("11:00", 9_400), ("15:30", 9_600)]}}
    rig = Rig(tmp_path, at(MON, 8, 0), paths)
    rig.trader.run(max_days=1)

    buys = [o for o in rig.orders() if o["side"] == "buy"]
    sells = [o for o in rig.orders() if o["side"] == "sell"]
    assert len(buys) == 1 and buys[0]["price"] == 10_000 and buys[0]["ts"].startswith("2024-03-04T09:00:30")
    assert len(sells) == 1 and sells[0]["price"] == 9_400 and "손절" in sells[0]["reason"]
    assert sells[0]["ts"] >= "2024-03-04T11:00:00"
    assert rig.core.day.ended and rig.clock.now() >= at(MON, 15, 35)
    eq = rig.store.equity_history()
    assert eq[-1][0] == MON and eq[-1][1] == pytest.approx(10_000_000 - 300 * 600)
    assert any("마감 요약" in a for a in rig.alerts)
    assert any("오늘의 계획" in a and "시가 매수 후보" in a for a in rig.alerts)


def test_breakout_entry_and_close_exit_before_auction(tmp_path):
    plan = DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=300), exit=ExitRule(ExitKind.CLOSE))
    paths = {MON: {"A": [("09:00", 10_000), ("10:30", 10_310), ("14:00", 10_500), ("15:20", 10_700)]}}
    rig = Rig(tmp_path, at(MON, 8, 50), paths, strategy=ScriptedStrategy(default=plan))
    rig.trader.run(max_days=1)
    buy, sell = rig.orders()
    assert buy["side"] == "buy" and buy["price"] == 10_310 and buy["ts"].startswith("2024-03-04T10:30")
    assert sell["side"] == "sell" and sell["price"] == 10_500 and sell["ts"].startswith("2024-03-04T15:15")
    assert rig.core.positions == {}


def test_weekend_and_calendar_holiday_are_skipped(tmp_path):
    sat = date(2024, 3, 2)
    cal = MarketCalendar(variable_holidays={2024: [MON]}, special_sessions={})
    paths = {TUE: {"A": [("09:00", 10_000), ("15:30", 10_100)]}}
    rig = Rig(tmp_path, at(sat, 12, 0), paths, calendar=cal)
    rig.trader.run(max_days=1)
    assert [o["day"] for o in rig.orders()] == [TUE.isoformat()]
    assert [d for d, _, _ in rig.store.equity_history()] == [TUE]


def test_broker_holiday_api_overrides_calendar(tmp_path):
    paths = {MON: {"A": [("09:00", 10_000), ("15:30", 10_000)]},
             TUE: {"A": [("09:00", 10_000), ("15:30", 10_000)]}}
    rig = Rig(tmp_path, at(MON, 8, 0), paths)
    rig.market.trading_day_answer = False            # 증권사 API: 오늘은 휴장
    stop_at = at(MON, 16, 0)
    rig.trader._stop_requested = lambda: rig.clock.now() >= stop_at
    rig.trader.run()
    assert rig.orders() == [] and rig.core.day is None


def test_unlisted_holiday_no_trades_because_market_never_goes_live(tmp_path):
    rig = Rig(tmp_path, at(MON, 8, 0), paths={})       # 달력은 개장일이라는데 실제로는 거래가 없는 날
    rig.trader.run(max_days=1)
    assert rig.orders() == []
    assert not rig.core.day.opened and rig.core.day.ended
    assert any("거래가 확인되지 않습니다" in a for a in rig.alerts)
    assert any("휴장으로 판단" in a for a in rig.alerts)


def test_delayed_open_is_detected_and_open_entries_still_happen(tmp_path):
    paths = {MON: {"A": [("10:00", 10_000), ("15:30", 10_100)]}}     # 수능일처럼 10시 개장인데 달력에는 없음
    rig = Rig(tmp_path, at(MON, 8, 0), paths)
    rig.trader.run(max_days=1)
    (buy,) = rig.orders()
    assert buy["ts"].startswith("2024-03-04T10:00") and buy["price"] == 10_000


def test_special_session_from_calendar_shifts_schedule(tmp_path):
    cal = MarketCalendar(variable_holidays={}, special_sessions={MON: (time(10, 0), time(16, 30))})
    plan = DayPlan(entry=EntryRule(EntryKind.OPEN), exit=ExitRule(ExitKind.CLOSE))
    paths = {MON: {"A": [("10:00", 10_000), ("16:00", 10_300), ("16:30", 10_400)]}}
    rig = Rig(tmp_path, at(MON, 8, 0), paths, calendar=cal, strategy=ScriptedStrategy(default=plan))
    rig.trader.run(max_days=1)
    buy, sell = rig.orders()
    assert buy["ts"].startswith("2024-03-04T10:00:30")
    assert sell["ts"].startswith("2024-03-04T16:15") and sell["price"] == 10_300
    assert rig.clock.now() >= at(MON, 16, 35)


def test_live_detection_works_without_todays_daily_bar(tmp_path):
    paths = {MON: {"A": [("09:00", 10_000), ("15:30", 10_000)]}}
    rig = Rig(tmp_path, at(MON, 8, 0), paths)
    rig.market.daily_includes_today = False          # 일봉 API 가 장중에 오늘 봉을 주지 않는 경우
    rig.trader.run(max_days=1)
    (buy,) = rig.orders()
    assert buy["ts"] <= "2024-03-04T09:01:00"        # 거래량 변화로 한 틱 뒤에 개장 확인


def test_late_start_skips_open_buys_and_passed_breakouts_but_sells(tmp_path):
    plans = {"A": BUY_OPEN, "B": DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=300)),
             "C": DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=300))}

    class S(ScriptedStrategy):
        def plan(self, history, position):
            return plans[history[-1].volume]

    hist = {s: [Bar(date(2024, 3, 1), 10_000, 10_000, 10_000, 10_000, s)] for s in "ABC"}
    paths = {MON: {
        "A": [("09:00", 10_000), ("15:30", 10_000)],
        "B": [("09:00", 10_000), ("10:00", 10_400), ("10:30", 10_320), ("15:30", 10_320)],   # 봇 시작 전에 이미 돌파
        "C": [("09:00", 10_000), ("13:00", 10_310), ("15:30", 10_310)],                        # 봇 시작 후 돌파
    }}
    rig = Rig(tmp_path, at(MON, 11, 0), paths, strategy=S(), universe=("A", "B", "C"), history=hist)
    rig.trader.run(max_days=1)
    assert [(o["symbol"], o["price"]) for o in rig.orders()] == [("C", 10_310)]


def test_kill_switch_pauses_and_resumes(tmp_path):
    paths = {MON: {"A": [("09:00", 10_000), ("12:00", 10_100), ("15:30", 10_100)]}}
    rig = Rig(tmp_path, at(MON, 8, 0), paths)
    rig.killed = True
    release_at = at(MON, 9, 10)

    def kill() -> bool:
        return rig.clock.now() < release_at

    rig.core._kill_switch = kill
    rig.trader._kill_switch = kill
    rig.trader.run(max_days=1)
    (buy,) = rig.orders()
    assert buy["ts"] >= "2024-03-04T09:10:00" and buy["ts"] < "2024-03-04T09:11:00"


def test_kill_switch_all_day_means_no_orders(tmp_path):
    paths = {MON: {"A": [("09:00", 10_000), ("11:00", 9_000), ("15:30", 9_000)]}}
    rig = Rig(tmp_path, at(MON, 8, 0), paths)
    rig.killed = True
    rig.trader.run(max_days=1)
    assert rig.orders() == [] and rig.core.day.ended


def test_liquidate_command_sells_all_and_sets_stop(tmp_path):
    paths = {MON: {"A": [("09:00", 10_000), ("12:00", 10_100), ("15:30", 10_100)]}}
    rig = Rig(tmp_path, at(MON, 8, 0), paths)
    fired = {"done": False}

    def maybe_enqueue() -> bool:
        if not fired["done"] and rig.clock.now() >= at(MON, 12, 0):
            fired["done"] = True
            enqueue_command(tmp_path, "paper", "liquidate")
        return (tmp_path / "STOP").exists()

    rig.core._kill_switch = maybe_enqueue
    rig.trader._kill_switch = maybe_enqueue
    rig.trader.run(max_days=1)
    buy, sell = rig.orders()
    assert sell["side"] == "sell" and "사용자 청산 요청" in sell["reason"] and sell["price"] == 10_100
    assert (tmp_path / "STOP").exists()
    assert rig.core.positions == {}


def test_liquidate_command_outside_market_hours_is_cancelled(tmp_path):
    from autotrader.models import Position

    rig = Rig(tmp_path, at(date(2024, 3, 2), 12, 0), paths={})
    rig.core.positions["A"] = Position("A", 10, 10_000, date(2024, 3, 1), 10_000)
    enqueue_command(tmp_path, "paper", "liquidate")
    stop_at = at(date(2024, 3, 2), 12, 5)
    rig.trader._stop_requested = lambda: rig.clock.now() >= stop_at
    rig.trader.run()
    assert not (tmp_path / "STOP").exists()          # 팔 수 없는 시간 → 요청 취소, 정지도 걸지 않음
    assert "A" in rig.core.positions and rig.orders() == []
    assert any("장중에만" in a for a in rig.alerts)


def test_liquidate_with_no_positions_just_stops(tmp_path):
    rig = Rig(tmp_path, at(date(2024, 3, 2), 12, 0), paths={})
    enqueue_command(tmp_path, "paper", "liquidate")
    stop_at = at(date(2024, 3, 2), 12, 5)
    rig.trader._stop_requested = lambda: rig.clock.now() >= stop_at
    rig.trader.run()
    assert (tmp_path / "STOP").exists()


def test_forget_and_resume_commands(tmp_path):
    paths = {MON: {"A": [("09:00", 10_000), ("15:30", 10_000)]}}
    rig = Rig(tmp_path, at(MON, 8, 0), paths)
    rig.core.halted = True                      # 최대 낙폭 중단 상태에서 시작
    enqueue_command(tmp_path, "paper", "resume")
    rig.trader.run(max_days=1)
    assert not rig.core.halted and "A" in rig.core.positions
    enqueue_command(tmp_path, "paper", "forget", symbol="a", qty=None, price=10_500)
    rig.trader._housekeeping()
    assert rig.core.positions == {}
    assert rig.core.cash == pytest.approx(10_000_000 + 300 * 500)


def test_quote_failures_do_not_crash_and_alert_once(tmp_path):
    paths = {MON: {"A": [("09:00", 10_000), ("15:30", 10_000)]}}
    rig = Rig(tmp_path, at(MON, 8, 0), paths)
    orig = rig.market.get_quote

    def flaky(symbol):
        now = rig.clock.now()
        if at(MON, 10, 0) <= now < at(MON, 11, 0):
            raise BrokerError("network down")
        return orig(symbol)

    rig.market.get_quote = flaky
    rig.trader.run(max_days=1)
    assert sum("시세 조회가 계속 실패" in a for a in rig.alerts) == 1
    assert sum("다시 정상화" in a for a in rig.alerts) == 1
    assert rig.core.day.ended


def test_history_failure_means_no_new_entry_for_that_symbol(tmp_path):
    paths = {MON: {"A": [("09:00", 10_000), ("15:30", 10_000)], "B": [("09:00", 10_000), ("15:30", 10_000)]}}
    rig = Rig(tmp_path, at(MON, 8, 0), paths, universe=("A", "B"))
    orig = rig.market.get_daily_bars

    def bars(symbol, start, end):
        if symbol == "B" and end < MON:
            raise BrokerError("no history")
        return orig(symbol, start, end)

    rig.market.get_daily_bars = bars
    rig.trader.run(max_days=1)
    assert {o["symbol"] for o in rig.orders()} == {"A"}
    assert any("일봉 데이터를 받지 못한" in a and "B" in a for a in rig.alerts)


def test_restart_mid_day_does_not_duplicate_orders(tmp_path):
    paths = {MON: {"A": [("09:00", 10_000), ("11:00", 9_400), ("15:30", 9_400)]}}
    db = tmp_path / "state.db"
    store = SqliteStore(db)
    rig = Rig(tmp_path, at(MON, 8, 0), paths, store=store)
    stop_at = at(MON, 10, 0)
    rig.trader._stop_requested = lambda: rig.clock.now() >= stop_at
    rig.trader.run()                                   # 10시에 봇이 꺼짐
    assert len(rig.orders()) == 1
    store.close()

    store2 = SqliteStore(db)
    rig2 = Rig(tmp_path, at(MON, 10, 30), paths, store=store2)
    rig2.trader.run(max_days=1)                        # 10:30 재시작 → 매수 반복 없이 손절만 수행
    orders = rig2.orders()
    assert [o["side"] for o in orders] == ["buy", "sell"]
    assert rig2.core.positions == {}
    store2.close()


def test_account_mismatch_is_reported_not_auto_fixed(tmp_path):
    class AcctBroker(PaperBroker):
        def get_account(self):
            return AccountSnapshot(cash=0, total_equity=0, positions={"A": BrokerPosition("A", 100, 100, 10_000)})

    paths = {MON: {"A": [("09:00", 10_000), ("15:30", 10_000)]},
             TUE: {"A": [("09:00", 10_000), ("15:30", 10_000)]}}
    rig = Rig(tmp_path, at(MON, 8, 0), paths, broker=AcctBroker())
    rig.history["A"] = flat_history()
    rig.trader.run(max_days=1)
    rig.history["A"] = flat_history() + [Bar(MON, 10_000, 10_000, 10_000, 10_000, 1000.0)]
    rig.trader.run(max_days=1)
    assert rig.core.positions["A"].qty == 300          # 장부는 그대로
    assert sum("계좌 보유 수량(100주)" in a for a in rig.alerts) == 1


def test_runs_multiple_days_and_sleeps_between(tmp_path):
    strat = ScriptedStrategy(default=lambda h, p: DayPlan(exit=ExitRule(ExitKind.OPEN)) if p else BUY_OPEN)
    paths = {MON: {"A": [("09:00", 10_000), ("15:30", 10_200)]},
             TUE: {"A": [("09:00", 10_300), ("15:30", 10_300)]}}
    rig = Rig(tmp_path, at(MON, 8, 0), paths, strategy=strat)
    orig = rig.market.get_daily_bars

    def bars(symbol, start, end):
        out = orig(symbol, start, end)
        if rig.clock.now().date() == TUE and end >= MON and not any(b.date == MON for b in out):
            out = [b for b in out if b.date < MON] + [Bar(MON, 10_000, 10_200, 10_000, 10_200, 1.0)] + [b for b in out if b.date > MON]
        return out

    rig.market.get_daily_bars = bars
    rig.trader.run(max_days=2)
    assert [(o["day"], o["side"], o["price"]) for o in rig.orders()] == [
        (MON.isoformat(), "buy", 10_000), (TUE.isoformat(), "sell", 10_300)]
    assert [d for d, _, _ in rig.store.equity_history()] == [MON, TUE]


def test_end_of_day_uses_official_daily_close_and_ignores_late_quotes(tmp_path):
    # 15:30 종가는 10,200 인데 그 뒤(시간외)에 현재가가 10,900 으로 바뀐 상황
    paths = {MON: {"A": [("09:00", 10_000), ("15:30", 10_200), ("16:10", 10_900)]}}
    rig = Rig(tmp_path, at(MON, 16, 15), paths)                       # 마감 45분 뒤에 봇을 켬
    rig.core.positions["A"] = __import__("autotrader.models", fromlist=["Position"]).Position("A", 10, 10_000, date(2024, 3, 1), 10_000)
    orig = rig.market.get_daily_bars
    rig.market.get_daily_bars = lambda s, a, b: [Bar(MON, 10_000, 10_250, 9_950, 10_200, 500.0)] if a == b == MON else orig(s, a, b)
    rig.trader.run(max_days=1)
    assert rig.core.close_marks["A"] == (MON.isoformat(), 10_200)       # 일봉의 공식 종가를 기록
    assert rig.core.positions["A"].highest_price == 10_250

    # 일봉을 못 받았고 마감 후 25분이 지났으면 현재가를 종가로 쓰지 않음
    rig2 = Rig(tmp_path / "b", at(MON, 16, 15), paths)
    rig2.core.positions["A"] = __import__("autotrader.models", fromlist=["Position"]).Position("A", 10, 10_000, date(2024, 3, 1), 10_000)
    rig2.market.daily_includes_today = False
    rig2.trader.run(max_days=1)
    assert "A" not in rig2.core.close_marks

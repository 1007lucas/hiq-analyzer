"""매매 판단 코어 (TradingCore).

백테스트와 실전이 **같은 코어**를 공유합니다. 코어는 시계도 네트워크도 모릅니다.
바깥의 '드라이버'가 하루의 사건을 순서대로 알려 주면, 코어가 전략 계획과
리스크 규칙에 따라 브로커에 주문을 내고 장부(현금·포지션)를 갱신합니다.

하루의 흐름 (드라이버가 호출하는 순서)
--------------------------------------
1. ``start_day(day, histories)``   장 시작 전. 전일까지의 일봉으로 종목별 DayPlan 수립
2. ``on_open(prices, opens)``      장 시작 직후. 시가 청산 → 갭 손절/익절 → 시가 진입
3. ``on_price(symbol, price)``     장중 반복. 손절/익절/추적손절, 돌파 진입
4. ``on_close(prices)``            장 마감 직전. 종가 청산
5. ``end_day(closes, highs)``      장 마감 후. 평가금 기록, 추적손절 기준가 갱신

* 백테스트 드라이버: 일봉의 시가/고가/저가/종가로 위 사건을 합성합니다.
* 실전 드라이버: 실제 시계와 실시간 시세로 위 사건을 발생시킵니다.

장부 원칙
---------
* 봇은 설정된 운용자금(risk.capital) 안에서만 매매하는 **가상 계좌**를 가집니다.
  계좌에 다른 돈이나 수동 매수 종목이 있어도 건드리지 않습니다.
* 수수료/세금은 설정된 비율로 **추정**해서 장부에 반영합니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, Callable, Mapping, Sequence

from .brokers.base import Broker
from .config import CostConfig, RiskConfig
from .models import Bar, OrderRequest, OrderResult, OrderStatus, Position, Side, now_kst
from .state import StateStore
from .strategies.base import HOLD, DayPlan, EntryKind, EntryRule, ExitKind, ExitRule, Strategy

STATE_VERSION = 1
MAX_EXIT_RETRIES = 3          # 같은 날 한 종목의 매도 실패 허용 횟수 (넘으면 잠그고 알림)
MAX_HISTORY_GAP_DAYS = 10     # 마지막 일봉이 이보다 오래됐으면 '데이터 이상'으로 보고 신규 진입 안 함
MAX_DAILY_MOVE = 0.31         # 전일 종가 대비 이보다 크게 벗어난 시세는 오류로 보고 무시 (가격제한폭 ±30%)
ADJUST_TOLERANCE = 0.02       # 봇이 본 종가와 수정주가 일봉의 종가가 이보다 다르면 액면분할 등 권리 변동으로 간주

log = logging.getLogger("autotrader.core")


# --------------------------------------------------------------------------- #
# 당일 상태
# --------------------------------------------------------------------------- #
@dataclass
class SymbolDay:
    """한 종목의 '오늘' 진행 상황."""

    plan: DayPlan = HOLD
    note: str = ""                  # 계획 관련 메모 (예: "일봉 부족")
    open_price: float = 0.0         # 오늘 시가 (돌파 목표가 계산용)
    prev_close: float = 0.0         # 전 거래일 종가 (비정상 시세 걸러내기용, 0 = 모름)
    odd_price_logged: bool = False  # 비정상 시세 경고를 이미 남겼는지
    cooldown: bool = False          # 재진입 금지 기간
    open_exit_done: bool = False    # 시가 청산 시도함
    entry_attempted: bool = False   # 오늘 진입 시도함 (성공/실패 무관, 하루 1회)
    entered: bool = False           # 오늘 진입 체결됨
    exited: bool = False            # 오늘 청산 체결됨
    risk_exited: bool = False       # 오늘 손절/익절로 청산됨
    exit_pending: str = ""          # 청산이 덜 끝남 → 다음 시세에 재시도 (값 = 사유)
    exit_pending_risk: bool = False
    exit_failures: int = 0
    exit_blocked: bool = False      # 매도 반복 실패/불확실 → 오늘은 봇이 손대지 않음 (수동 확인)
    entry_blocked: bool = False     # 매수 결과 불확실 → 오늘은 진입 금지

    def to_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "plan"}
        d["plan"] = _plan_to_dict(self.plan)
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "SymbolDay":
        kwargs = {k: d[k] for k in cls.__dataclass_fields__ if k != "plan" and k in d}
        return cls(plan=_plan_from_dict(d.get("plan") or {}), **kwargs)


@dataclass
class DayState:
    day: date
    start_equity: float
    symbols: dict[str, SymbolDay] = field(default_factory=dict)
    opened: bool = False            # on_open 처리됨
    closed: bool = False            # on_close 처리됨 (이후 장중 판단 없음)
    ended: bool = False             # end_day 처리됨
    entries_halted: bool = False    # 일일 손실 한도 도달 → 오늘 신규 진입 중단
    buy_orders: int = 0             # 오늘 낸 매수 주문 수
    pending: dict[str, Any] | None = None   # 브로커에 전송 중이던 주문 (비정상 종료 복구용)

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "start_equity": self.start_equity,
            "symbols": {s: sd.to_dict() for s, sd in self.symbols.items()},
            "opened": self.opened,
            "closed": self.closed,
            "ended": self.ended,
            "entries_halted": self.entries_halted,
            "buy_orders": self.buy_orders,
            "pending": self.pending,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "DayState":
        return cls(
            day=date.fromisoformat(d["day"]),
            start_equity=float(d["start_equity"]),
            symbols={s: SymbolDay.from_dict(v) for s, v in (d.get("symbols") or {}).items()},
            opened=bool(d.get("opened", False)),
            closed=bool(d.get("closed", False)),
            ended=bool(d.get("ended", False)),
            entries_halted=bool(d.get("entries_halted", False)),
            buy_orders=int(d.get("buy_orders", 0)),
            pending=d.get("pending"),
        )


@dataclass(frozen=True)
class WatchLevels:
    """장중에 지켜봐야 할 가격 수준 (0 = 해당 없음)."""

    stop: float = 0.0           # 이 가격 이하면 매도 (손절 또는 추적손절)
    stop_kind: str = ""         # "stop_loss" | "trailing_stop"
    take_profit: float = 0.0    # 이 가격 이상이면 매도 (익절)
    breakout: float = 0.0       # 이 가격 이상이면 매수 (돌파 진입)

    @property
    def any(self) -> bool:
        return self.stop > 0 or self.take_profit > 0 or self.breakout > 0


def _plan_to_dict(plan: DayPlan) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if plan.entry is not None:
        e = plan.entry
        out["entry"] = {"kind": e.kind.value, "offset": e.offset, "score": e.score, "note": e.note}
    if plan.exit is not None:
        out["exit"] = {"kind": plan.exit.kind.value, "note": plan.exit.note}
    return out


def _plan_from_dict(d: Mapping[str, Any]) -> DayPlan:
    entry = exit_ = None
    if d.get("entry"):
        e = d["entry"]
        entry = EntryRule(
            kind=EntryKind(e["kind"]),
            offset=float(e.get("offset", 0.0)),
            score=float(e.get("score", 0.0)),
            note=str(e.get("note", "")),
        )
    if d.get("exit"):
        x = d["exit"]
        exit_ = ExitRule(kind=ExitKind(x["kind"]), note=str(x.get("note", "")))
    return DayPlan(entry=entry, exit=exit_)


def risk_levels(pos: Position, risk: RiskConfig) -> tuple[float, str, float]:
    """(손절가, 손절 종류, 익절가). 해당 없으면 0 / ""."""
    stop, kind = 0.0, ""
    if risk.stop_loss_pct > 0:
        stop, kind = pos.avg_price * (1.0 - risk.stop_loss_pct), "stop_loss"
    if risk.trailing_stop_pct > 0:
        t = pos.highest_price * (1.0 - risk.trailing_stop_pct)
        if t > stop:
            stop, kind = t, "trailing_stop"
    tp = pos.avg_price * (1.0 + risk.take_profit_pct) if risk.take_profit_pct > 0 else 0.0
    return stop, kind, tp


def build_snapshot(
    *,
    time_iso: str,
    strategy_name: str,
    strategy_params: Mapping[str, Any],
    capital: float,
    cash: float,
    positions: Mapping[str, Position],
    last_prices: Mapping[str, float],
    day: DayState | None,
    peak_equity: float,
    halted: bool,
    cooldowns: Mapping[str, int],
    risk: RiskConfig,
    name_of: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """봇 상태 요약을 JSON 직렬화 가능한 dict 로 만듭니다 (status 명령 / 대시보드 / 알림 공용)."""
    name = name_of or (lambda s: s)
    d = day
    pos_rows = []
    positions_value = 0.0
    for sym, pos in positions.items():
        price = float(last_prices.get(sym, 0.0) or 0.0)
        if price <= 0:
            price = pos.avg_price
        stop, kind, tp = risk_levels(pos, risk)
        positions_value += pos.qty * price
        pos_rows.append(
            {
                "symbol": sym,
                "name": name(sym),
                "qty": pos.qty,
                "avg_price": pos.avg_price,
                "price": price,
                "value": pos.qty * price,
                "pnl": (price - pos.avg_price) * pos.qty,
                "pnl_pct": (price / pos.avg_price - 1.0) if pos.avg_price > 0 else 0.0,
                "entry_date": pos.entry_date.isoformat(),
                "entry_reason": pos.entry_reason,
                "stop": stop,
                "stop_kind": kind,
                "take_profit": tp,
            }
        )
    plan_rows = []
    if d is not None:
        for sym, sd in d.symbols.items():
            entry, exit_ = sd.plan.entry, sd.plan.exit
            plan_rows.append(
                {
                    "symbol": sym,
                    "name": name(sym),
                    "entry": entry.kind.value if entry else "",
                    "entry_note": entry.note if entry else "",
                    "breakout_target": (sd.open_price + entry.offset)
                    if entry and entry.kind == EntryKind.BREAKOUT and sd.open_price > 0
                    else 0.0,
                    "exit": exit_.kind.value if exit_ else "",
                    "exit_note": exit_.note if exit_ else "",
                    "note": sd.note,
                    "open_price": sd.open_price,
                    "cooldown": sd.cooldown,
                    "entered": sd.entered,
                    "exited": sd.exited,
                    "entry_blocked": sd.entry_blocked,
                    "exit_blocked": sd.exit_blocked,
                }
            )
    equity = cash + positions_value
    return {
        "time": time_iso,
        "strategy": strategy_name,
        "strategy_params": dict(strategy_params),
        "capital": capital,
        "cash": cash,
        "positions_value": positions_value,
        "equity": equity,
        "total_return": (equity / capital - 1.0) if capital > 0 else 0.0,
        "peak_equity": peak_equity,
        "halted": halted,
        "day": d.day.isoformat() if d else "",
        "day_opened": bool(d and d.opened),
        "day_closed": bool(d and d.closed),
        "day_ended": bool(d and d.ended),
        "day_start_equity": d.start_equity if d else 0.0,
        "day_return": (equity / d.start_equity - 1.0) if d and d.start_equity > 0 else 0.0,
        "entries_halted_today": bool(d and d.entries_halted),
        "cooldowns": dict(cooldowns),
        "positions": pos_rows,
        "plans": plan_rows,
    }


def snapshot_from_state(
    state: Mapping[str, Any],
    *,
    risk: RiskConfig,
    name_of: Callable[[str], str] | None = None,
    time_iso: str = "",
) -> dict[str, Any]:
    """저장된 코어 상태(StateStore.load_state 의 반환값)만으로 상태 요약을 만듭니다.

    봇을 띄우지 않고 (읽기 전용으로) 현재 상황을 보여 줄 때 씁니다 — status 명령, 대시보드.
    """
    return build_snapshot(
        time_iso=time_iso or str(state.get("saved_at", "")),
        strategy_name=str(state.get("strategy_name", "")),
        strategy_params=dict(state.get("strategy_params") or {}),
        capital=float(state.get("capital_base", 0.0)),
        cash=float(state.get("cash", 0.0)),
        positions={s: Position.from_dict(p) for s, p in (state.get("positions") or {}).items()},
        last_prices={s: float(p) for s, p in (state.get("last_prices") or {}).items()},
        day=DayState.from_dict(state["day"]) if state.get("day") else None,
        peak_equity=float(state.get("peak_equity", 0.0)),
        halted=bool(state.get("halted", False)),
        cooldowns={s: int(n) for s, n in (state.get("cooldowns") or {}).items()},
        risk=risk,
        name_of=name_of,
    )


# --------------------------------------------------------------------------- #
# 코어
# --------------------------------------------------------------------------- #
class TradingCore:
    def __init__(
        self,
        *,
        strategy: Strategy,
        universe: Sequence[str],
        risk: RiskConfig,
        costs: CostConfig,
        broker: Broker,
        store: StateStore,
        clock: Callable[[], datetime] | None = None,
        notify: Callable[[str], None] | None = None,
        kill_switch: Callable[[], bool] | None = None,
        name_of: Callable[[str], str] | None = None,
        enforce_drawdown_halt: bool = True,
    ) -> None:
        """
        clock        : 기록에 남길 현재 시각 (백테스트는 가상 시각을 넘김). 기본 = 실제 KST 시각
        notify       : 중요한 일을 사용자에게 알리는 함수 (텔레그램 등). 기본 = 아무것도 안 함
        kill_switch  : True 를 반환하면 어떤 주문도 내지 않음 (긴급 정지 파일 확인용)
        name_of      : 종목코드 → 표시 이름
        enforce_drawdown_halt : 최대 낙폭 한도(max_drawdown_pct) 적용 여부 (백테스트는 False)
        """
        if len(set(universe)) != len(universe):
            raise ValueError("universe 에 중복 종목이 있습니다")
        self.strategy = strategy
        self.universe: tuple[str, ...] = tuple(universe)
        self.risk = risk
        self.costs = costs
        self.broker = broker
        self.store = store
        self._clock = clock or now_kst
        self._notify_fn = notify
        self._kill_switch = kill_switch
        self._name_of = name_of or (lambda s: s)
        self.enforce_drawdown_halt = enforce_drawdown_halt

        # 장부
        self.capital_base: float = float(risk.capital)
        self.cash: float = float(risk.capital)
        self.positions: dict[str, Position] = {}
        self.last_prices: dict[str, float] = {}
        self.cooldowns: dict[str, int] = {}     # 종목 → 앞으로 진입이 금지되는 거래일 수
        self.close_marks: dict[str, tuple[str, float]] = {}   # 종목 → (날짜, 봇이 기록한 그날 종가)
        self.peak_equity: float = float(risk.capital)
        self.halted: bool = False               # 최대 낙폭 한도 초과 → 수동 해제 전까지 신규 진입 중단
        self.day: DayState | None = None
        self._seq: int = 0
        self._kill_logged_day: date | None = None

        self._load()

    # ------------------------------------------------------------------ #
    # 조회
    # ------------------------------------------------------------------ #
    def name_of(self, symbol: str) -> str:
        """표시용 종목 이름 (설정에 이름이 없으면 종목코드)."""
        return self._name_of(symbol)

    def price_of(self, symbol: str) -> float:
        """마지막으로 알려진 가격 (없으면 보유 평균단가, 그것도 없으면 0)."""
        p = self.last_prices.get(symbol, 0.0)
        if p > 0:
            return p
        pos = self.positions.get(symbol)
        return pos.avg_price if pos else 0.0

    def positions_value(self) -> float:
        return sum(pos.qty * self.price_of(sym) for sym, pos in self.positions.items())

    def equity(self) -> float:
        """봇 평가금 = 현금 + 보유 주식 평가액."""
        return self.cash + self.positions_value()

    def watch_levels(self, symbol: str) -> WatchLevels:
        """지금 이 종목에서 지켜볼 가격 수준. 지켜볼 것이 없으면 모두 0."""
        d = self.day
        if d is None or not d.opened or d.closed or d.ended:
            return WatchLevels()
        sd = d.symbols.get(symbol)
        if sd is None:
            return WatchLevels()
        pos = self.positions.get(symbol)
        if pos is not None:
            if sd.exit_blocked:
                return WatchLevels()
            stop, kind, tp = risk_levels(pos, self.risk)
            return WatchLevels(stop=stop, stop_kind=kind, take_profit=tp)
        entry = sd.plan.entry
        if entry is not None and entry.kind == EntryKind.BREAKOUT and sd.open_price > 0:
            if self._entry_block_reason(symbol) is None:
                return WatchLevels(breakout=sd.open_price + entry.offset)
        return WatchLevels()

    def watched_symbols(self) -> list[str]:
        """장중에 시세를 확인해야 하는 종목 (보유 종목 + 돌파 대기 종목 + 청산 재시도 종목)."""
        d = self.day
        if d is None or not d.opened or d.ended:
            return []
        out: list[str] = []
        for sym in list(self.universe) + [s for s in self.positions if s not in self.universe]:
            sd = d.symbols.get(sym)
            if sd is None:
                continue
            if sym in self.positions:
                if not sd.exit_blocked:
                    out.append(sym)
            elif not d.closed and self.watch_levels(sym).breakout > 0:
                out.append(sym)
        return out

    def has_pending_close_exits(self) -> bool:
        """종가 청산 대상인데 아직 팔리지 않은 포지션이 있는지 (실전 드라이버의 재시도 판단용)."""
        d = self.day
        if d is None or d.ended:
            return False
        for sym in self.positions:
            sd = d.symbols.get(sym)
            if sd is None or sd.exit_blocked:
                continue
            if sd.plan.exit is not None and sd.plan.exit.kind == ExitKind.CLOSE:
                return True
        return False

    def snapshot(self) -> dict[str, Any]:
        """상태 요약 (status 명령 / 대시보드용). JSON 으로 직렬화 가능한 dict."""
        return build_snapshot(
            time_iso=self._clock().isoformat(),
            strategy_name=self.strategy.name,
            strategy_params=dict(self.strategy.params),
            capital=self.capital_base,
            cash=self.cash,
            positions=self.positions,
            last_prices=self.last_prices,
            day=self.day,
            peak_equity=self.peak_equity,
            halted=self.halted,
            cooldowns=self.cooldowns,
            risk=self.risk,
            name_of=self._name_of,
        )

    # ------------------------------------------------------------------ #
    # 하루의 사건들
    # ------------------------------------------------------------------ #
    def start_day(self, day: date, histories: Mapping[str, Sequence[Bar]]) -> None:
        """오늘(day)의 계획을 세웁니다. histories 에는 day 이전의 일봉만 사용됩니다."""
        prev = self.day
        if prev is not None and prev.day == day:
            # 같은 날 재시작: 진행 상황은 그대로 두고, 빠진 종목만 채웁니다.
            for sym in self._tracked_symbols():
                if sym not in prev.symbols:
                    prev.symbols[sym] = self._make_symbol_day(sym, day, histories, in_cooldown=False)
            self._save()
            return
        if prev is not None and prev.day > day:
            raise ValueError(f"이미 {prev.day} 까지 진행했습니다. 과거 날짜({day})로 돌아갈 수 없습니다")
        if prev is not None and not prev.ended:
            # 전 거래일이 마감 처리되지 않고 넘어옴 (봇이 장중에 꺼졌던 경우) → 마지막 가격으로 마감 처리
            self._warn(f"{prev.day} 거래일이 마감 처리되지 않아 마지막으로 알려진 가격으로 마감합니다")
            self.end_day({}, None)

        blocked_today = {s for s, n in self.cooldowns.items() if n > 0}
        self.cooldowns = {s: n - 1 for s, n in self.cooldowns.items() if n - 1 > 0}

        ds = DayState(day=day, start_equity=self.equity())
        for sym in self._tracked_symbols():
            ds.symbols[sym] = self._make_symbol_day(sym, day, histories, in_cooldown=sym in blocked_today)
        self.day = ds
        self._save()

    def on_open(
        self,
        prices: Mapping[str, float],
        opens: Mapping[str, float] | None = None,
        allow_entries: bool = True,
    ) -> None:
        """장 시작 처리.

        prices        : 지금 체결 가능한 가격 (백테스트 = 시가, 실전 = 현재가)
        opens         : 오늘의 공식 시가 (돌파 목표가 기준). None 이면 prices 와 같다고 봅니다.
        allow_entries : False 면 '시가 매수'를 건너뜁니다 (봇을 늦게 켠 경우).
        """
        d = self._require_day()
        if d.opened or d.ended or self._killed():
            return
        prices = self._usable(prices)
        ref_opens = prices if opens is None else self._usable(opens)
        for sym, sd in d.symbols.items():
            o = ref_opens.get(sym, 0.0)
            if o > 0:
                sd.open_price = o
        self._mark(prices)

        # 1) 전략의 시가 청산
        for sym in list(self.positions):
            sd = d.symbols.get(sym)
            price = prices.get(sym, 0.0)
            if sd is None or price <= 0:
                continue
            self._maybe_open_exit(sym, sd, price)

        # 2) 갭 하락/상승으로 이미 손절·익절 수준을 넘은 종목
        for sym in list(self.positions):
            price = prices.get(sym, 0.0)
            if price > 0:
                self._check_risk_exit(sym, price)

        d.opened = True

        # 3) 시가 진입 (점수 높은 순, 같으면 universe 순서)
        if allow_entries:
            order = {s: i for i, s in enumerate(self.universe)}
            cands = []
            for sym in self.universe:
                sd = d.symbols.get(sym)
                price = prices.get(sym, 0.0)
                if sd is None or price <= 0 or sym in self.positions:
                    continue
                entry = sd.plan.entry
                if entry is None or entry.kind != EntryKind.OPEN:
                    continue
                if sd.exited:
                    continue  # 오늘 시가에 판 종목을 같은 시가에 되사지 않음
                cands.append((-entry.score, order[sym], sym, price, entry))
            for _, _, sym, price, entry in sorted(cands):
                self._enter(sym, price, f"시가 매수: {entry.note}" if entry.note else "시가 매수")

        self._check_daily_loss()
        self._save()

    def on_price(self, symbol: str, price: float, open_price: float | None = None) -> None:
        """장중 시세 1건. 손절/익절/돌파 진입을 판단합니다."""
        d = self.day
        if d is None or not d.opened or d.closed or d.ended:
            return
        price = float(price or 0.0)
        if price <= 0 or self._killed():
            return
        sd = d.symbols.get(symbol)
        if sd is None or self._odd_price(symbol, sd, price):
            return
        self.last_prices[symbol] = price
        if open_price and open_price > 0 and sd.open_price <= 0 and not self._odd_price(symbol, sd, float(open_price)):
            sd.open_price = float(open_price)

        pos = self.positions.get(symbol)
        if pos is not None:
            if sd.exit_blocked:
                pass
            elif sd.exit_pending:
                self._sell(symbol, price, sd.exit_pending, risk_exit=sd.exit_pending_risk)
            elif not self._maybe_open_exit(symbol, sd, price):
                self._check_risk_exit(symbol, price)
        else:
            entry = sd.plan.entry
            if entry is not None and entry.kind == EntryKind.BREAKOUT and sd.open_price > 0:
                target = sd.open_price + entry.offset
                if price >= target and self._entry_block_reason(symbol) is None:
                    if price <= target * (1.0 + self.risk.breakout_max_chase_pct) + 1e-9:
                        note = f"돌파 매수(목표가 {target:,.0f}): {entry.note}" if entry.note else f"돌파 매수(목표가 {target:,.0f})"
                        self._enter(symbol, price, note)
        self._check_daily_loss()

    def on_close(self, prices: Mapping[str, float]) -> None:
        """장 마감 직전 처리: 종가 청산. 팔리지 않은 종목이 있으면 다시 호출해 재시도할 수 있습니다."""
        d = self._require_day()
        if d.ended or self._killed():
            return
        prices = self._usable(prices)
        self._mark(prices)
        if d.opened:
            for sym in list(self.positions):
                sd = d.symbols.get(sym)
                price = prices.get(sym, 0.0)
                if sd is None or price <= 0 or sd.exit_blocked:
                    continue
                ex = sd.plan.exit
                if ex is not None and ex.kind == ExitKind.CLOSE:
                    self._sell(sym, price, f"종가 청산: {ex.note}" if ex.note else "종가 청산", risk_exit=False)
        d.closed = True
        self._save()

    def end_day(self, closes: Mapping[str, float], highs: Mapping[str, float] | None = None) -> None:
        """장 마감 후 처리: 평가금 기록, 추적손절 기준가 갱신, 최대 낙폭 점검."""
        d = self._require_day()
        if d.ended:
            return
        self._mark(closes)
        for sym, pos in self.positions.items():
            ref = max(
                float((highs or {}).get(sym, 0.0) or 0.0),
                float(closes.get(sym, 0.0) or 0.0),
            )
            if ref > pos.highest_price:
                pos.highest_price = ref
        # 권리 변동(액면분할 등) 감지를 위해 보유 종목의 오늘 종가를 기록해 둡니다.
        self.close_marks = {s: m for s, m in self.close_marks.items() if s in self.positions}
        for sym in self.positions:
            c = float(closes.get(sym, 0.0) or 0.0)
            if c > 0:
                self.close_marks[sym] = (d.day.isoformat(), c)
        eq = self.equity()
        self.store.record_equity(d.day, eq, self.cash)
        if eq > self.peak_equity:
            self.peak_equity = eq
        mdd = self.risk.max_drawdown_pct
        if self.enforce_drawdown_halt and mdd > 0 and not self.halted and self.peak_equity > 0:
            if eq <= self.peak_equity * (1.0 - mdd):
                self.halted = True
                self._alert(
                    f"⛔ 최대 낙폭 한도 도달: 최고 평가금 {self.peak_equity:,.0f}원 → 현재 {eq:,.0f}원 "
                    f"({eq / self.peak_equity - 1.0:+.1%}). 신규 매수를 중단합니다. "
                    "'resume' 명령으로 해제하기 전까지 보유 종목의 청산만 수행합니다."
                )
        d.closed = True
        d.ended = True
        self._save()

    # ------------------------------------------------------------------ #
    # 수동 조작
    # ------------------------------------------------------------------ #
    def liquidate_all(self, reason: str, prices: Mapping[str, float] | None = None) -> int:
        """보유 종목 전량 매도 시도. 매도 주문을 낸 종목 수를 반환합니다."""
        self._require_day()
        n = 0
        for sym in list(self.positions):
            price = float((prices or {}).get(sym, 0.0) or 0.0) or self.last_prices.get(sym, 0.0)
            if price <= 0:
                self._warn(f"{self._name_of(sym)}: 가격을 알 수 없어 청산하지 못했습니다")
                continue
            if self._sell(sym, price, reason, risk_exit=True):
                n += 1
        self._save()
        return n

    def resume(self) -> None:
        """최대 낙폭 한도로 걸린 중단을 해제합니다 (최고 평가금 기준을 현재 값으로 재설정)."""
        self.halted = False
        self.peak_equity = self.equity()
        self._info("신규 매수 중단이 해제되었습니다")
        self._save()

    def forget_position(
        self, symbol: str, *, qty: int | None = None, price: float | None = None, reason: str = "수동 정리"
    ) -> bool:
        """봇 장부에서 포지션(또는 그 일부)을 '팔린 것'으로 정리합니다. 실제 주문은 내지 않습니다.

        사용자가 증권사 앱에서 직접 매도했거나, 액면분할 등으로 장부가 실제와 달라졌을 때 씁니다.
        price 를 주면 그 가격에, 없으면 마지막으로 알려진 가격에 판 것으로 현금을 정산합니다.
        """
        pos = self.positions.get(symbol)
        if pos is None:
            return False
        n = pos.qty if qty is None else max(0, min(int(qty), pos.qty))
        px = float(price) if price is not None and price > 0 else self.price_of(symbol)
        if n < 1 or px <= 0:
            return False
        now = self._clock()
        rec: dict[str, Any] = {
            "ts": now.isoformat(),
            "day": now.date().isoformat(),
            "symbol": symbol,
            "side": Side.SELL.value,
            "qty": n,
            "ref_price": px,
            "reason": reason,
            "status": OrderStatus.FILLED.value,
            "broker_order_id": "",
            "message": "장부 조정 (실제 주문 아님)",
        }
        rec.update(self._book_sell(pos, n, px))
        rec["cash_after"] = self.cash
        self.store.record_order(rec)
        self._alert(
            f"📝 {self._name_of(symbol)} {n:,}주를 장부에서 정리했습니다 — {reason} "
            f"(정산가 {px:,.0f}원, 손익 {rec['pnl']:+,.0f}원)"
        )
        self._save()
        return True

    def skip_entry_today(self, symbol: str, reason: str) -> None:
        """오늘 이 종목의 신규 진입을 포기합니다 (예: 봇을 켜기 전에 이미 돌파가 지나간 경우)."""
        d = self._require_day()
        sd = d.symbols.get(symbol)
        if sd is None or sd.entry_attempted:
            return
        sd.entry_attempted = True
        self._info(f"{self._name_of(symbol)}: 오늘 진입 건너뜀 — {reason}")
        self._save()

    def mark_prices(self, prices: Mapping[str, float]) -> None:
        """평가용 최신 가격만 갱신합니다 (주문 판단 없음)."""
        self._mark(prices)

    def recover_pending(self) -> None:
        """비정상 종료로 결과를 모르는 주문이 있으면 브로커에 물어 장부를 맞춥니다 (시작 시 1회 호출)."""
        d = self.day
        if d is None or not d.pending:
            return
        p = d.pending
        req = OrderRequest(
            symbol=str(p["symbol"]),
            side=Side(p["side"]),
            qty=int(p["qty"]),
            ref_price=float(p["ref_price"]),
            reason=str(p.get("reason", "")),
            client_id=str(p.get("client_id", "")),
        )
        since = datetime.fromisoformat(p["ts"])
        name = self._name_of(req.symbol)
        try:
            res = self.broker.recover_order(req, since)
        except Exception as e:  # noqa: BLE001 - 브로커 구현의 어떤 오류든 '불확실'로 처리
            res = OrderResult(req, OrderStatus.UNKNOWN, message=f"복구 조회 실패: {e}")
        d.pending = None
        if res is None:
            self._warn(f"{name}: 재시작 전 전송 중이던 주문은 접수되지 않은 것으로 확인되었습니다")
            self._save()
            return
        self._alert(f"⚠️ {name}: 재시작 전 전송 중이던 주문을 복구했습니다 ({res.status.value}, 체결 {res.filled_qty}주)")
        self._apply_result(res, risk_exit=bool(p.get("risk_exit", False)))
        self._save()

    # ------------------------------------------------------------------ #
    # 내부: 계획
    # ------------------------------------------------------------------ #
    def _tracked_symbols(self) -> list[str]:
        return list(self.universe) + [s for s in self.positions if s not in self.universe]

    def _make_symbol_day(
        self, sym: str, day: date, histories: Mapping[str, Sequence[Bar]], *, in_cooldown: bool
    ) -> SymbolDay:
        sd = SymbolDay(cooldown=in_cooldown)
        pos = self.positions.get(sym)
        hist = histories.get(sym) or ()
        if hist and hist[-1].date >= day:
            hist = [b for b in hist if b.date < day]   # 오늘 이후 봉은 절대 전략에 넘기지 않음
        if hist and (day - hist[-1].date).days <= MAX_HISTORY_GAP_DAYS:
            sd.prev_close = float(hist[-1].close)
        if pos is not None and self._rights_changed(sym, hist):
            sd.exit_blocked = True
            sd.entry_blocked = True
            sd.note = "권리 변동 의심 — 수동 확인 필요"
            self._alert(
                f"🚨 {self._name_of(sym)}: 액면분할·병합·증자 등으로 주가 기준이 바뀐 것으로 보입니다. "
                f"봇 장부의 수량({pos.qty}주)·단가({pos.avg_price:,.0f}원)가 실제와 다를 수 있어 이 종목은 자동 매매하지 않습니다. "
                "증권사 앱에서 직접 정리한 뒤 'forget' 명령으로 봇 장부에서 제거해 주세요."
            )
            return sd
        if sym not in self.universe:
            sd.plan = DayPlan(exit=ExitRule(ExitKind.OPEN, "매매 대상에서 제외된 종목"))
            return sd
        if len(hist) < max(1, self.strategy.warmup):
            sd.note = f"일봉 부족 ({len(hist)}/{self.strategy.warmup})"
            return sd
        if (day - hist[-1].date).days > MAX_HISTORY_GAP_DAYS:
            sd.note = f"일봉 데이터가 오래됨 (마지막 {hist[-1].date})"
            return sd
        try:
            plan = self.strategy.plan(hist, replace(pos) if pos is not None else None)
        except Exception as e:  # noqa: BLE001 - 전략 버그가 봇 전체를 죽이지 않도록
            log.exception("전략 오류 (%s)", sym)
            self._warn(f"{self._name_of(sym)}: 전략 계산 오류로 오늘은 관망합니다 ({e})")
            sd.note = f"전략 오류: {e}"
            return sd
        if not isinstance(plan, DayPlan):
            sd.note = "전략이 DayPlan 을 반환하지 않음"
            self._warn(f"{self._name_of(sym)}: {sd.note}")
            return sd
        sd.plan = plan
        return sd

    def _rights_changed(self, sym: str, hist: Sequence[Bar]) -> bool:
        """보유 종목의 주가 기준이 바뀌었는지 (액면분할 등).

        봇이 장 마감 때 기록해 둔 종가와, 지금 받은 수정주가 일봉의 같은 날짜 종가를 비교합니다.
        둘이 다르면 그 사이에 과거 주가가 소급 수정된 것 = 권리 변동이 있었다는 뜻입니다.
        """
        mark = self.close_marks.get(sym)
        if mark is None or not hist:
            return False
        mark_day, seen = mark
        if seen <= 0:
            return False
        for bar in reversed(hist[-30:]):
            iso = bar.date.isoformat()
            if iso == mark_day:
                return bar.close > 0 and abs(bar.close / seen - 1.0) > ADJUST_TOLERANCE
            if iso < mark_day:
                break
        return False

    def _odd_price(self, sym: str, sd: SymbolDay, price: float) -> bool:
        """전일 종가 대비 가격제한폭을 벗어난 시세인지 (시세 오류·권리락 등). True 면 이 시세로 판단하지 않습니다."""
        ref = sd.prev_close
        if ref <= 0 or ref * (1.0 - MAX_DAILY_MOVE) <= price <= ref * (1.0 + MAX_DAILY_MOVE):
            return False
        if not sd.odd_price_logged:
            sd.odd_price_logged = True
            self._warn(
                f"{self._name_of(sym)}: 비정상 시세 무시 — 현재가 {price:,.0f}원이 전일 종가 {ref:,.0f}원 대비 "
                f"가격제한폭(±30%)을 벗어났습니다"
            )
        return True

    # ------------------------------------------------------------------ #
    # 내부: 청산 판단
    # ------------------------------------------------------------------ #
    def _maybe_open_exit(self, sym: str, sd: SymbolDay, price: float) -> bool:
        """전략의 시가 청산 대상이면 매도. 매도를 시도했으면 True."""
        d = self._require_day()
        pos = self.positions.get(sym)
        ex = sd.plan.exit
        if pos is None or ex is None or ex.kind != ExitKind.OPEN:
            return False
        if sd.open_exit_done or sd.exit_blocked or pos.entry_date >= d.day:
            return False
        sd.open_exit_done = True
        self._sell(sym, price, f"시가 청산: {ex.note}" if ex.note else "시가 청산", risk_exit=False)
        return True

    def _check_risk_exit(self, sym: str, price: float) -> bool:
        d = self._require_day()
        pos = self.positions.get(sym)
        sd = d.symbols.get(sym)
        if pos is None or sd is None or sd.exit_blocked or sd.exit_pending:
            return False
        stop, kind, tp = risk_levels(pos, self.risk)
        if stop > 0 and price <= stop:
            label = "추적손절" if kind == "trailing_stop" else "손절"
            return self._sell(sym, price, f"{label}(기준가 {stop:,.0f})", risk_exit=True)
        if tp > 0 and price >= tp:
            return self._sell(sym, price, f"익절(기준가 {tp:,.0f})", risk_exit=True)
        return False

    def _check_daily_loss(self) -> None:
        d = self.day
        limit = self.risk.daily_loss_limit_pct
        if d is None or limit <= 0 or d.entries_halted or d.start_equity <= 0:
            return
        eq = self.equity()
        if eq > d.start_equity * (1.0 - limit):
            return
        d.entries_halted = True
        self._alert(
            f"⛔ 일일 손실 한도 도달: 오늘 시작 {d.start_equity:,.0f}원 → 현재 {eq:,.0f}원 "
            f"({eq / d.start_equity - 1.0:+.2%}). 오늘은 신규 매수를 중단합니다."
        )
        if self.risk.daily_loss_action == "liquidate":
            for sym in list(self.positions):
                price = self.last_prices.get(sym, 0.0)
                if price > 0:
                    self._sell(sym, price, "일일 손실 한도 초과 청산", risk_exit=True)
        self._save()

    # ------------------------------------------------------------------ #
    # 내부: 진입
    # ------------------------------------------------------------------ #
    def _entry_block_reason(self, sym: str) -> str | None:
        """지금 이 종목에 진입할 수 없는 이유. 진입 가능하면 None."""
        d = self._require_day()
        sd = d.symbols.get(sym)
        if sd is None or sym not in self.universe:
            return "매매 대상이 아님"
        if sym in self.positions:
            return "이미 보유 중"
        if self.halted:
            return "최대 낙폭 한도 초과로 신규 매수 중단 상태"
        if d.entries_halted:
            return "일일 손실 한도 도달"
        if sd.entry_attempted or sd.entered:
            return "오늘 이미 진입을 시도함"
        if sd.entry_blocked:
            return "매수 결과 불확실로 잠김"
        if sd.risk_exited:
            return "오늘 손절/익절된 종목"
        if sd.cooldown:
            return "재진입 금지 기간"
        if len(self.positions) >= self.risk.max_positions:
            return f"최대 보유 종목 수({self.risk.max_positions}) 도달"
        if d.buy_orders >= self.risk.max_orders_per_day:
            return f"하루 최대 매수 주문 수({self.risk.max_orders_per_day}) 도달"
        return None

    def _enter(self, sym: str, price: float, reason: str) -> bool:
        d = self._require_day()
        sd = d.symbols[sym]
        name = self._name_of(sym)
        why = self._entry_block_reason(sym)
        if why is not None:
            # 보유 종목 수 한도 등으로 오늘 기회를 놓친 경우도 '시도함'으로 기록 (하루 1회 원칙)
            sd.entry_attempted = True
            self._info(f"{name}: 매수 건너뜀 — {why}")
            return False
        sd.entry_attempted = True

        r, c = self.risk, self.costs
        equity = self.equity()
        budget = equity * r.position_pct
        if r.max_order_amount > 0:
            budget = min(budget, r.max_order_amount)
        budget = min(budget, self.cash - equity * r.cash_reserve_pct)
        unit_cost = price * (1.0 + c.slippage_rate) * (1.0 + c.commission_rate)
        qty = int(budget // unit_cost) if budget > 0 and unit_cost > 0 else 0
        if qty < 1:
            self._info(f"{name}: 매수 건너뜀 — 예산 {max(budget, 0):,.0f}원으로 1주({price:,.0f}원)를 살 수 없음")
            return False
        try:
            cap = self.broker.max_buy_qty(sym, price)
        except Exception as e:  # noqa: BLE001
            self._warn(f"{name}: 매수가능수량 조회 실패로 매수를 건너뜁니다 ({e})")
            return False
        if cap is not None and cap < qty:
            self._info(f"{name}: 계좌 매수가능수량({cap}주)에 맞춰 수량 축소 ({qty}주 → {cap}주)")
            qty = int(cap)
        if qty < 1:
            self._info(f"{name}: 매수 건너뜀 — 계좌 매수가능수량 0")
            return False

        d.buy_orders += 1
        res = self._submit(OrderRequest(sym, Side.BUY, qty, price, reason, self._next_id()), risk_exit=False)
        self._apply_result(res, risk_exit=False)
        self._save()
        return res.filled_qty > 0

    # ------------------------------------------------------------------ #
    # 내부: 매도
    # ------------------------------------------------------------------ #
    def _sell(self, sym: str, price: float, reason: str, *, risk_exit: bool) -> bool:
        """보유 수량 전부 매도 시도. 1주라도 체결되면 True."""
        d = self._require_day()
        pos = self.positions.get(sym)
        if pos is None:
            return False
        sd = d.symbols.setdefault(sym, SymbolDay())
        if sd.exit_blocked:
            return False
        name = self._name_of(sym)
        qty = pos.qty
        try:
            cap = self.broker.sellable_qty(sym)
        except Exception as e:  # noqa: BLE001
            cap = None
            self._warn(f"{name}: 매도가능수량 조회 실패 — 장부 수량으로 매도를 시도합니다 ({e})")
        if cap is not None and cap < qty:
            self._warn(f"{name}: 계좌 매도가능수량({cap}주)이 봇 장부({qty}주)보다 적습니다")
            qty = int(cap)
        if qty < 1:
            self._exit_failed(sym, sd, reason, risk_exit, "매도가능수량 0")
            self._save()
            return False

        res = self._submit(OrderRequest(sym, Side.SELL, qty, price, reason, self._next_id()), risk_exit=risk_exit)
        self._apply_result(res, risk_exit=risk_exit)
        self._save()
        return res.filled_qty > 0

    def _exit_failed(self, sym: str, sd: SymbolDay, reason: str, risk_exit: bool, detail: str) -> None:
        sd.exit_failures += 1
        sd.exit_pending = reason
        sd.exit_pending_risk = risk_exit
        if sd.exit_failures >= MAX_EXIT_RETRIES:
            sd.exit_blocked = True
            sd.exit_pending = ""
            self._alert(
                f"🚨 {self._name_of(sym)}: 매도가 {sd.exit_failures}회 실패했습니다 ({detail}). "
                "오늘은 봇이 이 종목을 더 건드리지 않습니다. 직접 확인해 주세요."
            )

    # ------------------------------------------------------------------ #
    # 내부: 주문 전송과 장부 반영
    # ------------------------------------------------------------------ #
    def _submit(self, req: OrderRequest, *, risk_exit: bool) -> OrderResult:
        d = self._require_day()
        if self.store.persistent:
            d.pending = {
                "symbol": req.symbol,
                "side": req.side.value,
                "qty": req.qty,
                "ref_price": req.ref_price,
                "reason": req.reason,
                "client_id": req.client_id,
                "risk_exit": risk_exit,
                "ts": self._clock().isoformat(),
            }
            self._save()
        try:
            res = self.broker.submit_order(req)
        except Exception as e:  # noqa: BLE001 - 브로커 구현이 예외를 던져도 장부가 깨지지 않도록
            log.exception("브로커 주문 예외 (%s)", req.symbol)
            res = OrderResult(req, OrderStatus.UNKNOWN, message=f"브로커 예외: {e}")
        d.pending = None
        return res

    def _apply_result(self, res: OrderResult, *, risk_exit: bool) -> None:
        """브로커 결과를 장부·기록·알림에 반영합니다."""
        d = self._require_day()
        req = res.request
        sym = req.symbol
        name = self._name_of(sym)
        sd = d.symbols.setdefault(sym, SymbolDay())
        c = self.costs

        filled = int(res.filled_qty or 0)
        price = float(res.avg_price or 0.0)
        status = res.status
        message = res.message or ""
        if filled < 0 or filled > req.qty:
            message = f"체결수량 이상({filled}/{req.qty}) {message}".strip()
            filled = max(0, min(filled, req.qty))
            status = OrderStatus.UNKNOWN
        if filled > 0 and price <= 0:
            message = f"체결가 이상({price}) {message}".strip()
            filled = 0
            status = OrderStatus.UNKNOWN
        if filled == 0 and status in (OrderStatus.FILLED, OrderStatus.PARTIAL):
            status = OrderStatus.REJECTED
        if 0 < filled < req.qty and status == OrderStatus.FILLED:
            status = OrderStatus.PARTIAL

        rec: dict[str, Any] = {
            "ts": (res.time or self._clock()).isoformat(),
            "day": d.day.isoformat(),
            "symbol": sym,
            "side": req.side.value,
            "qty": req.qty,
            "filled_qty": filled,
            "price": price if filled > 0 else 0.0,
            "ref_price": req.ref_price,
            "amount": filled * price,
            "fee": 0.0,
            "tax": 0.0,
            "pnl": None,
            "pnl_pct": None,
            "entry_price": None,
            "entry_day": None,
            "reason": req.reason,
            "status": status.value,
            "broker_order_id": res.broker_order_id,
            "message": message,
        }

        if req.side == Side.BUY:
            if filled > 0:
                amount = filled * price
                fee = amount * c.commission_rate
                self.cash -= amount + fee
                rec["fee"] = fee
                pos = self.positions.get(sym)
                if pos is None:
                    self.positions[sym] = Position(sym, filled, price, d.day, price, req.reason)
                else:  # 복구 등으로 같은 종목을 추가 매수한 드문 경우: 평균단가 갱신
                    total = pos.qty + filled
                    pos.avg_price = (pos.avg_price * pos.qty + amount) / total
                    pos.qty = total
                    pos.highest_price = max(pos.highest_price, price)
                self.last_prices[sym] = price
                sd.entered = True
                self._alert(
                    f"🟢 매수 {name} {filled:,}주 @ {price:,.0f}원 (약 {amount:,.0f}원) — {req.reason}"
                    + (f" [일부 체결 {filled}/{req.qty}]" if filled < req.qty else "")
                )
            if status == OrderStatus.UNKNOWN:
                sd.entry_blocked = True
                self._alert(
                    f"🚨 {name}: 매수 주문 결과를 확인할 수 없습니다 ({message or '사유 불명'}). "
                    "증권사 앱에서 주문/잔고를 직접 확인해 주세요. 오늘 이 종목은 추가 매수하지 않습니다."
                )
            elif filled == 0:
                self._warn(f"{name}: 매수 주문이 체결되지 않았습니다 ({message or '사유 불명'})")
        else:
            pos = self.positions.get(sym)
            if filled > 0 and pos is not None:
                filled = min(filled, pos.qty)
                rec.update(self._book_sell(pos, filled, price))
                pnl = rec["pnl"]
                self.last_prices[sym] = price
                sd.exited = True
                if risk_exit:
                    sd.risk_exited = True
                    if self.risk.cooldown_days > 0:
                        self.cooldowns[sym] = self.risk.cooldown_days
                self._alert(
                    f"🔴 매도 {name} {filled:,}주 @ {price:,.0f}원 — {req.reason} "
                    f"(손익 {pnl:+,.0f}원, {rec['pnl_pct']:+.2%})"
                    + (f" [일부 체결, 잔여 {pos.qty}주]" if pos.qty > 0 else "")
                )
            elif filled > 0:
                # 장부에 없는 종목의 매도 체결 (복구 과정의 드문 경우) — 기록만 남김
                rec["message"] = f"장부에 없는 포지션의 매도 체결 {message}".strip()

            still_held = sym in self.positions
            if status == OrderStatus.UNKNOWN:
                sd.exit_blocked = True
                sd.exit_pending = ""
                self._alert(
                    f"🚨 {name}: 매도 주문 결과를 확인할 수 없습니다 ({message or '사유 불명'}). "
                    "증권사 앱에서 주문/잔고를 직접 확인해 주세요. 오늘은 봇이 이 종목을 더 건드리지 않습니다."
                )
            elif still_held:
                self._warn(f"{name}: 매도가 완료되지 않았습니다 ({message or status.value}) — 재시도 예정")
                self._exit_failed(sym, sd, req.reason, risk_exit, message or status.value)
            else:
                sd.exit_pending = ""

        rec["cash_after"] = self.cash
        self.store.record_order(rec)

    def _book_sell(self, pos: Position, qty: int, price: float) -> dict[str, Any]:
        """매도 체결을 장부에 반영하고 (현금 증가, 포지션 감소) 기록용 필드를 돌려줍니다."""
        c = self.costs
        amount = qty * price
        fee = amount * c.commission_rate
        tax = amount * c.sell_tax_rate
        entry_cost = pos.avg_price * qty
        entry_fee = entry_cost * c.commission_rate
        pnl = amount - fee - tax - entry_cost - entry_fee
        basis = entry_cost + entry_fee
        self.cash += amount - fee - tax
        fields = {
            "filled_qty": qty,
            "price": price,
            "amount": amount,
            "fee": fee,
            "tax": tax,
            "pnl": pnl,
            "pnl_pct": (pnl / basis) if basis > 0 else 0.0,
            "entry_price": pos.avg_price,
            "entry_day": pos.entry_date.isoformat(),
        }
        pos.qty -= qty
        if pos.qty <= 0:
            self.positions.pop(pos.symbol, None)
            self.close_marks.pop(pos.symbol, None)
        return fields

    # ------------------------------------------------------------------ #
    # 내부: 기타
    # ------------------------------------------------------------------ #
    def _require_day(self) -> DayState:
        if self.day is None:
            raise RuntimeError("start_day() 를 먼저 호출해야 합니다")
        return self.day

    def _usable(self, prices: Mapping[str, float]) -> dict[str, float]:
        """양수이고 비정상 시세가 아닌 가격만 남깁니다."""
        d = self._require_day()
        out: dict[str, float] = {}
        for sym, p in prices.items():
            p = float(p or 0.0)
            if p <= 0:
                continue
            sd = d.symbols.get(sym)
            if sd is not None and self._odd_price(sym, sd, p):
                continue
            out[sym] = p
        return out

    def _mark(self, prices: Mapping[str, float]) -> None:
        for sym, p in prices.items():
            p = float(p or 0.0)
            if p > 0:
                self.last_prices[sym] = p

    def _next_id(self) -> str:
        self._seq += 1
        d = self.day
        return f"{d.day:%Y%m%d}-{self._seq}" if d else str(self._seq)

    def _killed(self) -> bool:
        if self._kill_switch is None:
            return False
        try:
            killed = bool(self._kill_switch())
        except Exception:  # noqa: BLE001 - 확인 실패 시 안전하게 '정지'로 간주
            killed = True
        if killed and self.day is not None and self._kill_logged_day != self.day.day:
            self._kill_logged_day = self.day.day
            self._alert("⏸ 긴급 정지 상태입니다 (STOP 파일). 어떤 주문도 내지 않습니다.")
        return killed

    def _info(self, msg: str) -> None:
        log.info(msg)
        if self.store.persistent:
            self.store.log_event("info", msg, self._clock())

    def _warn(self, msg: str) -> None:
        log.warning(msg)
        self.store.log_event("warning", msg, self._clock())

    def _alert(self, msg: str) -> None:
        """기록 + 사용자 알림."""
        log.info(msg)
        self.store.log_event("alert", msg, self._clock())
        if self._notify_fn is not None:
            try:
                self._notify_fn(msg)
            except Exception:  # noqa: BLE001 - 알림 실패가 매매를 막으면 안 됨
                log.exception("알림 전송 실패")

    # ------------------------------------------------------------------ #
    # 내부: 저장/복원
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "capital_base": self.capital_base,
            "cash": self.cash,
            "positions": {s: p.to_dict() for s, p in self.positions.items()},
            "last_prices": dict(self.last_prices),
            "cooldowns": dict(self.cooldowns),
            "close_marks": {s: [d, p] for s, (d, p) in self.close_marks.items()},
            "peak_equity": self.peak_equity,
            "halted": self.halted,
            "seq": self._seq,
            "day": self.day.to_dict() if self.day is not None else None,
            # 아래는 표시용 (복원에는 쓰지 않음)
            "strategy_name": self.strategy.name,
            "strategy_params": dict(self.strategy.params),
            "saved_at": self._clock().isoformat(),
        }

    def _save(self) -> None:
        if self.store.persistent:
            self.store.save_state(self.to_dict())

    def _load(self) -> None:
        if not self.store.persistent:
            return
        st = self.store.load_state()
        if not st:
            self._save()
            return
        if int(st.get("version", 0)) != STATE_VERSION:
            raise RuntimeError(
                f"상태 파일 버전({st.get('version')})이 프로그램 버전({STATE_VERSION})과 다릅니다. "
                "data 폴더의 상태 파일을 백업한 뒤 삭제하고 다시 시작해 주세요."
            )
        self.cash = float(st["cash"])
        self.positions = {s: Position.from_dict(p) for s, p in (st.get("positions") or {}).items()}
        self.last_prices = {s: float(p) for s, p in (st.get("last_prices") or {}).items()}
        self.cooldowns = {s: int(n) for s, n in (st.get("cooldowns") or {}).items()}
        self.close_marks = {s: (str(v[0]), float(v[1])) for s, v in (st.get("close_marks") or {}).items()}
        self.peak_equity = float(st.get("peak_equity", self.cash))
        self.halted = bool(st.get("halted", False))
        self._seq = int(st.get("seq", 0))
        self.day = DayState.from_dict(st["day"]) if st.get("day") else None

        # 운용자금 설정이 바뀌었으면 차액을 입금/출금으로 처리
        old_base = float(st.get("capital_base", self.risk.capital))
        new_base = float(self.risk.capital)
        if abs(new_base - old_base) > 1e-6:
            delta = new_base - old_base
            self.cash += delta
            self.peak_equity = max(self.peak_equity + delta, 0.0)
            if self.day is not None:
                self.day.start_equity += delta
            self._warn(
                f"운용자금 설정 변경 감지: {old_base:,.0f}원 → {new_base:,.0f}원 "
                f"(봇 현금 {delta:+,.0f}원 조정, 현재 현금 {self.cash:,.0f}원)"
            )
        self.capital_base = new_base
        self._save()

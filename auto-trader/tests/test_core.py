"""TradingCore 단위 테스트 — 진입/청산/리스크/장부/복구."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from autotrader.config import CostConfig, RiskConfig
from autotrader.core import MAX_EXIT_RETRIES, TradingCore
from autotrader.models import KST, Bar, OrderResult, OrderStatus, Side
from autotrader.state import MemoryStore, SqliteStore
from autotrader.strategies.base import DayPlan, EntryKind, EntryRule, ExitKind, ExitRule

from conftest import ScriptedBroker, ScriptedStrategy, make_bars

D1 = date(2024, 3, 4)   # 월
D2 = date(2024, 3, 5)
D3 = date(2024, 3, 6)
D4 = date(2024, 3, 7)
D5 = date(2024, 3, 8)
D6 = date(2024, 3, 11)

BUY_OPEN = DayPlan(entry=EntryRule(EntryKind.OPEN, note="t"))
SELL_OPEN = DayPlan(exit=ExitRule(ExitKind.OPEN, note="t"))
NO_COST = CostConfig(commission_rate=0.0, sell_tax_rate=0.0, slippage_rate=0.0)


def hist(n: int = 5, last: date = date(2024, 3, 1), price: float = 10_000.0) -> list[Bar]:
    """last 일자로 끝나는 n개의 평탄한 일봉."""
    days = [last - timedelta(days=i) for i in range(n)][::-1]
    return [Bar(d, price, price, price, price, 1.0) for d in days]


def make_core(
    strategy=None,
    universe=("A",),
    risk: RiskConfig | None = None,
    costs: CostConfig = NO_COST,
    broker=None,
    store=None,
    **kw,
) -> TradingCore:
    return TradingCore(
        strategy=strategy or ScriptedStrategy(default=BUY_OPEN),
        universe=universe,
        risk=risk or RiskConfig(capital=10_000_000, max_positions=3, position_pct=0.3, cash_reserve_pct=0.0),
        costs=costs,
        broker=broker or ScriptedBroker(),
        store=store or MemoryStore(),
        clock=kw.pop("clock", lambda: datetime(2024, 3, 4, 9, 0, tzinfo=KST)),
        **kw,
    )


def bar(day: date, o: float, c: float | None = None, hi: float | None = None, lo: float | None = None) -> Bar:
    c = o if c is None else c
    return Bar(day, o, max(o, c) if hi is None else hi, min(o, c) if lo is None else lo, c, 1.0)


def run_day(core: TradingCore, day: date, o: float, c: float | None = None, path=(), sym="A"):
    """한 종목에 대해 하루를 진행: 시가 o → path 가격들 → 종가 c.

    지나간 날의 봉을 core._tape 에 쌓아 다음 날의 history 로 넘깁니다
    (실제처럼 '봇이 본 종가'와 '일봉 종가'가 일치하도록).
    """
    tape = core.__dict__.setdefault("_tape", {}).setdefault(sym, hist())
    core.start_day(day, {sym: list(tape)})
    core.on_open({sym: o})
    for p in path:
        core.on_price(sym, p)
    c = o if c is None else c
    core.on_close({sym: c})
    core.end_day({sym: c}, {sym: max([o, c, *path])})
    tape.append(bar(day, o, c, hi=max([o, c, *path]), lo=min([o, c, *path])))


# --------------------------------------------------------------------------- #
# 진입과 포지션 크기
# --------------------------------------------------------------------------- #
def test_open_entry_sizes_position_from_equity_and_costs():
    costs = CostConfig(commission_rate=0.001, sell_tax_rate=0.002, slippage_rate=0.01)
    core = make_core(costs=costs)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    pos = core.positions["A"]
    # 예산 300만원 / (10,000 * 1.01 * 1.001) = 296.7 → 296주
    assert pos.qty == 296
    assert pos.avg_price == 10_000          # ScriptedBroker 는 기준가에 체결
    assert core.cash == pytest.approx(10_000_000 - 296 * 10_000 * 1.001)
    assert core.equity() == pytest.approx(10_000_000 - 296 * 10_000 * 0.001)
    order = core.store.orders()[0]
    assert order["side"] == "buy" and order["filled_qty"] == 296 and order["status"] == "filled"
    assert order["fee"] == pytest.approx(296 * 10_000 * 0.001)


def test_max_order_amount_and_cash_reserve_limit_budget():
    risk = RiskConfig(capital=1_000_000, max_positions=5, position_pct=1.0, cash_reserve_pct=0.1, max_order_amount=500_000)
    core = make_core(risk=risk)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    assert core.positions["A"].qty == 50    # max_order_amount 가 먼저 제한

    risk = RiskConfig(capital=1_000_000, max_positions=5, position_pct=1.0, cash_reserve_pct=0.1)
    core = make_core(risk=risk)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    assert core.positions["A"].qty == 90    # 현금 10% 는 남김


def test_entry_skipped_when_budget_cannot_buy_one_share():
    risk = RiskConfig(capital=100_000, max_positions=3, position_pct=0.3)
    broker = ScriptedBroker()
    core = make_core(risk=risk, broker=broker)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 50_000})
    assert "A" not in core.positions and broker.requests == []


def test_broker_buy_cap_reduces_quantity_and_zero_cap_skips():
    broker = ScriptedBroker()
    broker.buy_cap = 7
    core = make_core(broker=broker)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    assert core.positions["A"].qty == 7

    broker = ScriptedBroker()
    broker.buy_cap = 0
    core = make_core(broker=broker)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    assert core.positions == {} and broker.requests == []


def test_max_positions_and_score_priority():
    plans = {
        "A": EntryRule(EntryKind.OPEN, score=1.0),
        "B": EntryRule(EntryKind.OPEN, score=3.0),
        "C": EntryRule(EntryKind.OPEN, score=2.0),
    }

    class S(ScriptedStrategy):
        def plan(self, history, position):
            return DayPlan(entry=plans[history[-1].volume])   # volume 필드에 종목 표시를 실어 보냄

    risk = RiskConfig(capital=10_000_000, max_positions=2, position_pct=0.3)
    core = make_core(strategy=S(), universe=("A", "B", "C"), risk=risk)
    hs = {s: [Bar(date(2024, 3, 1), 1000, 1000, 1000, 1000, s)] for s in "ABC"}
    core.start_day(D1, hs)
    core.on_open({"A": 1000, "B": 1000, "C": 1000})
    assert set(core.positions) == {"B", "C"}     # 점수 높은 두 종목만


def test_history_never_includes_today_or_future_bars():
    strat = ScriptedStrategy(default=DayPlan())
    core = make_core(strategy=strat)
    h = hist(n=5, last=D1 + timedelta(days=1))   # 오늘(D1)과 내일 봉이 섞여 들어온 상황
    core.start_day(D1, {"A": h})
    assert strat.calls and strat.calls[0][0] == 3   # D1 이전 봉 3개만 전달됨


def test_warmup_and_stale_history_mean_hold():
    strat = ScriptedStrategy(default=BUY_OPEN, warmup=10)
    core = make_core(strategy=strat)
    core.start_day(D1, {"A": hist(n=5)})
    core.on_open({"A": 10_000})
    assert core.positions == {} and strat.calls == []
    assert "일봉 부족" in core.day.symbols["A"].note

    strat = ScriptedStrategy(default=BUY_OPEN)
    core = make_core(strategy=strat)
    core.start_day(D1, {"A": hist(last=date(2024, 1, 2))})   # 두 달 전 데이터
    core.on_open({"A": 10_000})
    assert core.positions == {} and "오래됨" in core.day.symbols["A"].note


def test_strategy_exception_does_not_crash_and_holds():
    def boom(history, position):
        raise RuntimeError("bug")

    core = make_core(strategy=ScriptedStrategy(default=boom))
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    assert core.positions == {}
    assert "전략 오류" in core.day.symbols["A"].note


# --------------------------------------------------------------------------- #
# 청산
# --------------------------------------------------------------------------- #
def test_open_exit_and_realized_pnl_with_costs():
    costs = CostConfig(commission_rate=0.001, sell_tax_rate=0.002, slippage_rate=0.0)
    strat = ScriptedStrategy(default=lambda h, p: SELL_OPEN if p else BUY_OPEN)
    core = make_core(strategy=strat, costs=costs)
    run_day(core, D1, 10_000)
    qty = core.positions["A"].qty
    run_day(core, D2, 11_000)
    assert core.positions == {}
    sell = core.store.orders()[-1]
    amount = qty * 11_000
    expected = amount - amount * 0.001 - amount * 0.002 - qty * 10_000 * 1.001
    assert sell["side"] == "sell" and sell["pnl"] == pytest.approx(expected)
    assert sell["entry_price"] == 10_000 and sell["entry_day"] == D1.isoformat()
    assert core.cash == pytest.approx(10_000_000 + expected)
    assert core.equity() == pytest.approx(core.cash)


def test_no_rebuy_at_open_on_the_day_of_open_exit():
    both = DayPlan(entry=EntryRule(EntryKind.OPEN), exit=ExitRule(ExitKind.OPEN))
    strat = ScriptedStrategy(default=lambda h, p: both if p else BUY_OPEN)
    core = make_core(strategy=strat)
    run_day(core, D1, 10_000)
    run_day(core, D2, 10_000)
    assert core.positions == {}   # 팔고 같은 시가에 되사지 않음


def test_close_exit_sells_same_day_breakout_entry():
    plan = DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=500), exit=ExitRule(ExitKind.CLOSE))
    core = make_core(strategy=ScriptedStrategy(default=plan))
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    assert core.watch_levels("A").breakout == 10_500
    core.on_price("A", 10_400)
    assert core.positions == {}
    core.on_price("A", 10_500)
    assert core.positions["A"].avg_price == 10_500
    core.on_close({"A": 10_800})
    assert core.positions == {}
    core.end_day({"A": 10_800})
    assert core.store.orders()[-1]["pnl"] == pytest.approx(core.store.orders()[0]["filled_qty"] * 300)


def test_breakout_not_chased_beyond_limit_but_taken_when_price_returns():
    plan = DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=500))
    risk = RiskConfig(capital=10_000_000, position_pct=0.3, breakout_max_chase_pct=0.01)
    core = make_core(strategy=ScriptedStrategy(default=plan), risk=risk)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    core.on_price("A", 10_700)            # 목표가 10,500 의 +1% (10,605) 초과 → 추격 안 함
    assert core.positions == {}
    core.on_price("A", 10_600)            # 범위 안으로 돌아오면 매수
    assert core.positions["A"].avg_price == 10_600


def test_breakout_uses_official_open_when_bot_starts_late():
    plan = DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=500))
    core = make_core(strategy=ScriptedStrategy(default=plan))
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_300}, opens={"A": 10_000}, allow_entries=False)
    assert core.watch_levels("A").breakout == 10_500


def test_allow_entries_false_skips_open_buys_but_not_open_sells():
    strat = ScriptedStrategy(default=lambda h, p: SELL_OPEN if p else BUY_OPEN)
    core = make_core(strategy=strat)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000}, allow_entries=False)
    assert core.positions == {}
    # 다음 날 정상 매수, 그다음 날 늦게 켜도 매도는 실행
    core.end_day({"A": 10_000})
    run_day(core, D2, 10_000)
    assert "A" in core.positions
    core.start_day(D3, {"A": hist(last=D2)})
    core.on_open({"A": 10_000}, allow_entries=False)
    assert core.positions == {}


def test_orphan_position_outside_universe_is_sold_at_open():
    store = MemoryStore()
    core = make_core(store=store)
    run_day(core, D1, 10_000)
    assert "A" in core.positions
    core.universe = ("B",)     # 사용자가 종목을 설정에서 뺀 상황
    core.start_day(D2, {"B": hist(last=D1, price=5_000)})
    core.on_open({"A": 10_000, "B": 5_000})
    assert "A" not in core.positions and "B" in core.positions


# --------------------------------------------------------------------------- #
# 손절 / 익절 / 추적손절 / 재진입 금지
# --------------------------------------------------------------------------- #
def risk_cfg(**kw) -> RiskConfig:
    base = dict(capital=10_000_000, max_positions=3, position_pct=0.3, cash_reserve_pct=0.0, daily_loss_limit_pct=0.0)
    base.update(kw)
    return RiskConfig(**base)


def test_stop_loss_intraday_and_cooldown_blocks_reentry():
    core = make_core(risk=risk_cfg(stop_loss_pct=0.05, cooldown_days=2))
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    lv = core.watch_levels("A")
    assert lv.stop == pytest.approx(9_500) and lv.stop_kind == "stop_loss"
    core.on_price("A", 9_600)
    assert "A" in core.positions
    core.on_price("A", 9_500)
    assert core.positions == {}
    assert "손절" in core.store.orders()[-1]["reason"]
    core.on_close({"A": 9_500})
    core.end_day({"A": 9_500})
    core._tape = {"A": hist() + [bar(D1, 10_000, 9_500)]}
    # 다음 2거래일은 재진입 금지, 3거래일째에 재진입
    for day in (D2, D3):
        run_day(core, day, 9_500)
        assert core.positions == {}, day
    run_day(core, D4, 9_500)
    assert "A" in core.positions


def test_gap_down_through_stop_sells_at_open_price():
    core = make_core(risk=risk_cfg(stop_loss_pct=0.05))
    run_day(core, D1, 10_000)
    qty = core.positions["A"].qty
    core.start_day(D2, {"A": hist(last=D1)})
    core.on_open({"A": 9_000})          # 손절가 9,500 아래로 갭하락
    assert core.positions == {}
    sell = core.store.orders()[-1]
    assert sell["price"] == 9_000 and sell["pnl"] == pytest.approx(qty * -1_000)


def test_take_profit():
    core = make_core(risk=risk_cfg(stop_loss_pct=0.05, take_profit_pct=0.10))
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    assert core.watch_levels("A").take_profit == pytest.approx(11_000)
    core.on_price("A", 10_999)
    assert "A" in core.positions
    core.on_price("A", 11_000)
    assert core.positions == {} and "익절" in core.store.orders()[-1]["reason"]


def test_trailing_stop_ratchets_only_after_day_end():
    core = make_core(risk=risk_cfg(stop_loss_pct=0.05, trailing_stop_pct=0.10))
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    core.on_price("A", 12_000)                       # 장중 고가는 당일 손절선에 반영되지 않음
    assert core.watch_levels("A").stop == pytest.approx(9_500)
    core.on_close({"A": 11_500})
    core.end_day({"A": 11_500}, {"A": 12_000})
    assert core.positions["A"].highest_price == 12_000
    core.start_day(D2, {"A": hist() + [bar(D1, 10_000, 11_500, hi=12_000)]})
    core.on_open({"A": 11_500})
    lv = core.watch_levels("A")
    assert lv.stop == pytest.approx(10_800) and lv.stop_kind == "trailing_stop"
    core.on_price("A", 10_800)
    assert core.positions == {} and "추적손절" in core.store.orders()[-1]["reason"]


def test_no_reentry_on_the_day_of_a_risk_exit():
    plan = DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=100))
    core = make_core(strategy=ScriptedStrategy(default=plan), risk=risk_cfg(stop_loss_pct=0.01, cooldown_days=0))
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    core.on_price("A", 10_100)
    assert "A" in core.positions
    core.on_price("A", 9_900)           # 손절
    assert core.positions == {}
    core.on_price("A", 10_100)          # 다시 돌파해도 오늘은 재진입 없음
    assert core.positions == {}
    assert core.watch_levels("A").breakout == 0


# --------------------------------------------------------------------------- #
# 손실 한도 / 긴급 정지
# --------------------------------------------------------------------------- #
def test_daily_loss_limit_halts_new_entries():
    plans = {"A": BUY_OPEN, "B": DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=10))}

    class S(ScriptedStrategy):
        def plan(self, history, position):
            return plans[history[-1].volume]

    risk = risk_cfg(position_pct=0.5, daily_loss_limit_pct=0.02, stop_loss_pct=0.0)
    core = make_core(strategy=S(), universe=("A", "B"), risk=risk)
    hs = {"A": [Bar(date(2024, 3, 1), 10_000, 10_000, 10_000, 10_000, "A")],
          "B": [Bar(date(2024, 3, 1), 1_000, 1_000, 1_000, 1_000, "B")]}
    core.start_day(D1, hs)
    core.on_open({"A": 10_000, "B": 1_000})
    assert "A" in core.positions
    core.on_price("A", 9_500)           # -5% * 50% = 평가금 -2.5% → 한도 초과
    assert core.day.entries_halted
    core.on_price("B", 1_010)           # 돌파했지만 신규 진입 중단
    assert "B" not in core.positions and "A" in core.positions


def test_daily_loss_liquidate_action_sells_everything():
    risk = risk_cfg(position_pct=0.5, daily_loss_limit_pct=0.02, daily_loss_action="liquidate", stop_loss_pct=0.0)
    core = make_core(risk=risk)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    core.on_price("A", 9_500)
    assert core.positions == {} and core.day.entries_halted


def test_max_drawdown_halts_until_resume():
    strat = ScriptedStrategy(default=lambda h, p: SELL_OPEN if p else BUY_OPEN)
    risk = risk_cfg(position_pct=1.0, max_drawdown_pct=0.10, stop_loss_pct=0.0)
    core = make_core(strategy=strat, risk=risk)
    run_day(core, D1, 10_000, c=8_500)          # 평가금 -15%
    assert core.halted
    run_day(core, D2, 8_500)                    # 청산은 수행
    assert core.positions == {}
    run_day(core, D3, 8_500)                    # 신규 진입은 안 함
    assert core.positions == {}
    core.resume()
    run_day(core, D4, 8_500)
    assert "A" in core.positions and not core.halted


def test_drawdown_halt_not_enforced_when_disabled():
    risk = risk_cfg(position_pct=1.0, max_drawdown_pct=0.10, stop_loss_pct=0.0)
    core = make_core(risk=risk, enforce_drawdown_halt=False)
    run_day(core, D1, 10_000, c=8_000)
    assert not core.halted


def test_kill_switch_blocks_everything_then_resumes():
    killed = {"on": True}
    alerts: list[str] = []
    core = make_core(risk=risk_cfg(stop_loss_pct=0.05), kill_switch=lambda: killed["on"], notify=alerts.append)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    assert core.positions == {} and not core.day.opened
    assert sum("긴급 정지" in a for a in alerts) == 1
    killed["on"] = False
    core.on_open({"A": 10_000})
    assert "A" in core.positions
    killed["on"] = True
    core.on_price("A", 9_000)           # 손절 조건이지만 정지 중이라 주문 없음
    assert "A" in core.positions


def test_max_orders_per_day():
    risk = risk_cfg(max_orders_per_day=1, position_pct=0.2, max_positions=3)
    core = make_core(universe=("A", "B"), risk=risk)
    core.start_day(D1, {"A": hist(), "B": hist()})
    core.on_open({"A": 10_000, "B": 10_000})
    assert len(core.positions) == 1


# --------------------------------------------------------------------------- #
# 주문 실패 처리
# --------------------------------------------------------------------------- #
def test_rejected_buy_is_not_retried_same_day():
    broker = ScriptedBroker()
    broker.script = [OrderStatus.REJECTED]
    plan = DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=100))
    core = make_core(strategy=ScriptedStrategy(default=plan), broker=broker)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    core.on_price("A", 10_100)
    core.on_price("A", 10_100)
    assert core.positions == {} and len(broker.requests) == 1
    assert core.cash == 10_000_000
    assert core.store.orders()[0]["status"] == "rejected"


def test_unknown_buy_blocks_symbol_and_alerts():
    broker = ScriptedBroker()
    broker.script = [RuntimeError("timeout")]
    alerts: list[str] = []
    core = make_core(broker=broker, notify=alerts.append)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    assert core.positions == {} and core.day.symbols["A"].entry_blocked
    assert any("확인할 수 없습니다" in a for a in alerts)
    assert core.store.orders()[0]["status"] == "unknown"


def test_partial_buy_fill_books_only_filled_quantity():
    broker = ScriptedBroker()
    broker.script = [lambda req: OrderResult(req, OrderStatus.PARTIAL, 10, 10_010, "X")]
    core = make_core(broker=broker)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    assert core.positions["A"].qty == 10 and core.positions["A"].avg_price == 10_010
    assert core.cash == pytest.approx(10_000_000 - 100_100)


def test_failed_sell_is_retried_then_blocked_with_alert():
    broker = ScriptedBroker()
    alerts: list[str] = []
    core = make_core(risk=risk_cfg(stop_loss_pct=0.05), broker=broker, notify=alerts.append)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    broker.script = [OrderStatus.REJECTED] * MAX_EXIT_RETRIES
    for _ in range(MAX_EXIT_RETRIES + 2):
        core.on_price("A", 9_000)
    assert "A" in core.positions
    assert len(broker.requests) == 1 + MAX_EXIT_RETRIES       # 매수 1 + 매도 재시도 3, 이후 중단
    assert core.day.symbols["A"].exit_blocked
    assert any("직접 확인" in a for a in alerts)
    # 다음 날에는 다시 시도
    core.on_close({"A": 9_000})
    core.end_day({"A": 9_000})
    core.start_day(D2, {"A": hist() + [bar(D1, 10_000, 9_000)]})
    core.on_open({"A": 9_000})
    assert core.positions == {}


def test_partial_sell_keeps_remainder_and_retries_even_if_price_recovers():
    broker = ScriptedBroker()
    core = make_core(risk=risk_cfg(stop_loss_pct=0.05), broker=broker)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    qty = core.positions["A"].qty
    broker.script = [lambda req: OrderResult(req, OrderStatus.PARTIAL, 100, 9_400, "X")]
    core.on_price("A", 9_400)
    assert core.positions["A"].qty == qty - 100
    core.on_price("A", 9_900)           # 손절선 위로 회복했어도 남은 수량 청산을 마무리
    assert core.positions == {}


def test_unknown_sell_blocks_exits_for_the_day():
    broker = ScriptedBroker()
    core = make_core(risk=risk_cfg(stop_loss_pct=0.05), broker=broker)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    broker.script = [OrderStatus.UNKNOWN]
    core.on_price("A", 9_000)
    core.on_price("A", 9_000)
    assert "A" in core.positions and len(broker.requests) == 2
    assert core.watch_levels("A") .any is False
    assert "A" not in core.watched_symbols()


def test_sellable_cap_limits_sell_quantity():
    broker = ScriptedBroker()
    core = make_core(risk=risk_cfg(stop_loss_pct=0.05), broker=broker)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    qty = core.positions["A"].qty
    broker.sell_cap = 5                 # 사용자가 일부를 수동으로 판 상황
    core.on_price("A", 9_000)
    assert broker.requests[-1].side == Side.SELL and broker.requests[-1].qty == 5
    assert core.positions["A"].qty == qty - 5


def test_absurd_fill_quantity_is_treated_as_unknown():
    broker = ScriptedBroker()
    broker.script = [lambda req: OrderResult(req, OrderStatus.FILLED, req.qty * 10, 10_000, "X")]
    core = make_core(broker=broker)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    assert core.store.orders()[0]["status"] == "unknown"
    assert core.day.symbols["A"].entry_blocked


# --------------------------------------------------------------------------- #
# 종가 청산 재시도 / 감시 종목
# --------------------------------------------------------------------------- #
def test_close_exit_can_be_retried_by_calling_on_close_again():
    broker = ScriptedBroker()
    plan = DayPlan(entry=EntryRule(EntryKind.OPEN), exit=ExitRule(ExitKind.CLOSE))
    core = make_core(strategy=ScriptedStrategy(default=plan), broker=broker)
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    broker.script = [OrderStatus.REJECTED]
    core.on_close({"A": 10_100})
    assert "A" in core.positions and core.has_pending_close_exits()
    core.on_close({"A": 10_100})
    assert core.positions == {} and not core.has_pending_close_exits()


def test_watched_symbols_lists_holdings_and_breakout_candidates():
    plans = {"A": BUY_OPEN, "B": DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=10)), "C": DayPlan()}

    class S(ScriptedStrategy):
        def plan(self, history, position):
            return plans[history[-1].volume]

    core = make_core(strategy=S(), universe=("A", "B", "C"))
    hs = {s: [Bar(date(2024, 3, 1), 1000, 1000, 1000, 1000, s)] for s in "ABC"}
    core.start_day(D1, hs)
    assert core.watched_symbols() == []
    core.on_open({"A": 1000, "B": 1000, "C": 1000})
    assert core.watched_symbols() == ["A", "B"]
    core.on_close({"A": 1000, "B": 1000, "C": 1000})
    assert core.watched_symbols() == ["A"]


# --------------------------------------------------------------------------- #
# 저장 / 복구
# --------------------------------------------------------------------------- #
def test_state_survives_restart_and_same_day_restart_does_not_repeat_orders(tmp_path):
    path = tmp_path / "state.db"
    plan = DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=500))
    broker = ScriptedBroker()
    store = SqliteStore(path)
    core = make_core(strategy=ScriptedStrategy(default=BUY_OPEN), broker=broker, store=store,
                     risk=risk_cfg(stop_loss_pct=0.05))
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    qty = core.positions["A"].qty
    cash = core.cash
    store.close()

    # 같은 날 재시작
    broker2 = ScriptedBroker()
    store2 = SqliteStore(path)
    core2 = make_core(strategy=ScriptedStrategy(default=plan), broker=broker2, store=store2,
                      risk=risk_cfg(stop_loss_pct=0.05))
    assert core2.positions["A"].qty == qty and core2.cash == cash
    core2.start_day(D1, {"A": hist()})
    core2.on_open({"A": 10_000})          # 이미 처리된 시가 단계는 반복되지 않음
    assert broker2.requests == []
    assert core2.day.opened and core2.day.symbols["A"].entered
    core2.on_price("A", 9_400)            # 손절은 계속 동작
    assert core2.positions == {}
    assert len(store2.orders()) == 2
    store2.close()


def test_pending_order_is_recovered_after_crash(tmp_path):
    path = tmp_path / "state.db"

    class Crash(BaseException):
        pass

    class CrashingBroker(ScriptedBroker):
        def submit_order(self, req):
            self.requests.append(req)
            raise Crash()                 # 주문 전송 직후 프로세스가 죽은 상황을 흉내

    store = SqliteStore(path)
    core = make_core(broker=CrashingBroker(), store=store)
    core.start_day(D1, {"A": hist()})
    with pytest.raises(Crash):
        core.on_open({"A": 10_000})
    store.close()

    store2 = SqliteStore(path)
    assert store2.load_state()["day"]["pending"]["symbol"] == "A"
    broker2 = ScriptedBroker()
    core2 = make_core(broker=broker2, store=store2)
    req = core2.day.pending
    broker2.recovered = OrderResult(
        request=__import__("autotrader.models", fromlist=["OrderRequest"]).OrderRequest(
            "A", Side.BUY, req["qty"], req["ref_price"], req["reason"], req["client_id"]
        ),
        status=OrderStatus.FILLED, filled_qty=req["qty"], avg_price=10_020, broker_order_id="R1",
    )
    core2.recover_pending()
    assert core2.day.pending is None
    assert core2.positions["A"].qty == req["qty"] and core2.positions["A"].avg_price == 10_020
    store2.close()

    # 브로커가 '그런 주문 없음'이라고 답하면 접수되지 않은 것으로 처리
    store3 = SqliteStore(tmp_path / "s3.db")
    core3 = make_core(broker=CrashingBroker(), store=store3)
    core3.start_day(D1, {"A": hist()})
    with pytest.raises(Crash):
        core3.on_open({"A": 10_000})
    store3.close()
    store4 = SqliteStore(tmp_path / "s3.db")
    core4 = make_core(broker=ScriptedBroker(), store=store4)
    core4.recover_pending()
    assert core4.day.pending is None and core4.positions == {} and core4.cash == 10_000_000
    store4.close()


def test_capital_change_is_applied_as_deposit_or_withdrawal(tmp_path):
    path = tmp_path / "state.db"
    store = SqliteStore(path)
    core = make_core(store=store, risk=risk_cfg(capital=10_000_000))
    run_day(core, D1, 10_000)
    cash = core.cash
    store.close()
    store2 = SqliteStore(path)
    core2 = make_core(store=store2, risk=risk_cfg(capital=12_000_000))
    assert core2.cash == pytest.approx(cash + 2_000_000)
    assert core2.capital_base == 12_000_000
    store2.close()


def test_unfinished_previous_day_is_closed_out_on_next_start():
    core = make_core()
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 10_000})
    core.on_price("A", 10_500)
    # end_day 없이 다음 날로 넘어감 (봇이 장중에 꺼졌던 상황)
    core.start_day(D2, {"A": hist(last=D1)})
    eq = dict((d, e) for d, e, _ in core.store.equity_history())
    assert D1 in eq and eq[D1] == pytest.approx(10_000_000 + core.positions["A"].qty * 500)
    with pytest.raises(ValueError):
        core.start_day(D1, {"A": hist()})


def test_equity_history_and_snapshot():
    core = make_core(name_of=lambda s: f"N{s}")
    run_day(core, D1, 10_000, c=10_500)
    run_day(core, D2, 10_500, c=10_200)
    hist_ = core.store.equity_history()
    assert [d for d, _, _ in hist_] == [D1, D2]
    qty = core.positions["A"].qty
    assert hist_[0][1] == pytest.approx(10_000_000 + qty * 500)
    snap = core.snapshot()
    assert snap["positions"][0]["name"] == "NA" and snap["positions"][0]["qty"] == qty
    assert snap["equity"] == pytest.approx(10_000_000 + qty * 200)
    import json
    json.dumps(snap)   # 직렬화 가능해야 함


# --------------------------------------------------------------------------- #
# 비정상 시세 / 권리 변동 안전장치
# --------------------------------------------------------------------------- #
def test_price_outside_daily_limit_is_ignored_as_bad_tick():
    core = make_core(risk=risk_cfg(stop_loss_pct=0.05))
    run_day(core, D1, 10_000)
    qty = core.positions["A"].qty
    core.start_day(D2, {"A": list(core._tape["A"])})
    core.on_open({"A": 10_000})
    core.on_price("A", 1)               # 시세 오류 (전일 종가 대비 -99.99%)
    assert core.positions["A"].qty == qty
    assert core.price_of("A") == 10_000
    core.on_price("A", 9_400)           # 정상 범위의 하락은 손절
    assert core.positions == {}


def test_bad_open_price_blocks_entry_and_breakout_target():
    plan = DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=500))
    core = make_core(strategy=ScriptedStrategy(default=plan))
    core.start_day(D1, {"A": hist()})
    core.on_open({"A": 100_000})        # 전일 종가 10,000 인데 시가 100,000 → 무시
    assert core.day.symbols["A"].open_price == 0
    core.on_price("A", 10_600, open_price=10_000)   # 이후 정상 시세로 시가 보정
    assert core.positions["A"].avg_price == 10_600


def test_split_adjusted_history_blocks_auto_trading_of_held_symbol():
    alerts: list[str] = []
    strat = ScriptedStrategy(default=lambda h, p: SELL_OPEN if p else BUY_OPEN)
    core = make_core(strategy=strat, risk=risk_cfg(stop_loss_pct=0.05), notify=alerts.append)
    run_day(core, D1, 10_000)
    qty = core.positions["A"].qty
    # 다음 날 아침: 5:1 액면분할로 과거 일봉이 전부 1/5 로 소급 수정되어 내려옴
    split_hist = [Bar(b.date, b.open / 5, b.high / 5, b.low / 5, b.close / 5, b.volume) for b in core._tape["A"]]
    core.start_day(D2, {"A": split_hist})
    core.on_open({"A": 2_000})
    core.on_price("A", 1_900)
    assert core.positions["A"].qty == qty        # 전략 청산도, 손절도 하지 않음
    assert core.day.symbols["A"].exit_blocked and core.day.symbols["A"].entry_blocked
    assert any("액면분할" in a for a in alerts)
    assert len(core.store.orders()) == 1


def test_forget_position_settles_ledger_without_sending_an_order():
    broker = ScriptedBroker()
    core = make_core(broker=broker)
    run_day(core, D1, 10_000)
    qty = core.positions["A"].qty
    assert core.forget_position("A", qty=100, price=11_000, reason="수동 매도")
    assert core.positions["A"].qty == qty - 100
    assert core.cash == pytest.approx(10_000_000 - qty * 10_000 + 100 * 11_000)
    assert core.forget_position("A")                       # 나머지는 마지막 가격(10,000)으로 정리
    assert core.positions == {} and core.cash == pytest.approx(10_000_000 + 100 * 1_000)
    assert len(broker.requests) == 1                       # 매수 주문 1건뿐
    assert [o["message"] for o in core.store.orders()[1:]] == ["장부 조정 (실제 주문 아님)"] * 2
    assert not core.forget_position("A")


def test_snapshot_from_saved_state_matches_live_snapshot(tmp_path):
    from autotrader.core import snapshot_from_state

    store = SqliteStore(tmp_path / "s.db")
    risk = risk_cfg(stop_loss_pct=0.05, take_profit_pct=0.1)
    core = make_core(store=store, risk=risk, name_of=lambda s: f"N{s}")
    run_day(core, D1, 10_000, c=10_300)
    core.start_day(D2, {"A": list(core._tape["A"])})
    core.on_open({"A": 10_300})
    live = core.snapshot()
    store.close()

    ro = SqliteStore(tmp_path / "s.db", read_only=True)
    offline = snapshot_from_state(ro.load_state(), risk=risk, name_of=lambda s: f"N{s}")
    ro.close()
    for key in ("capital", "cash", "equity", "positions", "plans", "day", "day_opened", "halted", "strategy"):
        assert offline[key] == live[key], key
    assert offline["positions"][0]["stop"] == pytest.approx(9_500)


def test_read_only_store_works_with_awkward_paths_and_refuses_writes(tmp_path):
    import sqlite3

    folder = tmp_path / "내 문서 #1 100%" / "auto trader"
    store = SqliteStore(folder / "state.db")
    store.save_state({"cash": 1})
    store.record_equity(D1, 100.0, 50.0)
    store.close()
    ro = SqliteStore(folder / "state.db", read_only=True)
    assert ro.load_state() == {"cash": 1} and ro.equity_history() == [(D1, 100.0, 50.0)]
    with pytest.raises(sqlite3.OperationalError):
        ro.save_state({"cash": 2})
    ro.close()
    with pytest.raises(FileNotFoundError):
        SqliteStore(folder / "missing.db", read_only=True)

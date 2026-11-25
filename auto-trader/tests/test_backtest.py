"""백테스트 드라이버 테스트.

손으로 만든 짧은 일봉에 대해 체결가·현금·평가금을 직접 계산해 두고 결과와 맞춰 봅니다.
기대값은 엔진 코드를 다시 부르지 않고 주석의 산식으로 미리 계산한 숫자입니다.
"""

from __future__ import annotations

import random
import time
from datetime import date, timedelta

import pytest

from autotrader.backtest.engine import BacktestResult, benchmark_curve, run_backtest
from autotrader.config import CostConfig, RiskConfig
from autotrader.models import Bar
from autotrader.strategies.base import HOLD, DayPlan, EntryKind, EntryRule, ExitKind, ExitRule, Strategy

from conftest import ScriptedStrategy

D0 = date(2024, 3, 1)    # 금 — 전략에 넘길 '과거 자료' 1개 (이날은 일봉 부족으로 관망)
D1 = date(2024, 3, 4)    # 월
D2 = date(2024, 3, 5)
D3 = date(2024, 3, 6)
D4 = date(2024, 3, 7)

BUY_OPEN = DayPlan(entry=EntryRule(EntryKind.OPEN, note="t"))
SELL_OPEN = DayPlan(exit=ExitRule(ExitKind.OPEN, note="t"))
DAY_TRADE = DayPlan(entry=EntryRule(EntryKind.OPEN), exit=ExitRule(ExitKind.CLOSE))
BREAKOUT_500 = DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=500))
NO_COST = CostConfig(commission_rate=0.0, sell_tax_rate=0.0, slippage_rate=0.0)
SLIP_ONLY = CostConfig(commission_rate=0.0, sell_tax_rate=0.0, slippage_rate=0.001)


def bar(day: date, o: float, h: float, l: float, c: float) -> Bar:
    return Bar(day, float(o), float(h), float(l), float(c), 1000.0)


def flat(day: date, price: float = 10_000) -> Bar:
    return bar(day, price, price, price, price)


def risk_cfg(**kw) -> RiskConfig:
    """손절·익절·한도를 모두 끈 기본 설정 (테스트마다 필요한 것만 켭니다)."""
    base = dict(
        capital=10_000_000, max_positions=3, position_pct=0.3, cash_reserve_pct=0.0,
        stop_loss_pct=0.0, take_profit_pct=0.0, trailing_stop_pct=0.0, cooldown_days=0,
        daily_loss_limit_pct=0.0, max_drawdown_pct=0.0,
    )
    base.update(kw)
    return RiskConfig(**base)


def run(data, strategy, risk: RiskConfig | None = None, costs: CostConfig = NO_COST, **kw) -> BacktestResult:
    return run_backtest(data=data, strategy=strategy, risk=risk or risk_cfg(), costs=costs, **kw)


def buy_once() -> ScriptedStrategy:
    """과거 일봉이 1개인 날(D1)에만 시가 매수하고 이후에는 아무것도 하지 않는 전략."""
    return ScriptedStrategy(plans={1: BUY_OPEN})


def filled(result: BacktestResult, side: str | None = None) -> list[dict]:
    return [o for o in result.orders if o["filled_qty"] > 0 and (side is None or o["side"] == side)]


# --------------------------------------------------------------------------- #
# 시가 진입/청산과 비용
# --------------------------------------------------------------------------- #
def test_open_entry_and_exit_with_costs_and_slippage():
    costs = CostConfig(commission_rate=0.001, sell_tax_rate=0.002, slippage_rate=0.01)
    data = {"A": [flat(D0), bar(D1, 10_000, 10_200, 9_900, 10_100), bar(D2, 11_000, 11_100, 10_900, 11_000)]}
    strat = ScriptedStrategy(default=lambda h, p: SELL_OPEN if p else BUY_OPEN)
    r = run(data, strat, costs=costs)

    buy, sell = r.orders
    # 매수: 예산 300만 / (10,000 × 1.01 × 1.001 = 10,110.1) = 296.7 → 296주, 체결가 10,000 × 1.01 = 10,100
    assert (buy["day"], buy["symbol"], buy["side"], buy["status"]) == ("2024-03-04", "A", "buy", "filled")
    assert buy["ts"] == "2024-03-04T09:00:00+09:00"
    assert buy["qty"] == buy["filled_qty"] == 296
    assert buy["ref_price"] == 10_000
    assert buy["price"] == pytest.approx(10_100)
    assert buy["amount"] == pytest.approx(2_989_600)            # 296 × 10,100
    assert buy["fee"] == pytest.approx(2_989.6)                 # 0.1%
    assert buy["cash_after"] == pytest.approx(7_007_410.4)      # 1,000만 − 2,989,600 − 2,989.6
    assert buy["pnl"] is None
    # 매도: 체결가 11,000 × 0.99 = 10,890 → 296 × 10,890 = 3,223,440
    assert (sell["day"], sell["side"], sell["status"]) == ("2024-03-05", "sell", "filled")
    assert sell["ts"] == "2024-03-05T09:00:00+09:00"
    assert sell["filled_qty"] == 296
    assert sell["price"] == pytest.approx(10_890)
    assert sell["fee"] == pytest.approx(3_223.44)
    assert sell["tax"] == pytest.approx(6_446.88)
    # 손익 = 3,223,440 − 3,223.44 − 6,446.88 − 2,989,600 − 2,989.6
    assert sell["pnl"] == pytest.approx(221_180.08)
    assert sell["pnl_pct"] == pytest.approx(221_180.08 / 2_992_589.6)
    assert sell["entry_price"] == pytest.approx(10_100) and sell["entry_day"] == "2024-03-04"
    assert sell["cash_after"] == pytest.approx(10_221_180.08)

    assert [d for d, _ in r.equity_curve] == [D0, D1, D2]
    assert [e for _, e in r.equity_curve] == pytest.approx([10_000_000, 9_997_010.4, 10_221_180.08])
    assert [c for _, c in r.cash_curve] == pytest.approx([10_000_000, 7_007_410.4, 10_221_180.08])
    assert r.final_positions == []
    assert (r.start, r.end, r.initial_capital) == (D0, D2, 10_000_000)
    m = r.metrics
    assert (m.num_trades, m.num_wins) == (1, 1)
    assert m.total_fees == pytest.approx(2_989.6 + 3_223.44)
    assert m.total_taxes == pytest.approx(6_446.88)
    assert m.final_equity == pytest.approx(10_221_180.08)
    assert m.exposure == pytest.approx(1 / 3)                   # 3일 중 D1 하루만 주식을 들고 마감


def test_position_still_open_at_the_end_is_reported_at_last_close():
    data = {"A": [flat(D0), bar(D1, 10_000, 10_300, 9_900, 10_200)]}
    r = run(data, buy_once(), names={"A": "가나다전자"})
    (pos,) = r.final_positions
    assert (pos["symbol"], pos["name"], pos["qty"]) == ("A", "가나다전자", 300)
    assert pos["avg_price"] == 10_000 and pos["price"] == 10_200 and pos["entry_date"] == "2024-03-04"
    assert r.equity_curve[-1] == (D1, 10_060_000)               # 700만 + 300 × 10,200
    assert r.cash_curve[-1] == (D1, 7_000_000)
    assert r.metrics.num_trades == 0
    assert r.names == {"A": "가나다전자"}
    assert r.strategy_name == "scripted" and r.strategy_params == {"warmup": 1}
    assert r.symbols == ["A"]


# --------------------------------------------------------------------------- #
# 손절 / 익절 / 추적손절
# --------------------------------------------------------------------------- #
def test_stop_loss_inside_the_bar_fills_at_the_stop_level_minus_slippage():
    data = {"A": [flat(D0), bar(D1, 10_000, 10_100, 9_950, 10_050), bar(D2, 10_000, 10_050, 9_400, 9_800)]}
    r = run(data, buy_once(), risk=risk_cfg(stop_loss_pct=0.05), costs=SLIP_ONLY)
    buy, sell = r.orders
    # 매수 299주 @ 10,010 (300만 / 10,010 = 299.7) → 현금 7,007,010, 손절가 10,010 × 0.95 = 9,509.5
    assert buy["filled_qty"] == 299 and buy["price"] == pytest.approx(10_010)
    assert r.equity_curve[1][1] == pytest.approx(10_011_960)    # 7,007,010 + 299 × 10,050
    # D2: 시가 10,000 은 손절가 위, 저가 9,400 은 아래 → 손절가 9,509.5 에서 슬리피지 0.1% 불리하게
    assert sell["day"] == "2024-03-05" and "손절" in sell["reason"]
    assert sell["ts"] == "2024-03-05T12:00:00+09:00"
    assert sell["ref_price"] == pytest.approx(9_509.5)
    assert sell["price"] == pytest.approx(9_499.9905)
    assert sell["pnl"] == pytest.approx(-152_492.8405)          # 299 × (9,499.9905 − 10,010)
    assert r.equity_curve[2][1] == pytest.approx(9_847_507.1595)
    assert r.final_positions == []


def test_gap_down_through_the_stop_fills_at_the_open_not_at_the_stop():
    data = {"A": [flat(D0), bar(D1, 10_000, 10_100, 9_950, 10_050), bar(D2, 9_000, 9_200, 8_900, 9_100)]}
    r = run(data, buy_once(), risk=risk_cfg(stop_loss_pct=0.05), costs=SLIP_ONLY)
    buy, sell = r.orders
    assert sell["ts"] == "2024-03-05T09:00:00+09:00"            # 장 시작 단계에서 처리
    assert sell["ref_price"] == 9_000
    assert sell["price"] == pytest.approx(8_991)                # 9,000 × 0.999
    assert r.equity_curve[2][1] == pytest.approx(9_695_319)     # 7,007,010 + 299 × 8,991


def test_stop_is_assumed_first_when_stop_and_take_profit_are_both_in_range():
    risk = risk_cfg(stop_loss_pct=0.05, take_profit_pct=0.05)   # 손절가 9,500 / 익절가 10,500
    data = {"A": [flat(D0), flat(D1), bar(D2, 10_000, 10_600, 9_400, 10_500)]}
    r = run(data, buy_once(), risk=risk)
    buy, sell = r.orders
    assert "손절" in sell["reason"] and sell["price"] == pytest.approx(9_500)
    assert sell["pnl"] == pytest.approx(-150_000)               # 300주 × −500
    assert r.equity_curve[-1][1] == pytest.approx(9_850_000)


def test_take_profit_inside_the_bar_and_gap_up_through_take_profit():
    risk = risk_cfg(stop_loss_pct=0.05, take_profit_pct=0.05)
    inside = {"A": [flat(D0), flat(D1), bar(D2, 10_000, 10_600, 9_600, 10_550)]}
    r = run(inside, buy_once(), risk=risk)
    sell = r.orders[-1]
    assert "익절" in sell["reason"] and sell["price"] == pytest.approx(10_500)
    assert sell["ts"] == "2024-03-05T12:00:00+09:00"
    assert sell["pnl"] == pytest.approx(150_000)

    gap = {"A": [flat(D0), flat(D1), bar(D2, 10_700, 10_800, 10_600, 10_700)]}
    r = run(gap, buy_once(), risk=risk)
    sell = r.orders[-1]
    assert "익절" in sell["reason"] and sell["price"] == pytest.approx(10_700)   # 익절가가 아니라 시가
    assert sell["ts"] == "2024-03-05T09:00:00+09:00"
    assert len(r.orders) == 2


def test_levels_just_outside_the_bar_do_not_trigger():
    risk = risk_cfg(stop_loss_pct=0.05, take_profit_pct=0.05)
    data = {"A": [flat(D0), flat(D1), bar(D2, 10_000, 10_499, 9_501, 10_000)]}
    r = run(data, buy_once(), risk=risk)
    assert len(r.orders) == 1 and len(r.final_positions) == 1


def test_trailing_stop_follows_the_previous_days_high():
    risk = risk_cfg(stop_loss_pct=0.05, trailing_stop_pct=0.10)
    data = {"A": [flat(D0), bar(D1, 10_000, 12_000, 9_900, 11_500), bar(D2, 11_500, 11_600, 10_700, 11_000)]}
    r = run(data, buy_once(), risk=risk)
    buy, sell = r.orders
    # D1 고가 12,000 → D2 추적손절가 12,000 × 0.9 = 10,800 (고정 손절가 9,500 보다 높음)
    assert sell["day"] == "2024-03-05" and "추적손절" in sell["reason"]
    assert sell["price"] == pytest.approx(10_800)
    assert sell["pnl"] == pytest.approx(240_000)                # 300주 × 800


def test_stop_tighter_than_slippage_never_fills_above_the_days_range():
    # 손절폭(0.05%)이 슬리피지(0.1%)보다 작으면 손절가(10,004.995)가 시가(10,000)·고가보다 높아집니다.
    # 가격이 올라가서 손절될 수는 없으므로 방금 체결된 가격(시가)에 바로 팔린 것으로 봐야 합니다.
    data = {"A": [flat(D0), bar(D1, 10_000, 10_000, 9_990, 9_995)]}
    r = run(data, buy_once(), risk=risk_cfg(stop_loss_pct=0.0005), costs=SLIP_ONLY)
    buy, sell = r.orders
    assert buy["price"] == pytest.approx(10_010)
    assert sell["ref_price"] == 10_000
    assert sell["price"] == pytest.approx(9_990)                # 10,000 × 0.999


# --------------------------------------------------------------------------- #
# 돌파 진입
# --------------------------------------------------------------------------- #
def breakout_once() -> ScriptedStrategy:
    return ScriptedStrategy(plans={1: BREAKOUT_500})


def test_breakout_entry_fills_at_open_plus_offset():
    data = {"A": [flat(D0), bar(D1, 10_000, 10_600, 9_950, 10_550)]}
    r = run(data, breakout_once(), costs=SLIP_ONLY)
    (buy,) = r.orders
    # 목표가 10,500 → 체결가 10,500 × 1.001 = 10,510.5, 300만 / 10,510.5 = 285.4 → 285주
    assert buy["ts"] == "2024-03-04T12:00:00+09:00" and "돌파 매수" in buy["reason"]
    assert buy["ref_price"] == pytest.approx(10_500)
    assert buy["price"] == pytest.approx(10_510.5)
    assert buy["filled_qty"] == 285
    assert r.cash_curve[-1][1] == pytest.approx(7_004_507.5)    # 1,000만 − 285 × 10,510.5
    assert r.equity_curve[-1][1] == pytest.approx(10_011_257.5)  # + 285 × 10,550


def test_breakout_needs_the_high_to_reach_the_target():
    below = {"A": [flat(D0), bar(D1, 10_000, 10_499, 9_950, 10_400)]}
    assert run(below, breakout_once()).orders == []
    touch = {"A": [flat(D0), bar(D1, 10_000, 10_500, 9_950, 10_400)]}
    assert len(run(touch, breakout_once()).orders) == 1


def test_same_day_take_profit_after_breakout_is_exact():
    data = {"A": [flat(D0), bar(D1, 10_000, 10_800, 9_990, 10_750)]}
    r = run(data, breakout_once(), risk=risk_cfg(take_profit_pct=0.02))
    buy, sell = r.orders
    # 285주 @ 10,500 → 익절가 10,710. 고가 10,800 이므로 매수 뒤에 익절가에 닿은 것이 확실합니다.
    assert buy["filled_qty"] == 285 and buy["price"] == pytest.approx(10_500)
    assert sell["day"] == "2024-03-04" and "익절" in sell["reason"]
    assert sell["price"] == pytest.approx(10_710)
    assert sell["pnl"] == pytest.approx(59_850)                 # 285 × 210
    assert r.equity_curve[-1][1] == pytest.approx(10_059_850)


def test_same_day_stop_after_breakout_uses_the_worst_case():
    # 저가 9,950 은 돌파 전에 찍혔을 수도 있지만, 일봉으로는 알 수 없으므로 당일 손절로 처리합니다.
    data = {"A": [flat(D0), bar(D1, 10_000, 10_600, 9_950, 10_550)]}
    r = run(data, breakout_once(), risk=risk_cfg(stop_loss_pct=0.02))
    buy, sell = r.orders
    assert sell["day"] == "2024-03-04" and "손절" in sell["reason"]
    assert sell["price"] == pytest.approx(10_290)               # 10,500 × 0.98
    assert sell["pnl"] == pytest.approx(-59_850)
    assert r.final_positions == []                              # 같은 날 다시 사지 않음

    # 손절가(10,290)가 시가(10,000)보다 높으면 저가는 항상 손절가 이하입니다. 시가에서 한 번도
    # 밀리지 않고 고가로 마감한 날조차 당일 손절로 처리됩니다 (최악 가정의 귀결 — 문서화된 한계).
    straight_up = {"A": [flat(D0), bar(D1, 10_000, 10_600, 10_000, 10_600)]}
    r = run(straight_up, breakout_once(), risk=risk_cfg(stop_loss_pct=0.02))
    assert [o["side"] for o in r.orders] == ["buy", "sell"] and "손절" in r.orders[-1]["reason"]

    # 손절가가 그날 저가보다 낮으면 손절되지 않고 보유한 채 마감합니다 (6% → 손절가 9,870).
    safe = {"A": [flat(D0), bar(D1, 10_000, 10_600, 9_900, 10_550)]}
    r = run(safe, breakout_once(), risk=risk_cfg(stop_loss_pct=0.06))
    assert len(r.orders) == 1 and len(r.final_positions) == 1


def test_same_day_stop_wins_over_take_profit_after_breakout():
    data = {"A": [flat(D0), bar(D1, 10_000, 10_900, 9_950, 10_800)]}
    r = run(data, breakout_once(), risk=risk_cfg(stop_loss_pct=0.02, take_profit_pct=0.02))
    buy, sell = r.orders
    assert "손절" in sell["reason"] and sell["price"] == pytest.approx(10_290)


def test_breakout_with_close_exit_sells_at_the_close_of_the_entry_day():
    plan = DayPlan(entry=EntryRule(EntryKind.BREAKOUT, offset=500), exit=ExitRule(ExitKind.CLOSE))
    data = {"A": [flat(D0), bar(D1, 10_000, 10_600, 9_950, 10_550)]}
    r = run(data, ScriptedStrategy(plans={1: plan}))
    buy, sell = r.orders
    assert sell["ts"] == "2024-03-04T15:20:00+09:00" and "종가 청산" in sell["reason"]
    assert sell["price"] == 10_550 and sell["pnl"] == pytest.approx(14_250)   # 285 × 50


# --------------------------------------------------------------------------- #
# 종가 청산 (당일 매매)
# --------------------------------------------------------------------------- #
def test_close_exit_on_the_entry_day():
    data = {"A": [flat(D0), bar(D1, 10_000, 10_300, 9_900, 10_200), bar(D2, 10_200, 10_400, 10_000, 10_100)]}
    r = run(data, ScriptedStrategy(default=DAY_TRADE))
    assert [(o["day"], o["side"], o["filled_qty"], o["price"]) for o in r.orders] == [
        ("2024-03-04", "buy", 300, 10_000),      # 300만 / 10,000
        ("2024-03-04", "sell", 300, 10_200),
        ("2024-03-05", "buy", 295, 10_200),      # 1,006만 × 0.3 = 3,018,000 / 10,200 = 295.9
        ("2024-03-05", "sell", 295, 10_100),
    ]
    assert [o["ts"][11:16] for o in r.orders] == ["09:00", "15:20", "09:00", "15:20"]
    assert [e for _, e in r.equity_curve] == pytest.approx([10_000_000, 10_060_000, 10_030_500])
    assert r.metrics.exposure == 0.0                            # 장 마감 때는 항상 현금뿐
    assert r.metrics.avg_holding_days == 0.0


# --------------------------------------------------------------------------- #
# 기간과 워밍업
# --------------------------------------------------------------------------- #
class Spy(Strategy):
    """전략이 받은 과거 자료의 (개수, 마지막 날짜)를 기록합니다."""

    name = "spy"
    DEFAULTS = {"warmup": 1}

    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.seen: list[tuple[int, date]] = []

    @property
    def warmup(self) -> int:
        return int(self.params["warmup"])

    def plan(self, history, position):
        self.seen.append((len(history), history[-1].date))
        return BUY_OPEN


def weekdays(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_bars_before_start_are_history_only_and_are_not_traded():
    days = weekdays(date(2024, 2, 26), 8)                       # 2/26(월) ~ 3/6(수)
    data = {"A": [flat(d) for d in days]}
    spy = Spy()
    r = run(data, spy, start=D1, end=D2)
    assert [d for d, _ in r.equity_curve] == [D1, D2]
    assert (r.start, r.end, r.metrics.trading_days) == (D1, D2, 2)
    assert spy.seen == [(5, D0), (6, D1)]                       # 시작일 이전 5개 봉이 과거 자료로 전달됨
    assert [o["day"] for o in r.orders] == ["2024-03-04"]       # 첫 매매는 시작일
    assert [d for d, _ in r.benchmark_curve] == [D1, D2]


def test_strategy_only_ever_sees_bars_strictly_before_today():
    days = weekdays(D1, 6)
    data = {"A": [bar(d, 10_000 + i, 10_100 + i, 9_900 + i, 10_050 + i) for i, d in enumerate(days)]}
    spy = Spy()
    run(data, spy)
    # 첫날은 과거 자료가 없어 호출되지 않고, i번째 날에는 i-1번째 날까지만 보입니다.
    assert spy.seen == [(i, days[i - 1]) for i in range(1, 6)]


def test_no_trading_until_the_strategy_has_enough_history():
    days = weekdays(D1, 5)
    data = {"A": [flat(d) for d in days]}
    r = run(data, ScriptedStrategy(default=BUY_OPEN, warmup=3))
    assert [o["day"] for o in r.orders] == [days[3].isoformat()]
    assert len(r.equity_curve) == 5


def test_universe_selects_and_orders_symbols():
    data = {s: [flat(D0), flat(D1), flat(D2)] for s in ("A", "B", "C")}
    r = run(data, ScriptedStrategy(default=DAY_TRADE), universe=["C", "A"])
    assert r.symbols == ["C", "A"]
    assert {o["symbol"] for o in r.orders} == {"C", "A"}
    assert [o["symbol"] for o in r.orders[:2]] == ["C", "A"]    # 점수가 같으면 universe 순서대로 매수


# --------------------------------------------------------------------------- #
# 거래가 없는 날 (거래정지 / 데이터 누락)
# --------------------------------------------------------------------------- #
def test_symbol_without_a_bar_is_not_traded_that_day_while_others_are():
    data = {
        "A": [flat(D0), flat(D1), flat(D2), flat(D3)],
        "B": [flat(D0, 5_000), flat(D1, 5_000), flat(D3, 5_000)],     # D2 거래정지
    }
    r = run(data, ScriptedStrategy(default=DAY_TRADE))
    traded = sorted({(o["day"], o["symbol"]) for o in r.orders})
    assert traded == [
        ("2024-03-04", "A"), ("2024-03-04", "B"),
        ("2024-03-05", "A"),
        ("2024-03-06", "A"), ("2024-03-06", "B"),
    ]
    assert [d for d, _ in r.equity_curve] == [D0, D1, D2, D3]
    assert all(o["status"] == "filled" for o in r.orders)


def test_held_symbol_without_a_bar_is_valued_at_its_last_close():
    data = {
        "A": [flat(D0), flat(D1), flat(D2), flat(D3)],
        "B": [flat(D0, 5_000), bar(D1, 5_000, 5_200, 4_900, 5_100), bar(D3, 5_300, 5_400, 5_200, 5_300)],
    }

    class OnlyB(ScriptedStrategy):
        def plan(self, history, position):
            return BUY_OPEN if history[0].close == 5_000 and len(history) == 1 else HOLD

    r = run(data, OnlyB())
    (buy,) = r.orders
    assert (buy["symbol"], buy["filled_qty"]) == ("B", 600)     # 300만 / 5,000
    equity = [e for _, e in r.equity_curve]
    # D1 종가 5,100 → D2 는 일봉이 없어 5,100 그대로 → D3 종가 5,300
    assert equity == pytest.approx([10_000_000, 10_060_000, 10_060_000, 10_180_000])


def test_daily_loss_liquidation_cannot_sell_a_suspended_symbol_at_a_stale_price():
    risk = risk_cfg(position_pct=0.5, max_positions=2, daily_loss_limit_pct=0.02, daily_loss_action="liquidate")
    data = {
        "A": [flat(D0), flat(D1), bar(D2, 9_000, 9_100, 8_900, 9_000), flat(D3, 9_000)],
        "B": [flat(D0, 5_000), flat(D1, 5_000), flat(D3, 4_000)],     # D2 거래정지, D3 에 −20% 로 재개
    }
    r = run(data, buy_once(), risk=risk)
    b_orders = [(o["day"], o["side"], o["status"], o["filled_qty"], o["price"]) for o in r.orders if o["symbol"] == "B"]
    assert b_orders == [
        ("2024-03-04", "buy", "filled", 1000, 5_000),
        ("2024-03-05", "sell", "rejected", 0, 0.0),      # 거래정지 중에는 팔 수 없음
        ("2024-03-06", "sell", "filled", 1000, 4_000),   # 재개된 날의 실제 가격에 청산
    ]
    rejected = next(o for o in r.orders if o["status"] == "rejected")
    assert "거래가 없는 종목" in rejected["message"]
    a_sell = next(o for o in r.orders if o["symbol"] == "A" and o["side"] == "sell")
    assert (a_sell["day"], a_sell["price"]) == ("2024-03-05", 9_000)
    # D2: A 500주를 9,000 에 청산(450만) + B 1,000주는 5,000 으로 평가만 / D3: B 를 4,000 에 청산
    assert [e for _, e in r.equity_curve] == pytest.approx([10_000_000, 10_000_000, 9_500_000, 8_500_000])
    assert r.metrics.num_trades == 2                           # 거부된 주문은 거래로 세지 않음


# --------------------------------------------------------------------------- #
# 입력 검증
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bars, fragment",
    [
        ([flat(D1), flat(D1)], "2024-03-04"),                                   # 날짜 중복
        ([flat(D2), flat(D1)], "순서"),                                          # 날짜 역순
        ([flat(D0), bar(D1, 0, 10, 0, 5)], "0보다 큰"),                          # 0원
        ([flat(D0), bar(D1, -1, 10, -1, 5)], "0보다 큰"),                        # 음수
        ([flat(D0), bar(D1, 100, float("nan"), 90, 95)], "0보다 큰"),            # 숫자가 아님
        ([flat(D0), bar(D1, 100, float("inf"), 90, 95)], "0보다 큰"),            # 무한대
        ([flat(D0), bar(D1, 100, 110, 101, 105)], "저가"),                       # 저가 > 시가
        ([flat(D0), bar(D1, 100, 110, 96, 95)], "저가"),                         # 저가 > 종가
        ([flat(D0), bar(D1, 100, 104, 90, 105)], "고가"),                        # 고가 < 종가
        ([flat(D0), bar(D1, 100, 99, 90, 95)], "고가"),                          # 고가 < 시가
    ],
)
def test_invalid_bars_are_rejected_with_symbol_and_date(bars, fragment):
    with pytest.raises(ValueError) as err:
        run({"005930": bars}, buy_once())
    message = str(err.value)
    assert "005930" in message and "2024-03-0" in message and fragment in message


def test_tiny_float_noise_in_ohlc_is_tolerated():
    noisy = bar(D1, 10_000, 10_000, 10_000 * (1 + 1e-12), 10_000)
    assert len(run({"A": [flat(D0), noisy]}, buy_once()).orders) == 1


def test_invalid_universe_and_period_are_rejected():
    ok = [flat(D0), flat(D1)]
    with pytest.raises(ValueError, match="종목이 없습니다"):
        run({}, buy_once())
    with pytest.raises(ValueError, match="B.*일봉 데이터가 없습니다"):
        run({"A": ok}, buy_once(), universe=["A", "B"])
    with pytest.raises(ValueError, match="B.*일봉 데이터가 없습니다"):
        run({"A": ok, "B": []}, buy_once())
    with pytest.raises(ValueError, match="중복.*A"):
        run({"A": ok}, buy_once(), universe=["A", "A"])
    with pytest.raises(ValueError, match="시작일.*종료일"):
        run({"A": ok}, buy_once(), start=D2, end=D1)
    with pytest.raises(ValueError, match="해당하는 일봉이 없습니다.*2024-03-01 ~ 2024-03-04"):
        run({"A": ok}, buy_once(), start=date(2025, 1, 1))
    with pytest.raises(ValueError, match="capital"):
        run({"A": ok}, buy_once(), risk=risk_cfg(capital=0))
    with pytest.raises(ValueError, match="slippage_rate"):
        run({"A": ok}, buy_once(), costs=CostConfig(slippage_rate=-0.1))


def test_bars_outside_the_universe_are_not_validated_or_traded():
    data = {"A": [flat(D0), flat(D1)], "BROKEN": [flat(D1), flat(D0)]}
    r = run(data, buy_once(), universe=["A"])
    assert r.symbols == ["A"]


# --------------------------------------------------------------------------- #
# 벤치마크 (동일 비중 단순보유)
# --------------------------------------------------------------------------- #
def test_benchmark_is_equal_weight_buy_and_hold():
    data = {
        "A": [flat(D1, 100), flat(D2, 110), flat(D3, 121)],                 # D4 는 일봉 없음 → 직전 값 유지
        "B": [flat(D2, 50), flat(D3, 40), flat(D4, 45)],                    # D2 에 처음 등장 → 그 전은 1.0배
    }
    curve = benchmark_curve(data, ["A", "B"], [D1, D2, D3, D4], 10_000_000)
    assert [d for d, _ in curve] == [D1, D2, D3, D4]
    assert [v for _, v in curve] == pytest.approx([
        10_000_000,      # A 1.00, B 1.00
        10_500_000,      # A 1.10, B 1.00 (첫 종가가 기준)
        10_050_000,      # A 1.21, B 0.80
        10_550_000,      # A 1.21(유지), B 0.90
    ])
    r = run(data, ScriptedStrategy(default=HOLD))
    assert r.benchmark_curve == curve
    assert r.metrics.benchmark_return == pytest.approx(0.055)
    assert r.metrics.benchmark_max_drawdown == pytest.approx(10_050_000 / 10_500_000 - 1)


def test_benchmark_base_is_the_first_close_on_or_after_start():
    data = {"A": [flat(D0, 50), flat(D1, 100), flat(D2, 150)]}
    r = run(data, ScriptedStrategy(default=HOLD), start=D1)
    assert [v for _, v in r.benchmark_curve] == pytest.approx([10_000_000, 15_000_000])   # D0 의 50 은 기준이 아님


# --------------------------------------------------------------------------- #
# 무작위 데이터로 확인하는 성질
# --------------------------------------------------------------------------- #
class SmaCross(Strategy):
    """단기 평균이 장기 평균 위면 시가 매수, 아래면 시가 매도."""

    name = "test_sma_cross"
    DEFAULTS = {"fast": 3, "slow": 8}

    @property
    def warmup(self) -> int:
        return int(self.params["slow"])

    def plan(self, history, position):
        fast_n, slow_n = int(self.params["fast"]), int(self.params["slow"])
        closes = [b.close for b in history[-slow_n:]]
        fast, slow = sum(closes[-fast_n:]) / fast_n, sum(closes) / slow_n
        if position is None:
            return DayPlan(entry=EntryRule(EntryKind.OPEN, score=fast / slow)) if fast > slow else HOLD
        return SELL_OPEN if fast < slow else HOLD


class RangeBreakout(Strategy):
    """전일 변동폭의 k배만큼 시가보다 오르면 매수하고, 다음 날 시가에 매도 (같은 날 재돌파 시 재매수)."""

    name = "test_range_breakout"
    DEFAULTS = {"k": 0.4}

    @property
    def warmup(self) -> int:
        return 2

    def plan(self, history, position):
        prev = history[-1]
        width = prev.high - prev.low
        entry = EntryRule(EntryKind.BREAKOUT, offset=width * self.params["k"], score=width / prev.close) if width > 0 else None
        exit_ = ExitRule(ExitKind.OPEN) if position is not None else None
        return DayPlan(entry=entry, exit=exit_)


def random_walk(seed: int, days: list[date], price: float = 10_000.0, skip: frozenset[int] = frozenset()) -> list[Bar]:
    """seed 로 고정된 무작위 일봉. skip 에 든 순번의 날은 거래정지(일봉 없음)."""
    rng = random.Random(seed)
    bars: list[Bar] = []
    for i, d in enumerate(days):
        o = price * (1 + rng.gauss(0, 0.008))
        c = o * (1 + rng.gauss(0.0002, 0.02))
        h = max(o, c) * (1 + abs(rng.gauss(0, 0.008)))
        l = min(o, c) * (1 - abs(rng.gauss(0, 0.008)))
        price = c
        if i not in skip:
            bars.append(Bar(d, o, h, l, c, 1000.0))
    return bars


def random_market(n_days: int = 260) -> tuple[list[date], dict[str, list[Bar]]]:
    days = weekdays(date(2022, 1, 3), n_days)
    data = {
        "AAA": random_walk(1, days),
        "BBB": random_walk(2, days, price=52_000.0, skip=frozenset(range(100, 104)) | {180}),
        "CCC": random_walk(3, days, price=3_300.0)[40:],        # 늦게 상장된 종목
        "DDD": random_walk(4, days, price=128_000.0),
    }
    return days, data


PROPERTY_RISK = dict(
    capital=10_000_000, max_positions=2, position_pct=0.45, cash_reserve_pct=0.01,
    stop_loss_pct=0.03, take_profit_pct=0.06, trailing_stop_pct=0.05, cooldown_days=2,
    daily_loss_limit_pct=0.03, max_drawdown_pct=0.2,
)
PROPERTY_CASES = [
    pytest.param(SmaCross, {}, id="sma_cross"),
    pytest.param(RangeBreakout, {}, id="range_breakout"),
    pytest.param(RangeBreakout, {"daily_loss_action": "liquidate", "daily_loss_limit_pct": 0.01}, id="breakout_liquidate"),
]


@pytest.mark.parametrize("strategy_cls, risk_overrides", PROPERTY_CASES)
def test_no_look_ahead_truncating_the_future_never_changes_the_past(strategy_cls, risk_overrides):
    days, data = random_market()
    risk = RiskConfig(**{**PROPERTY_RISK, **risk_overrides})
    costs = CostConfig()
    full = run_backtest(data=data, strategy=strategy_cls(), risk=risk, costs=costs)
    assert len(filled(full, "sell")) >= 20, "성질을 확인하기에 거래가 너무 적습니다"
    assert any("손절" in o["reason"] for o in full.orders) and any("익절" in o["reason"] for o in full.orders)

    for n in (0, 9, 41, 77, 102, 133, 180, 201, len(days) - 2, len(days) - 1):
        cut = days[n]
        truncated = {sym: [b for b in bars if b.date <= cut] for sym, bars in data.items()}
        truncated = {sym: bars for sym, bars in truncated.items() if bars}   # 아직 상장 전인 종목은 뺌
        part = run_backtest(data=truncated, strategy=strategy_cls(), risk=risk, costs=costs)
        assert part.orders == [o for o in full.orders if o["day"] <= cut.isoformat()], cut
        assert part.equity_curve == full.equity_curve[: n + 1], cut
        assert part.cash_curve == full.cash_curve[: n + 1], cut
        if set(truncated) == set(data):     # 종목 구성이 같을 때만 벤치마크(동일 비중)도 같아야 함
            assert part.benchmark_curve == full.benchmark_curve[: n + 1], cut


@pytest.mark.parametrize("strategy_cls, risk_overrides", PROPERTY_CASES)
def test_every_fill_is_inside_that_days_bar_and_the_ledger_adds_up(strategy_cls, risk_overrides):
    days, data = random_market()
    risk = RiskConfig(**{**PROPERTY_RISK, **risk_overrides})
    costs = CostConfig()
    r = run_backtest(data=data, strategy=strategy_cls(), risk=risk, costs=costs)
    bars = {(sym, b.date.isoformat()): b for sym, series in data.items() for b in series}

    for o in r.orders:
        b = bars.get((o["symbol"], o["day"]))
        if o["filled_qty"] == 0:
            assert b is None and o["status"] == "rejected"      # 체결되지 않은 주문은 거래정지 종목뿐
            continue
        assert b is not None, "일봉이 없는 날에 체결된 주문"
        assert b.low * (1 - 1e-12) <= o["ref_price"] <= b.high * (1 + 1e-12), o
        slip = costs.slippage_rate if o["side"] == "buy" else -costs.slippage_rate
        assert o["price"] == pytest.approx(o["ref_price"] * (1 + slip))

    # 장부 검산 1: 마지막 평가금 = 현금 + 보유 수량 × 마지막 종가
    last_close = {sym: series[-1].close for sym, series in data.items()}
    held_value = sum(p["qty"] * last_close[p["symbol"]] for p in r.final_positions)
    assert r.equity_curve[-1][1] == pytest.approx(r.cash_curve[-1][1] + held_value)
    assert r.orders[-1]["cash_after"] == pytest.approx(r.cash_curve[-1][1])
    # 장부 검산 2: 총손익 = 실현손익 합계 + 보유분 평가손익 − 보유분 매수 수수료
    realized = sum(o["pnl"] for o in filled(r, "sell"))
    unrealized = sum(
        p["qty"] * (last_close[p["symbol"]] - p["avg_price"]) - p["qty"] * p["avg_price"] * costs.commission_rate
        for p in r.final_positions
    )
    assert r.equity_curve[-1][1] - r.initial_capital == pytest.approx(realized + unrealized)
    assert all(cash >= -1e-6 for _, cash in r.cash_curve)       # 현금이 마이너스가 되는 일은 없음
    assert len(r.equity_curve) == len(days) and [d for d, _ in r.equity_curve] == days


def test_two_runs_give_identical_results():
    _, data = random_market(150)
    risk = RiskConfig(**PROPERTY_RISK)
    a = run_backtest(data=data, strategy=RangeBreakout(), risk=risk, costs=CostConfig())
    b = run_backtest(data=data, strategy=RangeBreakout(), risk=risk, costs=CostConfig())
    assert a == b
    assert a.orders and a.orders[0]["ts"].endswith("+09:00")    # 실제 시계가 아니라 가상 시각(KST)


def test_input_data_is_not_modified():
    _, data = random_market(60)
    before = {sym: list(bars) for sym, bars in data.items()}
    run_backtest(data=data, strategy=SmaCross(), risk=RiskConfig(**PROPERTY_RISK), costs=CostConfig())
    assert data == before


# --------------------------------------------------------------------------- #
# 진행률 / 속도
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("n_days, expected_calls", [(1, 1), (7, 7), (100, 100), (101, 51), (250, 84), (1234, 95)])
def test_progress_is_reported_at_most_about_100_times(n_days, expected_calls):
    data = {"A": [flat(d) for d in weekdays(D1, n_days)]}
    calls: list[tuple[int, int]] = []
    run(data, ScriptedStrategy(default=HOLD), progress=lambda done, total: calls.append((done, total)))
    assert len(calls) == expected_calls <= 100
    assert calls[-1] == (n_days, n_days)                        # 마지막 호출은 항상 100%
    assert all(total == n_days for _, total in calls)
    assert [done for done, _ in calls] == sorted({done for done, _ in calls})   # 단조 증가, 중복 없음


def test_ten_symbols_over_1500_days_run_quickly():
    days = weekdays(date(2018, 1, 2), 1500)
    data = {f"S{i:02d}": random_walk(100 + i, days) for i in range(10)}
    started = time.perf_counter()
    r = run_backtest(data=data, strategy=SmaCross(), risk=RiskConfig(), costs=CostConfig())
    elapsed = time.perf_counter() - started
    assert len(r.equity_curve) == 1500 and r.metrics.num_trades > 50
    assert elapsed < 5.0, f"백테스트가 너무 느립니다: {elapsed:.2f}초"

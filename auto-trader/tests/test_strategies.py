"""전략 단위 테스트 — 전략별 분기, 파라미터 검증, 레지스트리, 결정성(백테스트 = 실전), 코어 연동."""

from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Sequence

import pytest

from autotrader.brokers.paper import PaperBroker
from autotrader.config import CostConfig, RiskConfig, StrategyConfig
from autotrader.core import SymbolDay, TradingCore
from autotrader.models import KST, Bar, Position
from autotrader.state import MemoryStore
from autotrader.strategies import STRATEGIES, available_strategies, create_strategy
from autotrader.strategies.base import HOLD, DayPlan, EntryKind, EntryRule, ExitKind, ExitRule, Strategy
from autotrader.strategies.bollinger_reversion import BollingerReversion
from autotrader.strategies.donchian_breakout import DonchianBreakout
from autotrader.strategies.momentum import Momentum
from autotrader.strategies.rsi_reversion import RsiReversion
from autotrader.strategies.sma_cross import SmaCross
from autotrader.strategies.volatility_breakout import VolatilityBreakout

ALL_NAMES = ["volatility_breakout", "sma_cross", "donchian_breakout", "momentum", "rsi_reversion", "bollinger_reversion"]


# --------------------------------------------------------------------------- #
# 도우미
# --------------------------------------------------------------------------- #
def trading_days(count: int, start: date = date(2023, 1, 2)) -> list[date]:
    """start 부터 평일만 count 개."""
    days: list[date] = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def candles(
    closes: Sequence[float],
    highs: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
) -> list[Bar]:
    """종가 목록으로 일봉을 만듭니다. 고가/저가를 주지 않으면 종가와 같게 둡니다 (시가 = 종가)."""
    highs = closes if highs is None else highs
    lows = closes if lows is None else lows
    assert len(highs) == len(lows) == len(closes)
    return [
        Bar(day, float(c), float(h), float(l), float(c), 1000.0)
        for day, c, h, l in zip(trading_days(len(closes)), closes, highs, lows)
    ]


def holding(bars: Sequence[Bar], bars_ago: int = 1) -> Position:
    """bars 의 뒤에서 bars_ago 번째 날에 산 포지션 (1 = 어제 매수)."""
    entry = bars[-bars_ago]
    return Position("A", 10, entry.close, entry.date, entry.close)


def open_entry(plan: DayPlan) -> EntryRule:
    """'시가 매수만 있는 계획'인지 확인하고 진입 규칙을 돌려줍니다."""
    assert plan.exit is None
    assert plan.entry is not None and plan.entry.kind == EntryKind.OPEN and plan.entry.offset == 0.0
    return plan.entry


def open_exit(plan: DayPlan) -> ExitRule:
    """'시가 매도만 있는 계획'인지 확인하고 청산 규칙을 돌려줍니다."""
    assert plan.entry is None
    assert plan.exit is not None and plan.exit.kind == ExitKind.OPEN
    return plan.exit


def assert_invalid(cls: type[Strategy], match: str, **params: Any) -> None:
    with pytest.raises(ValueError, match=match):
        cls(**params)


def random_bars(seed: int, count: int, tick: float = 0.0) -> list[Bar]:
    """난수 걸음(random walk) 일봉. tick 을 주면 그 단위로 반올림해 '같은 값'이 자주 나오게 합니다."""
    rng = random.Random(seed)

    def snap(value: float) -> float:
        return round(value / tick) * tick if tick else value

    bars: list[Bar] = []
    close = 50_000.0
    for day in trading_days(count):
        open_ = snap(close * (1 + rng.gauss(0, 0.005)))
        close = snap(max(close * math.exp(rng.gauss(0, 0.025)), 1_000.0))
        high = snap(max(open_, close) * (1 + abs(rng.gauss(0, 0.008))))
        low = snap(min(open_, close) * (1 - abs(rng.gauss(0, 0.008))))
        bars.append(Bar(day, open_, max(high, open_, close), min(low, open_, close), close, 100_000.0))
    return bars


# --------------------------------------------------------------------------- #
# sma_cross
# --------------------------------------------------------------------------- #
def test_sma_cross_buys_when_fast_average_is_above_slow_average():
    bars = candles([70_000] * 19 + [72_000])               # 5일선 70,400 / 20일선 70,100
    entry = open_entry(SmaCross().plan(bars, None))
    assert entry.score == pytest.approx(70_400 / 70_100 - 1)
    assert entry.note == "5일선(70,400) > 20일선(70,100)"


def test_sma_cross_sells_when_fast_average_falls_below_slow_average():
    bars = candles([70_000] * 19 + [68_000])               # 5일선 69,600 / 20일선 69,900
    exit_ = open_exit(SmaCross().plan(bars, holding(bars)))
    assert exit_.note == "5일선(69,600) < 20일선(69,900)"


def test_sma_cross_holds_in_every_other_case():
    up = candles([70_000] * 19 + [72_000])
    down = candles([70_000] * 19 + [68_000])
    flat = candles([70_000] * 20)
    strategy = SmaCross()
    assert strategy.plan(up, holding(up)) == HOLD          # 보유 중 + 상승 추세 → 계속 보유 (진입 계획 없음)
    assert strategy.plan(down, None) == HOLD               # 미보유 + 하락 추세 → 관망
    assert strategy.plan(flat, None) == HOLD               # 두 평균이 같으면 어느 쪽도 아님
    assert strategy.plan(flat, holding(flat)) == HOLD


def test_sma_cross_uses_only_the_slow_window():
    # 20일보다 오래된 급등락은 결과에 영향을 주지 않습니다.
    bars = candles([999_999, 1] + [70_000] * 19 + [72_000])
    assert open_entry(SmaCross().plan(bars, None)).note == "5일선(70,400) > 20일선(70,100)"
    custom = SmaCross(fast=2, slow=3)
    assert open_entry(custom.plan(candles([10, 10, 13]), None)).score == pytest.approx(11.5 / 11 - 1)


def test_sma_cross_cross_only_buys_only_on_the_day_of_the_cross():
    first_day = candles([70_000] * 20 + [72_000])          # 하루 전: 두 평균이 같음 → 오늘 막 넘어섬
    second_day = candles([70_000] * 20 + [72_000, 72_000])  # 하루 전에도 이미 위에 있었음
    cross_only = SmaCross(cross_only=True)
    entry = open_entry(cross_only.plan(first_day, None))
    assert entry.note == "골든크로스: 5일선(70,400) > 20일선(70,100)"
    assert cross_only.plan(second_day, None) == HOLD
    assert open_entry(SmaCross().plan(second_day, None)).note == "5일선(70,800) > 20일선(70,200)"
    # 청산 규칙은 cross_only 와 무관
    down = candles([70_000] * 20 + [68_000])
    assert open_exit(cross_only.plan(down, holding(down))).note == "5일선(69,600) < 20일선(69,900)"


def test_sma_cross_warmup():
    assert SmaCross().warmup == 20
    assert SmaCross(cross_only=True).warmup == 21
    assert SmaCross(fast=1, slow=2).warmup == 2
    assert SmaCross(fast=10, slow=60, cross_only=True).warmup == 61


def test_sma_cross_rejects_bad_parameters():
    assert_invalid(SmaCross, "fast 값은 1 이상", fast=0)
    assert_invalid(SmaCross, "보다 작아야", fast=20, slow=20)
    assert_invalid(SmaCross, "보다 작아야", fast=30)
    assert_invalid(SmaCross, "slow 값은 2 이상", fast=1, slow=1)
    assert_invalid(SmaCross, "fast 값은 소수점 없는 정수", fast=5.0)
    assert_invalid(SmaCross, "fast 값은 소수점 없는 정수", fast=True)
    assert_invalid(SmaCross, "slow 값은 소수점 없는 정수", slow="20")
    assert_invalid(SmaCross, "cross_only 값은 true 또는 false", cross_only=1)
    assert_invalid(SmaCross, "cross_only 값은 true 또는 false", cross_only="yes")
    assert_invalid(SmaCross, "없는 파라미터", period=5)


# --------------------------------------------------------------------------- #
# rsi_reversion  (period=2 → RSI 가 쓰는 종가는 21개)
# --------------------------------------------------------------------------- #
OVERSOLD = [10_000] * 19 + [9_900, 9_800]                  # 하락만 있었음 → RSI 0
OVERBOUGHT = [10_000] * 19 + [10_100, 10_200]              # 상승만 있었음 → RSI 100
FLAT = [10_000] * 21                                       # 움직임 없음 → RSI 50
# 꾸준히 오르다 이틀 눌림: 상승 평균 100 → 50 → 25, 하락 평균 0 → 50 → 75 → RSI = 25
PULLBACK = [10_000 + 100 * i for i in range(19)] + [11_700, 11_600]


def test_rsi_reversion_buys_when_oversold():
    bars = candles(OVERSOLD)
    entry = open_entry(RsiReversion(period=2).plan(bars, None))
    assert entry.score == pytest.approx(30.0)              # buy_below 30 − RSI 0
    assert entry.note == "RSI(2) 0.0 < 30"
    pullback = open_entry(RsiReversion(period=2).plan(candles(PULLBACK), None))
    assert pullback.score == pytest.approx(5.0) and pullback.note == "RSI(2) 25.0 < 30"


def test_rsi_reversion_sells_when_recovered():
    bars = candles(OVERBOUGHT)
    exit_ = open_exit(RsiReversion(period=2).plan(bars, holding(bars)))
    assert exit_.note == "RSI(2) 100.0 > 55"


def test_rsi_reversion_holds_in_every_other_case():
    strategy = RsiReversion(period=2)
    flat, oversold, overbought = candles(FLAT), candles(OVERSOLD), candles(OVERBOUGHT)
    assert strategy.plan(flat, None) == HOLD
    assert strategy.plan(flat, holding(flat)) == HOLD      # 어제 매수, RSI 50 → 계속 보유
    assert strategy.plan(overbought, None) == HOLD         # 미보유 + 과매수 → 관망
    assert strategy.plan(oversold, holding(oversold)) == HOLD   # 보유 중 + 과매도 → 추가 매수 계획 없음
    # 경계값은 신호가 아님 (RSI 가 정확히 buy_below / sell_above 와 같을 때)
    exact = RsiReversion(period=2, buy_below=25.0, sell_above=50.0)
    assert exact.plan(candles(PULLBACK), None) == HOLD
    assert exact.plan(flat, holding(flat)) == HOLD


def test_rsi_reversion_trend_filter():
    filtered = RsiReversion(period=2, trend_ma=20)
    # 상승 추세 속 눌림목: 종가 11,600 > 20일선 11,020 → 매수
    entry = open_entry(filtered.plan(candles(PULLBACK), None))
    assert entry.note == "RSI(2) 25.0 < 30, 종가(11,600) > 20일선(11,020)"
    # 과매도지만 종가 9,800 < 20일선 9,985 → 필터가 막음 (필터를 끄면 매수)
    assert filtered.plan(candles(OVERSOLD), None) == HOLD
    assert RsiReversion(period=2, trend_ma=0).plan(candles(OVERSOLD), None).entry is not None
    # 필터는 매도에는 관여하지 않음
    bars = candles(OVERBOUGHT)
    assert open_exit(filtered.plan(bars, holding(bars))).note == "RSI(2) 100.0 > 55"


def test_rsi_reversion_time_stop():
    bars = candles(FLAT)                                   # RSI 50 → RSI 로는 매도 사유 없음
    strategy = RsiReversion(period=2, max_hold_days=3)
    assert strategy.plan(bars, holding(bars, 1)) == HOLD   # 진입일 포함 1거래일 보유
    assert strategy.plan(bars, holding(bars, 2)) == HOLD
    exit_ = open_exit(strategy.plan(bars, holding(bars, 3)))
    assert exit_.note == "보유 3거래일 경과 (반등 없음, 기간 청산)"
    assert strategy.plan(bars, holding(bars, 4)).exit is not None
    ancient = replace(holding(bars), entry_date=date(2000, 1, 3))    # 넘겨받은 일봉보다 오래된 진입일
    assert strategy.plan(bars, ancient).exit is not None
    # 0 = 기간 청산 사용 안 함
    assert RsiReversion(period=2, max_hold_days=0).plan(bars, ancient) == HOLD
    # RSI 매도 사유가 함께 있으면 RSI 쪽 설명을 남김
    hot = candles(OVERBOUGHT)
    assert open_exit(strategy.plan(hot, holding(hot, 5))).note == "RSI(2) 100.0 > 55"


def test_rsi_reversion_time_stop_counts_trading_days_not_calendar_days():
    bars = candles(FLAT)
    friday_entry = next(i for i in range(1, 6) if bars[-i].date.weekday() == 4)
    position = holding(bars, friday_entry)                 # 금요일 매수 → 주말을 끼고 보유
    calendar_days = (bars[-1].date - position.entry_date).days + 1
    assert calendar_days > friday_entry or friday_entry == 1
    assert RsiReversion(period=2, max_hold_days=friday_entry).plan(bars, position).exit is not None
    assert RsiReversion(period=2, max_hold_days=friday_entry + 1).plan(bars, position) == HOLD


def test_rsi_reversion_warmup():
    assert RsiReversion().warmup == 141                    # RSI(14) 는 종가 141개를 사용
    assert RsiReversion(period=2).warmup == 21
    assert RsiReversion(trend_ma=200).warmup == 200
    assert RsiReversion(period=2, max_hold_days=30).warmup == 31
    assert RsiReversion(period=2, max_hold_days=0, trend_ma=5).warmup == 21


def test_rsi_reversion_rejects_bad_parameters():
    assert_invalid(RsiReversion, "period 값은 2 이상", period=1)
    assert_invalid(RsiReversion, "period 값은 소수점 없는 정수", period=14.0)
    assert_invalid(RsiReversion, "0 < buy_below < sell_above < 100", buy_below=0)
    assert_invalid(RsiReversion, "0 < buy_below < sell_above < 100", buy_below=60)
    assert_invalid(RsiReversion, "0 < buy_below < sell_above < 100", buy_below=55.0)
    assert_invalid(RsiReversion, "0 < buy_below < sell_above < 100", sell_above=100)
    assert_invalid(RsiReversion, "buy_below 값은 숫자", buy_below="30")
    assert_invalid(RsiReversion, "sell_above 값은 숫자", sell_above=True)
    assert_invalid(RsiReversion, "buy_below 값은 유한한 숫자", buy_below=math.nan)
    assert_invalid(RsiReversion, "trend_ma 값은 0 이상", trend_ma=-1)
    assert_invalid(RsiReversion, "trend_ma 값은 소수점 없는 정수", trend_ma=1.5)
    assert_invalid(RsiReversion, "max_hold_days 값은 0 이상", max_hold_days=-1)
    assert_invalid(RsiReversion, "max_hold_days 값은 소수점 없는 정수", max_hold_days=False)
    RsiReversion(buy_below=25, sell_above=60)              # 정수로 적어도 됨


# --------------------------------------------------------------------------- #
# volatility_breakout
# --------------------------------------------------------------------------- #
def vb_bars(last_high: float = 71_500, last_low: float = 70_000, last_close: float = 71_000) -> list[Bar]:
    """평탄한 19일 + 마지막 날만 지정한 일봉 20개."""
    return candles([70_000] * 19 + [last_close], highs=[70_000] * 19 + [last_high], lows=[70_000] * 19 + [last_low])


def breakout_entry(plan: DayPlan) -> EntryRule:
    assert plan.entry is not None and plan.entry.kind == EntryKind.BREAKOUT
    return plan.entry


def test_volatility_breakout_sets_target_offset_from_yesterdays_range():
    plan = VolatilityBreakout().plan(vb_bars(), None)
    entry = breakout_entry(plan)
    assert plan.exit is None                                # 미보유 + next_open → 청산 규칙 없음
    assert entry.offset == pytest.approx(750.0)             # (71,500 − 70,000) × 0.5
    assert entry.score == 0.0
    assert entry.note == "전일 변동폭 1,500 × k 0.5 = 750"
    assert breakout_entry(VolatilityBreakout(k=1).plan(vb_bars(), None)).offset == pytest.approx(1_500.0)
    assert breakout_entry(VolatilityBreakout(k=2.0).plan(vb_bars(), None)).offset == pytest.approx(3_000.0)
    # warmup 은 1: 어제 봉 하나만 있어도 계획을 세울 수 있음
    assert breakout_entry(VolatilityBreakout().plan(vb_bars()[-1:], None)).offset == pytest.approx(750.0)


@pytest.mark.parametrize("high, low", [(70_000, 70_000), (0, 0), (69_000, 70_000), (math.nan, 70_000), (math.inf, 70_000)])
def test_volatility_breakout_never_enters_without_a_positive_range(high, low):
    bars = vb_bars(last_high=high, last_low=low)
    assert VolatilityBreakout().plan(bars, None) == HOLD
    # 진입은 못 해도 청산 규칙은 그대로 나와야 함 (어제 산 물량은 팔아야 하므로)
    held = VolatilityBreakout().plan(bars, holding(bars))
    assert held.entry is None and held.exit is not None and held.exit.kind == ExitKind.OPEN
    close_mode = VolatilityBreakout(hold="close").plan(bars, None)
    assert close_mode.entry is None and close_mode.exit is not None and close_mode.exit.kind == ExitKind.CLOSE


def test_volatility_breakout_next_open_sells_yesterdays_purchase_and_allows_reentry():
    bars = vb_bars()
    plan = VolatilityBreakout().plan(bars, holding(bars))
    assert breakout_entry(plan).offset == pytest.approx(750.0)   # 시가에 판 뒤 같은 날 다시 돌파하면 재매수
    assert plan.exit == ExitRule(ExitKind.OPEN, note="변동성 돌파 매수분은 다음 거래일 시가에 매도")


def test_volatility_breakout_close_mode_always_exits_at_the_close():
    bars = vb_bars()
    strategy = VolatilityBreakout(hold="close")
    expected_exit = ExitRule(ExitKind.CLOSE, note="변동성 돌파 매수분은 당일 종가에 매도")
    flat_plan = strategy.plan(bars, None)                   # 오늘 살 물량을 종가에 팔기 위해 미리 걸어 둠
    assert breakout_entry(flat_plan).offset == pytest.approx(750.0) and flat_plan.exit == expected_exit
    held_plan = strategy.plan(bars, holding(bars))          # 남아 있는 물량도 종가에 정리
    assert breakout_entry(held_plan).offset == pytest.approx(750.0) and held_plan.exit == expected_exit


def test_volatility_breakout_trend_filter():
    filtered = VolatilityBreakout(trend_ma=20)
    above = vb_bars(last_close=71_000)                      # 종가 71,000 > 20일선 70,050
    entry = breakout_entry(filtered.plan(above, None))
    assert entry.note == "전일 변동폭 1,500 × k 0.5 = 750, 종가(71,000) > 20일선(70,050)"
    below = vb_bars(last_high=70_500, last_low=69_000, last_close=69_500)   # 종가 69,500 < 20일선 69,975
    assert filtered.plan(below, None) == HOLD
    assert VolatilityBreakout().plan(below, None).entry is not None         # 필터를 끄면 진입
    # 필터가 진입을 막아도 어제 매수분 청산은 그대로
    held = filtered.plan(below, holding(below))
    assert held.entry is None and held.exit is not None and held.exit.kind == ExitKind.OPEN
    # 종가가 평균과 같으면 '위'가 아님
    level = vb_bars(last_close=70_000)
    assert filtered.plan(level, None) == HOLD


def test_volatility_breakout_warmup():
    assert VolatilityBreakout().warmup == 1
    assert VolatilityBreakout(trend_ma=20).warmup == 20
    assert VolatilityBreakout(trend_ma=1).warmup == 1


def test_volatility_breakout_rejects_bad_parameters():
    assert_invalid(VolatilityBreakout, "k 값은 0 초과 2 이하", k=0)
    assert_invalid(VolatilityBreakout, "k 값은 0 초과 2 이하", k=-0.5)
    assert_invalid(VolatilityBreakout, "k 값은 0 초과 2 이하", k=2.1)
    assert_invalid(VolatilityBreakout, "k 값은 숫자", k="0.5")
    assert_invalid(VolatilityBreakout, "k 값은 숫자", k=True)
    assert_invalid(VolatilityBreakout, "k 값은 유한한 숫자", k=math.nan)
    assert_invalid(VolatilityBreakout, 'hold 값은 "next_open" 또는 "close"', hold="overnight")
    assert_invalid(VolatilityBreakout, 'hold 값은 "next_open" 또는 "close"', hold=1)
    assert_invalid(VolatilityBreakout, 'hold 값은 "next_open" 또는 "close"', hold=None)
    assert_invalid(VolatilityBreakout, "trend_ma 값은 0 이상", trend_ma=-1)
    assert_invalid(VolatilityBreakout, "trend_ma 값은 소수점 없는 정수", trend_ma=2.5)


# --------------------------------------------------------------------------- #
# donchian_breakout  (기본: 직전 20일 최고가 돌파 매수 / 직전 10일 최저가 이탈 매도)
# --------------------------------------------------------------------------- #
def channel(
    last_close: float,
    *,
    last_high: float | None = None,
    last_low: float | None = None,
    highs: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
) -> list[Bar]:
    """종가 70,000 · 고가 71,000 · 저가 69,000 인 봉들 뒤에 마지막 봉 하나를 붙입니다."""
    highs = [71_000] * 20 if highs is None else list(highs)
    lows = [69_000] * 20 if lows is None else list(lows)
    last_high = max(last_close, 71_000) if last_high is None else last_high
    last_low = min(last_close, 69_000) if last_low is None else last_low
    return candles([70_000] * len(highs) + [last_close], highs=highs + [last_high], lows=lows + [last_low])


def test_donchian_buys_when_close_exceeds_the_prior_high():
    bars = channel(71_500, last_high=72_000)                # 어제 고가 72,000 은 비교 대상이 아님
    entry = open_entry(DonchianBreakout().plan(bars, None))
    assert entry.score == pytest.approx(71_500 / 71_000 - 1)
    assert entry.note == "종가(71,500) > 직전 20일 최고가(71,000)"


def test_donchian_entry_window_is_exactly_the_entry_days_before_yesterday():
    strategy = DonchianBreakout()
    # 21번째 전 봉(구간 밖)의 높은 고가는 무시
    outside = channel(71_500, highs=[80_000] + [71_000] * 20, lows=[69_000] * 21)
    assert strategy.plan(outside, None).entry is not None
    # 20번째 전 봉(구간의 맨 앞)의 높은 고가는 반영
    inside = channel(71_500, highs=[80_000] + [71_000] * 19)
    assert strategy.plan(inside, None) == HOLD
    # 종가가 최고가와 같으면 돌파가 아님
    assert strategy.plan(channel(71_000), None) == HOLD
    assert strategy.plan(channel(70_000), None) == HOLD


def test_donchian_sells_when_close_falls_below_the_prior_low():
    bars = channel(68_500, last_low=68_000)                 # 어제 저가 68,000 은 비교 대상이 아님
    exit_ = open_exit(DonchianBreakout().plan(bars, holding(bars)))
    assert exit_.note == "종가(68,500) < 직전 10일 최저가(69,000)"


def test_donchian_exit_window_is_exactly_the_exit_days_before_yesterday():
    # 직전 10일의 저가는 69,000, 그보다 오래된 봉의 저가는 60,000
    lows = [60_000] * 10 + [69_000] * 10
    bars = channel(68_500, lows=lows)
    assert DonchianBreakout().plan(bars, holding(bars)).exit is not None            # 10일 기준: 이탈
    assert DonchianBreakout(exit_days=11).plan(bars, holding(bars)) == HOLD         # 11일 기준: 최저가 60,000
    level = channel(69_000)
    assert DonchianBreakout().plan(level, holding(level)) == HOLD                   # 같으면 이탈이 아님


def test_donchian_holds_in_every_other_case():
    strategy = DonchianBreakout()
    breakout, breakdown = channel(71_500), channel(68_500)
    assert strategy.plan(breakout, holding(breakout)) == HOLD      # 보유 중 신고가 → 계속 보유 (진입 계획 없음)
    assert strategy.plan(breakdown, None) == HOLD                  # 미보유 + 저가 이탈 → 관망


def test_donchian_refuses_to_plan_on_broken_prices_in_the_window_it_reads():
    # 거래정지일처럼 저가가 0 으로 들어온 봉이 있으면 '최저가 0' 으로 조용히 매도를 놓치지 않고 오류를 냅니다.
    lows = [69_000] * 15 + [0] + [69_000] * 4
    bars = channel(68_500, lows=lows)
    with pytest.raises(ValueError, match="저가가 올바르지 않습니다"):
        DonchianBreakout().plan(bars, holding(bars))
    old = channel(68_500, lows=[0] * 10 + [69_000] * 10)    # 매도 판단 구간(10일) 밖의 깨진 값은 무관
    assert DonchianBreakout().plan(old, holding(old)).exit is not None


def test_donchian_warmup():
    assert DonchianBreakout().warmup == 21
    assert DonchianBreakout(entry_days=5, exit_days=30).warmup == 31
    assert DonchianBreakout(entry_days=2, exit_days=1).warmup == 3


def test_donchian_rejects_bad_parameters():
    assert_invalid(DonchianBreakout, "entry_days 값은 2 이상", entry_days=1)
    assert_invalid(DonchianBreakout, "exit_days 값은 1 이상", exit_days=0)
    assert_invalid(DonchianBreakout, "entry_days 값은 소수점 없는 정수", entry_days=20.0)
    assert_invalid(DonchianBreakout, "entry_days 값은 소수점 없는 정수", entry_days="20")
    assert_invalid(DonchianBreakout, "exit_days 값은 소수점 없는 정수", exit_days=True)


# --------------------------------------------------------------------------- #
# bollinger_reversion
# --------------------------------------------------------------------------- #
def bands(closes: Sequence[float], num_std: float = 2.0) -> tuple[float, float, float]:
    """표준 라이브러리 statistics 로 따로 계산한 볼린저밴드 (하단, 중심선, 상단)."""
    middle = statistics.fmean(closes)
    width = num_std * statistics.pstdev(closes)
    return middle - width, middle, middle + width


def test_bollinger_buys_below_the_lower_band():
    closes = [70_000] * 19 + [60_000]
    lower, _, _ = bands(closes)                             # 평균 69,500 − 2 × 2,179.4 = 65,141.1
    assert lower == pytest.approx(65_141.1, abs=0.1)
    entry = open_entry(BollingerReversion().plan(candles(closes), None))
    assert entry.score == pytest.approx((lower - 60_000) / 60_000)
    assert entry.note == "종가(60,000) < 볼린저 하단(65,141)"


def test_bollinger_sells_above_the_middle_or_upper_band():
    # 69,000 과 71,000 을 오가다 70,500 으로 마감: 중심선(약 70,000)보다는 위, 상단(약 72,000)보다는 아래
    closes = [69_000, 71_000] * 9 + [69_000, 70_500]
    _, middle, upper = bands(closes)
    assert middle < 70_500 < upper
    bars = candles(closes)
    exit_ = open_exit(BollingerReversion().plan(bars, holding(bars)))
    assert exit_.note == f"종가(70,500) > 볼린저 중심선({middle:,.0f})"
    assert BollingerReversion(exit_at="upper").plan(bars, holding(bars)) == HOLD
    # 한 번에 크게 뛰면 상단도 넘음
    spike = [70_000] * 19 + [71_000]
    _, _, spike_upper = bands(spike)
    assert spike_upper < 71_000
    spike_bars = candles(spike)
    upper_exit = open_exit(BollingerReversion(exit_at="upper").plan(spike_bars, holding(spike_bars)))
    assert upper_exit.note == f"종가(71,000) > 볼린저 상단({spike_upper:,.0f})"


def test_bollinger_num_std_changes_the_band_width():
    closes = [69_000, 71_000] * 9 + [71_000, 68_500]        # 평균보다 약 1.5 표준편차 아래
    lower_1, _, _ = bands(closes, 1.0)
    lower_2, _, _ = bands(closes, 2.0)
    assert lower_2 < 68_500 < lower_1
    assert BollingerReversion(num_std=1).plan(candles(closes), None).entry is not None
    assert BollingerReversion(num_std=2.0).plan(candles(closes), None) == HOLD


def test_bollinger_holds_in_every_other_case():
    strategy = BollingerReversion()
    crash = candles([70_000] * 19 + [60_000])
    spike = candles([70_000] * 19 + [71_000])
    flat = candles([123.45] * 20)                           # 소수점 가격이 전혀 움직이지 않은 경우
    assert strategy.plan(crash, holding(crash)) == HOLD     # 보유 중 + 하단 이탈 → 추가 매수 계획 없음
    assert strategy.plan(spike, None) == HOLD               # 미보유 + 상단 돌파 → 관망
    assert strategy.plan(flat, None) == HOLD                # 밴드 폭 0: 종가 = 하단 = 중심선 → 신호 없음
    assert strategy.plan(flat, holding(flat)) == HOLD


def test_bollinger_warmup_and_window():
    assert BollingerReversion().warmup == 20
    assert BollingerReversion(period=5).warmup == 5
    closes = [1.0, 999_999.0] + [70_000] * 19 + [60_000]    # 20일보다 오래된 값은 무관
    assert BollingerReversion().plan(candles(closes), None).entry.note == "종가(60,000) < 볼린저 하단(65,141)"


def test_bollinger_rejects_bad_parameters():
    assert_invalid(BollingerReversion, "period 값은 2 이상", period=1)
    assert_invalid(BollingerReversion, "period 값은 소수점 없는 정수", period=20.5)
    assert_invalid(BollingerReversion, "num_std 값은 0보다 커야", num_std=0)
    assert_invalid(BollingerReversion, "num_std 값은 0보다 커야", num_std=-2.0)
    assert_invalid(BollingerReversion, "num_std 값은 숫자", num_std="2")
    assert_invalid(BollingerReversion, "num_std 값은 숫자", num_std=True)
    assert_invalid(BollingerReversion, "num_std 값은 유한한 숫자", num_std=math.inf)
    assert_invalid(BollingerReversion, 'exit_at 값은 "middle" 또는 "upper"', exit_at="lower")
    assert_invalid(BollingerReversion, 'exit_at 값은 "middle" 또는 "upper"', exit_at=0)


# --------------------------------------------------------------------------- #
# momentum
# --------------------------------------------------------------------------- #
def test_momentum_buys_when_lookback_return_is_positive():
    bars = candles([50_000, 51_000, 50_500, 55_000])
    entry = open_entry(Momentum(lookback=3).plan(bars, None))
    assert entry.score == pytest.approx(0.10)
    assert entry.note == "3일 수익률 +10.0% (상승 추세)"


def test_momentum_sells_when_return_turns_negative():
    bars = candles([50_000, 51_000, 50_500, 45_000])
    exit_ = open_exit(Momentum(lookback=3).plan(bars, holding(bars)))
    assert exit_.note == "3일 수익률 -10.0% (하락 전환)"


def test_momentum_holds_in_every_other_case():
    strategy = Momentum(lookback=3)
    up = candles([50_000, 51_000, 50_500, 55_000])
    down = candles([50_000, 51_000, 50_500, 45_000])
    unchanged = candles([50_000, 60_000, 40_000, 50_000])   # 3일 수익률이 정확히 0
    assert strategy.plan(up, holding(up)) == HOLD           # 보유 중 + 상승 → 계속 보유 (진입 계획 없음)
    assert strategy.plan(down, None) == HOLD                # 미보유 + 하락 → 관망
    assert strategy.plan(unchanged, None) == HOLD
    assert strategy.plan(unchanged, holding(unchanged)) == HOLD


def test_momentum_exit_lookback_can_differ_from_entry_lookback():
    # 5일 수익률 +20%, 2일 수익률 −4%
    bars = candles([100_000, 120_000, 120_000, 125_000, 121_000, 120_000])
    fast_exit = Momentum(lookback=5, exit_lookback=2)
    assert open_entry(fast_exit.plan(bars, None)).note == "5일 수익률 +20.0% (상승 추세)"   # 매수는 5일 기준
    assert open_exit(fast_exit.plan(bars, holding(bars))).note == "2일 수익률 -4.0% (하락 전환)"
    assert Momentum(lookback=5).plan(bars, holding(bars)) == HOLD      # exit_lookback 0 = 5일 기준 → 보유
    # 매도 기간이 더 긴 경우: 2일 수익률 −4% 라 매수는 안 하지만, 5일 수익률 +20% 라 팔지도 않음
    slow_exit = Momentum(lookback=2, exit_lookback=5)
    assert slow_exit.plan(bars, None) == HOLD
    assert slow_exit.plan(bars, holding(bars)) == HOLD


def test_momentum_warmup_and_window():
    assert Momentum().warmup == 61
    assert Momentum(lookback=20, exit_lookback=5).warmup == 21
    assert Momentum(lookback=5, exit_lookback=40).warmup == 41
    bars = candles([1.0, 999_999.0, 50_000, 51_000, 50_500, 55_000])   # 4일보다 오래된 값은 무관
    assert open_entry(Momentum(lookback=3).plan(bars, None)).score == pytest.approx(0.10)


def test_momentum_refuses_to_plan_on_broken_prices():
    for broken in (0.0, -50_000.0, math.nan):
        bars = candles([broken, 51_000, 50_500, 55_000])
        with pytest.raises(ValueError, match="종가가 올바르지 않습니다"):
            Momentum(lookback=3).plan(bars, None)


def test_momentum_rejects_bad_parameters():
    assert_invalid(Momentum, "lookback 값은 1 이상", lookback=0)
    assert_invalid(Momentum, "lookback 값은 소수점 없는 정수", lookback=60.0)
    assert_invalid(Momentum, "lookback 값은 소수점 없는 정수", lookback="60")
    assert_invalid(Momentum, "exit_lookback 값은 0 이상", exit_lookback=-1)
    assert_invalid(Momentum, "exit_lookback 값은 소수점 없는 정수", exit_lookback=True)


# --------------------------------------------------------------------------- #
# 레지스트리
# --------------------------------------------------------------------------- #
def test_registry_lists_every_strategy_in_display_order():
    assert list(STRATEGIES) == ALL_NAMES
    for name, cls in STRATEGIES.items():
        assert issubclass(cls, Strategy) and cls.name == name
        assert cls.description and "\n" not in cls.description
    assert StrategyConfig().name in STRATEGIES               # 설정의 기본 전략이 실제로 존재


def test_available_strategies_describes_each_strategy_for_help_output():
    rows = available_strategies()
    assert [name for name, _, _ in rows] == ALL_NAMES
    by_name = {name: (description, defaults) for name, description, defaults in rows}
    assert by_name["sma_cross"] == ("이동평균 골든크로스 추세추종", {"fast": 5, "slow": 20, "cross_only": False})
    assert by_name["rsi_reversion"] == (
        "RSI 과매도 반등 매수",
        {"period": 14, "buy_below": 30.0, "sell_above": 55.0, "trend_ma": 0, "max_hold_days": 10},
    )
    assert by_name["volatility_breakout"] == ("변동성 돌파 (래리 윌리엄스)", {"k": 0.5, "hold": "next_open", "trend_ma": 0})
    assert by_name["donchian_breakout"] == ("신고가 돌파 추세추종 (터틀)", {"entry_days": 20, "exit_days": 10})
    assert by_name["bollinger_reversion"] == ("볼린저밴드 하단 반등 매수", {"period": 20, "num_std": 2.0, "exit_at": "middle"})
    assert by_name["momentum"] == ("절대 모멘텀 (N일 수익률 추세추종)", {"lookback": 60, "exit_lookback": 0})
    # 돌려받은 기본값을 고쳐도 전략의 실제 기본값은 변하지 않아야 함
    rows[0][2]["k"] = 99
    assert STRATEGIES["volatility_breakout"].DEFAULTS["k"] == 0.5
    assert available_strategies()[0][2]["k"] == 0.5


def test_create_strategy_builds_with_defaults_and_overrides():
    for name, cls in STRATEGIES.items():
        strategy = create_strategy(name)
        assert type(strategy) is cls and strategy.params == cls.DEFAULTS
        assert isinstance(strategy.warmup, int) and strategy.warmup >= 1
        assert type(create_strategy(name, {})) is cls
    custom = create_strategy("sma_cross", {"fast": 3, "slow": 10})
    assert custom.params == {"fast": 3, "slow": 10, "cross_only": False} and custom.warmup == 10
    assert SmaCross.DEFAULTS == {"fast": 5, "slow": 20, "cross_only": False}    # 기본값은 그대로


def test_create_strategy_does_not_keep_a_reference_to_the_given_params():
    params = {"lookback": 20}
    strategy = create_strategy("momentum", params)
    params["lookback"] = 5
    assert strategy.params["lookback"] == 20


@pytest.mark.parametrize("name", ["", "SMA_CROSS", "sma-cross", "sma_cross ", "macd", None, 5])
def test_create_strategy_unknown_name_lists_the_available_names(name):
    with pytest.raises(ValueError, match="알 수 없는 전략 이름") as error:
        create_strategy(name)
    for known in ALL_NAMES:
        assert known in str(error.value)


def test_create_strategy_passes_on_parameter_errors():
    with pytest.raises(ValueError, match="sma_cross.fast 값은 1 이상"):
        create_strategy("sma_cross", {"fast": 0})
    with pytest.raises(ValueError, match="없는 파라미터"):
        create_strategy("momentum", {"period": 20})
    with pytest.raises(ValueError, match="파라미터는 '이름 = 값' 형태"):
        create_strategy("momentum", [("lookback", 20)])
    with pytest.raises(ValueError, match="파라미터는 '이름 = 값' 형태"):
        create_strategy("momentum", {1: 20})


# --------------------------------------------------------------------------- #
# 모든 전략의 공통 성질
# --------------------------------------------------------------------------- #
PARAM_SETS: dict[str, list[dict[str, Any]]] = {
    "sma_cross": [
        {},
        {"fast": 1, "slow": 2},
        {"fast": 3, "slow": 10},
        {"fast": 5, "slow": 20, "cross_only": True},
        {"fast": 10, "slow": 60, "cross_only": True},
    ],
    "rsi_reversion": [
        {},
        {"period": 2, "buy_below": 20, "sell_above": 70, "max_hold_days": 0},
        {"period": 5, "trend_ma": 60, "max_hold_days": 3},
        {"period": 3, "buy_below": 45.0, "sell_above": 50.0, "trend_ma": 5, "max_hold_days": 40},
    ],
    "volatility_breakout": [
        {},
        {"k": 0.3, "hold": "close"},
        {"k": 1, "trend_ma": 20},
        {"k": 2.0, "hold": "close", "trend_ma": 5},
    ],
    "donchian_breakout": [
        {},
        {"entry_days": 2, "exit_days": 1},
        {"entry_days": 5, "exit_days": 30},
        {"entry_days": 55, "exit_days": 20},
    ],
    "bollinger_reversion": [
        {},
        {"period": 2, "num_std": 0.5},
        {"period": 10, "num_std": 1.5, "exit_at": "upper"},
        {"period": 50, "num_std": 1},
    ],
    "momentum": [
        {},
        {"lookback": 1},
        {"lookback": 20, "exit_lookback": 5},
        {"lookback": 5, "exit_lookback": 40},
    ],
}
ALL_CASES = [(name, params) for name, sets in PARAM_SETS.items() for params in sets]
CASE_IDS = [f"{name}-{index}" for name, sets in PARAM_SETS.items() for index in range(len(sets))]

# 가격이 연속적인 경우와, 100원 단위로 반올림되어 '같은 값'이 자주 나오는 경우
WALKS = [random_bars(seed=101, count=260), random_bars(seed=202, count=260, tick=100.0)]


def position_variants(history: Sequence[Bar]) -> list[Position | None]:
    """미보유 + 진입 시점이 서로 다른 보유 상태들 (기간 청산처럼 진입일을 보는 규칙까지 검증)."""
    variants: list[Position | None] = [None]
    for bars_ago in (1, 3, 11, 45):
        if bars_ago <= len(history):
            variants.append(holding(history, bars_ago))
    variants.append(replace(holding(history), entry_date=date(2000, 1, 3)))
    return variants


class TailOnlyHistory(Sequence[Bar]):
    """맨 뒤 allowed 개 밖의 일봉을 읽으려 하면 실패하는 일봉 목록."""

    def __init__(self, bars: Sequence[Bar], allowed: int) -> None:
        self._bars = list(bars)
        self._first_allowed = len(self._bars) - allowed

    def __len__(self) -> int:
        return len(self._bars)

    def __getitem__(self, index):  # type: ignore[override]
        touched = range(len(self._bars))[index]
        first = (touched[0] if len(touched) else len(self._bars)) if isinstance(index, slice) else touched
        assert first >= self._first_allowed, f"warmup 구간 밖의 일봉을 읽었습니다 (index {index!r})"
        return self._bars[index]


def test_param_sets_cover_every_registered_strategy():
    assert set(PARAM_SETS) == set(STRATEGIES)


@pytest.mark.parametrize("name, params", ALL_CASES, ids=CASE_IDS)
def test_plan_depends_only_on_the_last_warmup_bars(name, params):
    """결정성: 날마다 길어지는 일봉(백테스트)과 고정 길이 일봉(실전)이 완전히 같은 계획을 만든다."""
    strategy = create_strategy(name, params)
    warmup = strategy.warmup
    compared = 0
    for bars in WALKS:
        for end in range(warmup, len(bars) + 1):
            history = bars[:end]
            tail = history[-warmup:]
            for position in position_variants(history):
                expected = strategy.plan(tail, position)
                assert strategy.plan(history, position) == expected, (end, position)
                compared += 1
    assert compared > 100


@pytest.mark.parametrize("name, params", ALL_CASES, ids=CASE_IDS)
def test_plan_never_reads_bars_older_than_warmup(name, params):
    """효율: 일봉이 아무리 길어도 맨 뒤 warmup 개만 읽는다 (백테스트는 종목·날짜마다 plan 을 호출)."""
    strategy = create_strategy(name, params)
    bars = WALKS[0]
    guarded = TailOnlyHistory(bars, strategy.warmup)
    for position in position_variants(bars):
        assert strategy.plan(guarded, position) == strategy.plan(bars, position)
    with pytest.raises(AssertionError, match="warmup 구간 밖"):
        guarded[0]                                         # 감시 장치 자체가 동작하는지 확인


@pytest.mark.parametrize("name, params", ALL_CASES, ids=CASE_IDS)
def test_plan_is_pure_and_well_formed(name, params):
    strategy = create_strategy(name, params)
    is_breakout = name == "volatility_breakout"
    bars = WALKS[1]
    for end in range(strategy.warmup, len(bars) + 1):
        history = bars[:end]
        before = list(history)
        for position in position_variants(history):
            frozen = replace(position) if position is not None else None
            plan = strategy.plan(history, position)
            assert isinstance(plan, DayPlan)
            assert strategy.plan(history, position) == plan           # 같은 입력 → 같은 출력
            assert position == frozen and history == before           # 입력을 바꾸지 않음

            if plan.entry is not None:
                assert math.isfinite(plan.entry.score) and plan.entry.note
                if is_breakout:
                    assert plan.entry.kind == EntryKind.BREAKOUT and plan.entry.score == 0.0
                    assert 0 < plan.entry.offset < math.inf
                else:
                    # 시가 매수 계획은 미보유일 때만, 그리고 점수는 신호의 강도(양수)
                    assert plan.entry.kind == EntryKind.OPEN and position is None and plan.entry.score > 0
            if plan.exit is not None:
                assert plan.exit.note
                if not is_breakout:
                    assert plan.exit.kind == ExitKind.OPEN and position is not None

            # 코어가 저장하는 형태(JSON)로 바꿨다가 되돌려도 같은 계획이어야 함 (재시작 복구)
            saved = json.loads(json.dumps(SymbolDay(plan=plan).to_dict(), ensure_ascii=False))
            assert SymbolDay.from_dict(saved).plan == plan


@pytest.mark.parametrize("name", ALL_NAMES)
def test_every_strategy_produces_both_entries_and_exits_on_random_data(name):
    """위의 성질 테스트들이 '항상 관망'인 전략으로 헛돌지 않았는지 확인."""
    entries = exits = 0
    for params in PARAM_SETS[name]:
        strategy = create_strategy(name, params)
        for bars in WALKS:
            for end in range(strategy.warmup, len(bars) + 1):
                history = bars[:end]
                entries += strategy.plan(history, None).entry is not None
                exits += strategy.plan(history, holding(history, min(3, len(history)))).exit is not None
    assert entries > 10 and exits > 10


@pytest.mark.parametrize("name, params", ALL_CASES, ids=CASE_IDS)
def test_a_stock_that_never_moves_gives_no_signal(name, params):
    # 소수점 가격이 전혀 움직이지 않을 때 부동소수 오차로 가짜 신호가 나오면 안 됩니다.
    strategy = create_strategy(name, {**params, "max_hold_days": 0} if name == "rsi_reversion" else params)
    bars = candles([4_999.99] * (strategy.warmup + 3))
    plan = strategy.plan(bars, None)
    assert plan.entry is None
    if name != "volatility_breakout":                       # 변동성 돌파의 청산은 가격과 무관한 규칙
        assert plan == HOLD
        assert strategy.plan(bars, holding(bars)) == HOLD


@pytest.mark.parametrize("name, params", ALL_CASES, ids=CASE_IDS)
def test_plan_with_too_few_bars_fails_with_a_clear_message(name, params):
    # 코어는 warmup 미만이면 plan 을 부르지 않지만, 직접 호출했을 때도 엉뚱한 값 대신 분명한 오류를 냅니다.
    strategy = create_strategy(name, params)
    bars = WALKS[0][: strategy.warmup - 1]
    with pytest.raises(ValueError, match="일봉이 부족합니다"):
        strategy.plan(bars, None)


# --------------------------------------------------------------------------- #
# 코어 연동 (PaperBroker + MemoryStore 로 약 300거래일 구동)
# --------------------------------------------------------------------------- #
SYMBOLS = ("A", "B", "C")
E2E_COSTS = CostConfig()
E2E_RISK = RiskConfig(capital=10_000_000, max_positions=2)


def synthetic_bars(seed: int, count: int = 300) -> list[Bar]:
    """완만한 상승 + 70일 주기의 출렁임 + 잡음. 추세·역추세 전략 모두 매매 기회가 생기는 모양."""
    rng = random.Random(seed)
    phase = rng.uniform(0, 2 * math.pi)
    bars: list[Bar] = []
    walk, prev_close = 0.0, 50_000.0
    for i, day in enumerate(trading_days(count)):
        walk += rng.gauss(0, 0.012)
        close = 50_000.0 * math.exp(0.0004 * i + 0.12 * math.sin(2 * math.pi * i / 70 + phase) + walk)
        open_ = prev_close * (1 + rng.gauss(0, 0.004))
        high = max(open_, close) * (1 + abs(rng.gauss(0, 0.006)))
        low = min(open_, close) * (1 - abs(rng.gauss(0, 0.006)))
        o, h, l, c = (float(round(value / 10) * 10) for value in (open_, high, low, close))
        bars.append(Bar(day, o, max(h, o, c), min(l, o, c), c, 100_000.0))
        prev_close = c
    return bars


E2E_DATA: Mapping[str, list[Bar]] = {symbol: synthetic_bars(seed) for symbol, seed in zip(SYMBOLS, (11, 12, 13))}


def make_core(name: str) -> TradingCore:
    return TradingCore(
        strategy=create_strategy(name),
        universe=SYMBOLS,
        risk=E2E_RISK,
        costs=E2E_COSTS,
        broker=PaperBroker(E2E_COSTS.slippage_rate),
        store=MemoryStore(),
        clock=lambda: datetime(2023, 1, 2, 9, 0, tzinfo=KST),
        enforce_drawdown_halt=False,
    )


def check_ledger(core: TradingCore) -> None:
    """장부가 서로 맞는지: 평가금 = 현금 + 주식 평가액, 현금은 유한한 0 이상의 수."""
    assert math.isfinite(core.cash) and core.cash >= 0
    value = sum(position.qty * core.price_of(symbol) for symbol, position in core.positions.items())
    assert core.positions_value() == pytest.approx(value)
    assert core.equity() == pytest.approx(core.cash + value)
    assert math.isfinite(core.equity()) and core.equity() > 0
    assert len(core.positions) <= core.risk.max_positions
    for position in core.positions.values():
        assert position.qty > 0 and position.avg_price > 0


def drive(core: TradingCore, data: Mapping[str, list[Bar]], lookback: int | None = None) -> None:
    """일봉으로 하루의 사건을 합성해 코어를 끝까지 구동합니다 (간단한 백테스트 드라이버).

    lookback 을 주면 실전처럼 매일 '최근 lookback 개'의 일봉만 코어에 넘깁니다.
    """
    days = [bar.date for bar in data[SYMBOLS[0]]]
    for i in range(1, len(days)):
        today = {symbol: bars[i] for symbol, bars in data.items()}
        start = 0 if lookback is None else max(0, i - lookback)
        core.start_day(days[i], {symbol: bars[start:i] for symbol, bars in data.items()})
        core.on_open({symbol: bar.open for symbol, bar in today.items()})
        check_ledger(core)
        for symbol, bar in today.items():
            levels = core.watch_levels(symbol)
            if 0 < levels.breakout <= bar.high:
                core.on_price(symbol, levels.breakout)     # 장중 고가가 목표가에 닿음 → 목표가에 매수
            levels = core.watch_levels(symbol)
            if levels.stop > 0 and bar.low <= levels.stop:
                core.on_price(symbol, levels.stop)         # 장중 저가가 손절선에 닿음
        core.on_close({symbol: bar.close for symbol, bar in today.items()})
        core.end_day(
            {symbol: bar.close for symbol, bar in today.items()},
            {symbol: bar.high for symbol, bar in today.items()},
        )
        check_ledger(core)
        assert not any(day_state.note.startswith("전략") for day_state in core.day.symbols.values())


@pytest.mark.parametrize("name", ALL_NAMES)
def test_strategy_drives_the_real_core_end_to_end(name):
    core = make_core(name)
    drive(core, E2E_DATA)

    # 전략 오류나 경고 없이 끝까지 구동됨
    assert [event for event in core.store.events() if event["level"] == "warning"] == []
    history = core.store.equity_history()
    assert [day for day, _, _ in history] == [bar.date for bar in E2E_DATA["A"][1:]]
    assert all(math.isfinite(equity) and equity > 0 and math.isfinite(cash) and cash >= 0 for _, equity, cash in history)

    # 실제로 매매가 일어났고, 주문 사유에 전략의 설명이 남음
    orders = core.store.orders()
    buys = [order for order in orders if order["side"] == "buy"]
    sells = [order for order in orders if order["side"] == "sell"]
    assert buys and sells and all(order["status"] == "filled" for order in orders)
    prefix = "돌파 매수(목표가 " if name == "volatility_breakout" else "시가 매수: "
    assert all(order["reason"].startswith(prefix) and len(order["reason"]) > len(prefix) + 5 for order in buys)
    strategy_sells = [order for order in sells if order["reason"].startswith(("시가 청산: ", "종가 청산: "))]
    assert strategy_sells and all(len(order["reason"]) > 10 for order in strategy_sells)

    # 주문 기록만으로 현금과 보유 수량을 다시 계산하면 장부와 일치
    cash = core.capital_base
    shares = dict.fromkeys(SYMBOLS, 0)
    for order in orders:
        if order["side"] == "buy":
            cash -= order["amount"] + order["fee"]
            shares[order["symbol"]] += order["filled_qty"]
        else:
            cash += order["amount"] - order["fee"] - order["tax"]
            shares[order["symbol"]] -= order["filled_qty"]
    assert core.cash == pytest.approx(cash)
    assert {symbol: qty for symbol, qty in shares.items() if qty} == {s: p.qty for s, p in core.positions.items()}


@pytest.mark.parametrize("name", ALL_NAMES)
def test_growing_history_and_fixed_lookback_trade_identically(name):
    """백테스트(전체 일봉)와 실전(최근 warmup + 여유분만)이 주문 하나까지 똑같이 매매하는지."""
    backtest_style = make_core(name)
    drive(backtest_style, E2E_DATA)
    live_style = make_core(name)
    drive(live_style, E2E_DATA, lookback=live_style.strategy.warmup + 5)

    assert live_style.store.orders() == backtest_style.store.orders()
    assert live_style.store.equity_history() == backtest_style.store.equity_history()
    assert live_style.cash == backtest_style.cash and live_style.positions == backtest_style.positions


def test_close_mode_volatility_breakout_never_holds_overnight():
    core = TradingCore(
        strategy=create_strategy("volatility_breakout", {"hold": "close", "k": 0.7}),
        universe=SYMBOLS,
        risk=E2E_RISK,
        costs=E2E_COSTS,
        broker=PaperBroker(E2E_COSTS.slippage_rate),
        store=MemoryStore(),
        clock=lambda: datetime(2023, 1, 2, 9, 0, tzinfo=KST),
        enforce_drawdown_halt=False,
    )
    drive(core, E2E_DATA)
    assert core.positions == {}
    orders = core.store.orders()
    assert orders and len(orders) % 2 == 0
    for symbol in SYMBOLS:
        # 종목별로 '매수 → 같은 날 매도'가 짝을 이룸 (손절이든 종가 청산이든 당일에 끝남)
        symbol_orders = [order for order in orders if order["symbol"] == symbol]
        assert len(symbol_orders) % 2 == 0
        for buy, sell in zip(symbol_orders[::2], symbol_orders[1::2]):
            assert (buy["side"], sell["side"]) == ("buy", "sell") and buy["day"] == sell["day"]
            assert buy["reason"].startswith("돌파 매수(목표가 ")
    assert all(equity == cash for _, equity, cash in core.store.equity_history())   # 장 마감 후에는 항상 현금뿐

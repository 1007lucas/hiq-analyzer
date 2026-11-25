"""기술적 지표 단위 테스트 — 손으로 계산한 기대값, 경계 조건, '최근 구간만 본다' 성질."""

from __future__ import annotations

import math
import random
import statistics
from datetime import date, timedelta
from typing import Callable, Sequence

import pytest

from autotrader import indicators as ind
from autotrader.models import Bar

BAD_PERIODS = [0, -1, 2.0, True, "3", None]


def random_walk(seed: int, count: int, start: float = 50_000.0, step: float = 0.02) -> list[float]:
    rng = random.Random(seed)
    values = [start]
    while len(values) < count:
        values.append(values[-1] * math.exp(rng.gauss(0, step)))
    return values


def bar(day: int, open_: float, high: float, low: float, close: float) -> Bar:
    return Bar(date(2024, 1, 1) + timedelta(days=day), open_, high, low, close, 1000.0)


# --------------------------------------------------------------------------- #
# 파라미터 검증 도우미
# --------------------------------------------------------------------------- #
def test_require_int_accepts_only_real_integers():
    assert ind.require_int(5, "x") == 5
    assert ind.require_int(0, "x", minimum=0) == 0
    for bad in (True, False, 5.0, "5", None, [5]):
        with pytest.raises(ValueError, match="x 값은 소수점 없는 정수"):
            ind.require_int(bad, "x")
    with pytest.raises(ValueError, match="x 값은 3 이상"):
        ind.require_int(2, "x", minimum=3)


def test_require_number_accepts_int_and_float_but_not_bool_text_or_non_finite():
    assert ind.require_number(2, "x") == 2.0 and isinstance(ind.require_number(2, "x"), float)
    assert ind.require_number(0.5, "x") == 0.5
    for bad in (True, "0.5", None, [1.0]):
        with pytest.raises(ValueError, match="x 값은 숫자여야"):
            ind.require_number(bad, "x")
    for bad in (math.nan, math.inf, -math.inf, 10**400):
        with pytest.raises(ValueError, match="x 값은 유한한 숫자"):
            ind.require_number(bad, "x")


# --------------------------------------------------------------------------- #
# sma
# --------------------------------------------------------------------------- #
def test_sma_is_the_mean_of_the_last_period_values():
    assert ind.sma([1, 2, 3, 4, 5], 5) == 3.0
    assert ind.sma([100, 1, 2, 3], 3) == 2.0          # 맨 앞의 100 은 구간 밖
    assert ind.sma([7.5], 1) == 7.5
    assert ind.sma((70_000, 70_200, 70_700), 2) == 70_450.0   # 튜플도 가능


def test_sma_needs_exactly_period_values():
    assert ind.sma([1.0, 2.0, 3.0], 3) == 2.0
    with pytest.raises(ValueError, match="부족"):
        ind.sma([1.0, 2.0], 3)
    with pytest.raises(ValueError, match="부족"):
        ind.sma([], 1)


@pytest.mark.parametrize("period", BAD_PERIODS)
def test_sma_rejects_invalid_period(period):
    with pytest.raises(ValueError, match="period"):
        ind.sma([1.0, 2.0, 3.0], period)


@pytest.mark.parametrize("price", [0.1, 1 / 3, 123.45, 70_000.0, 4_999.99])
@pytest.mark.parametrize("period", [2, 3, 5, 14, 20, 60])
def test_mean_of_a_flat_series_is_exactly_that_value(price, period):
    # 소수점 가격에서도 오차가 없어야 "전혀 안 움직인 종목"에서 가짜 신호가 나지 않습니다.
    flat = [price] * period
    assert ind.sma(flat, period) == price
    assert ind.ema(flat, period, window=period) == price
    assert ind.stdev(flat, period) == 0.0
    assert ind.bollinger(flat, period, 2.0) == (price, price, price)


# --------------------------------------------------------------------------- #
# ema
# --------------------------------------------------------------------------- #
def reference_ema(values: Sequence[float], period: int) -> float:
    """교과서 그대로의 EMA: 처음 period 개 평균에서 출발해 주어진 값 전부를 반영."""
    alpha = 2 / (period + 1)
    value = sum(values[:period]) / period
    for x in values[period:]:
        value = alpha * x + (1 - alpha) * value
    return value


def test_ema_hand_computed():
    # 구간 = 마지막 5개 [11,12,13,14,15], 시작값 = (11+12+13)/3 = 12, alpha = 0.5
    # 12 → 12 + 0.5×(14−12) = 13 → 13 + 0.5×(15−13) = 14
    assert ind.ema([10, 11, 12, 13, 14, 15], period=3, window=5) == pytest.approx(14.0)
    # 구간 6개 전부, 시작값 = (2+4+6+8)/4 = 5, alpha = 0.4 → 5 + 0.4×7 = 7.8 → 7.8 + 0.4×2.2 = 8.68
    assert ind.ema([2, 4, 6, 8, 12, 10], period=4, window=6) == pytest.approx(8.68)


def test_ema_with_window_equal_to_period_is_the_sma():
    values = random_walk(1, 30)
    assert ind.ema(values, 7, window=7) == pytest.approx(ind.sma(values, 7))


def test_ema_matches_reference_over_the_window():
    values = random_walk(2, 400)
    for period, window in ((2, 9), (5, 50), (12, 120), (26, 260)):
        expected = reference_ema(values[-window:], period)
        assert ind.ema(values, period, window) == pytest.approx(expected, rel=1e-12)
    # 기본 구간(period × 10)은 '처음부터 누적'한 값과 사실상 같습니다
    assert ind.ema(values, 12) == pytest.approx(reference_ema(values, 12), rel=1e-6)


def test_ema_default_window_is_ten_periods_and_is_required_in_full():
    values = [float(v) for v in range(1, 21)]            # 20개 = period 2 × 10
    assert ind.ema(values, 2) == pytest.approx(reference_ema(values, 2))
    with pytest.raises(ValueError, match="부족"):
        ind.ema(values[1:], 2)                            # 19개: 하나 모자람
    assert ind.ema(values[1:], 2, window=19) > 0          # 구간을 직접 줄이면 가능
    with pytest.raises(ValueError, match="부족"):
        ind.ema(values, 2, window=21)


@pytest.mark.parametrize("period, window", [(0, None), (-2, None), (2.0, None), (True, None), (3, 2), (3, 0), (3, 4.0), (3, True)])
def test_ema_rejects_invalid_parameters(period, window):
    with pytest.raises(ValueError):
        ind.ema([float(v) for v in range(100)], period, window)


# --------------------------------------------------------------------------- #
# rsi
# --------------------------------------------------------------------------- #
def reference_rsi(closes: Sequence[float], period: int) -> float:
    """교과서 그대로의 와일더 RSI (주어진 종가 전부를 사용하는 독립 구현)."""
    ups: list[float] = []
    downs: list[float] = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        ups.append(diff if diff > 0 else 0.0)
        downs.append(-diff if diff < 0 else 0.0)
    up = sum(ups[:period]) / period
    down = sum(downs[:period]) / period
    for i in range(period, len(ups)):
        up = (up * (period - 1) + ups[i]) / period
        down = (down * (period - 1) + downs[i]) / period
    if down == 0:
        return 50.0 if up == 0 else 100.0
    rs = up / down
    return 100.0 * rs / (1.0 + rs)


# StockCharts ChartSchool 의 14일 RSI 예제 (QQQQ 종가 33개와 공개된 RSI 19개).
# 공개된 표는 반올림 전 가격으로 계산되어, 반올림된 종가로 다시 계산하면 0.1 미만의 차이가 납니다.
CLASSIC_CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89,
    46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64, 46.21, 46.25,
    45.71, 46.45, 45.78, 45.35, 44.03, 44.18, 44.22, 44.57, 43.42, 42.66, 43.13,
]
CLASSIC_RSI = [
    70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93, 63.26, 56.06, 62.38,
    54.71, 50.42, 39.99, 41.46, 41.87, 45.46, 37.30, 33.08, 37.77,
]


def test_rsi_reproduces_the_classic_published_example():
    for offset, published in enumerate(CLASSIC_RSI):
        closes = CLASSIC_CLOSES[: 15 + offset]
        value = ind.rsi(closes, 14, window=len(closes) - 1)
        assert value == pytest.approx(published, abs=0.1), offset
        assert value == pytest.approx(reference_rsi(closes, 14), abs=1e-9), offset


def test_rsi_hand_computed():
    # 변화량 [+1, −1, +2], period 2: 시작 평균 상승 0.5 / 하락 0.5
    # → 상승 (0.5×1 + 2)/2 = 1.25, 하락 (0.5×1 + 0)/2 = 0.25 → RS = 5 → RSI = 100 − 100/6
    assert ind.rsi([10, 11, 10, 12], period=2, window=3) == pytest.approx(100 - 100 / 6)
    # 구간이 period 와 같으면 단순 평균만: 상승 합 3, 하락 합 1 → RS = 3 → RSI = 75
    assert ind.rsi([10, 11, 10, 12], period=3, window=3) == pytest.approx(75.0)


def test_rsi_extremes_and_flat_series():
    rising = [100.0 + i for i in range(30)]
    falling = rising[::-1]
    assert ind.rsi(rising, 14, window=29) == 100.0       # 하락이 한 번도 없음
    assert ind.rsi(falling, 14, window=29) == 0.0        # 상승이 한 번도 없음
    assert ind.rsi([123.45] * 30, 14, window=29) == 50.0  # 전혀 움직이지 않음 → 중립


def test_rsi_matches_reference_and_stays_in_range():
    for seed in range(5):
        closes = random_walk(seed, 400)
        for period in (2, 5, 14, 21):
            window = period * 10
            value = ind.rsi(closes, period)
            assert 0.0 <= value <= 100.0
            assert value == pytest.approx(reference_rsi(closes[-(window + 1):], period), abs=1e-9)
            # 기본 구간(period × 10)은 '처음부터 누적'한 교과서 값과 사실상 같습니다
            assert value == pytest.approx(reference_rsi(closes, period), abs=0.01)


def test_rsi_min_bars_and_boundary():
    assert ind.rsi_min_bars(14) == 141
    assert ind.rsi_min_bars(14, 14) == 15
    assert ind.rsi_min_bars(2, 5) == 6
    closes = random_walk(7, 141)
    assert 0.0 <= ind.rsi(closes, 14) <= 100.0            # 정확히 필요한 만큼
    with pytest.raises(ValueError, match="부족"):
        ind.rsi(closes[1:], 14)                           # 하나 모자람
    assert 0.0 <= ind.rsi(closes[:15], 14, window=14) <= 100.0
    with pytest.raises(ValueError, match="부족"):
        ind.rsi(closes[:14], 14, window=14)


@pytest.mark.parametrize("period, window", [(0, None), (-1, None), (14.0, None), (True, None), ("14", None), (14, 13), (14, 0), (14, 20.0)])
def test_rsi_rejects_invalid_parameters(period, window):
    closes = random_walk(3, 300)
    with pytest.raises(ValueError):
        ind.rsi(closes, period, window)
    with pytest.raises(ValueError):
        ind.rsi_min_bars(period, window)


# --------------------------------------------------------------------------- #
# stdev / bollinger
# --------------------------------------------------------------------------- #
def test_stdev_is_population_standard_deviation_of_the_last_period_values():
    data = [2, 4, 4, 4, 5, 5, 7, 9]                       # 평균 5, 분산 32/8 = 4
    assert ind.stdev(data, 8) == pytest.approx(2.0)
    assert ind.stdev([1000, 1000] + data, 8) == pytest.approx(2.0)   # 앞의 값은 구간 밖
    assert ind.stdev([1, 3], 2) == pytest.approx(1.0)     # 표본(n−1) 방식이면 1.414…
    assert ind.stdev([42.0], 1) == 0.0
    values = random_walk(4, 100)
    assert ind.stdev(values, 20) == pytest.approx(statistics.pstdev(values[-20:]))


def test_stdev_boundary_and_invalid_period():
    with pytest.raises(ValueError, match="부족"):
        ind.stdev([1.0, 2.0], 3)
    for period in BAD_PERIODS:
        with pytest.raises(ValueError, match="period"):
            ind.stdev([1.0, 2.0, 3.0], period)


def test_bollinger_hand_computed():
    data = [2, 4, 4, 4, 5, 5, 7, 9]                       # 평균 5, 표준편차 2
    assert ind.bollinger(data, 8, 2.0) == pytest.approx((1.0, 5.0, 9.0))
    assert ind.bollinger(data, 8, 1) == pytest.approx((3.0, 5.0, 7.0))
    assert ind.bollinger([0, 0] + data, 8, 0.5) == pytest.approx((4.0, 5.0, 6.0))


def test_bollinger_defaults_boundary_and_consistency():
    values = random_walk(5, 60)
    lower, middle, upper = ind.bollinger(values)          # 기본 20일, 2배
    assert middle == ind.sma(values, 20)
    assert upper - middle == pytest.approx(2 * ind.stdev(values, 20))
    assert middle - lower == pytest.approx(upper - middle)
    assert ind.bollinger(values[-20:]) == (lower, middle, upper)
    with pytest.raises(ValueError, match="부족"):
        ind.bollinger(values[-19:])


@pytest.mark.parametrize("num_std", [0, -1.0, True, "2", None, math.nan, math.inf])
def test_bollinger_rejects_invalid_width(num_std):
    with pytest.raises(ValueError, match="num_std"):
        ind.bollinger([1.0, 2.0, 3.0], 3, num_std)


# --------------------------------------------------------------------------- #
# highest / lowest / rate_of_change
# --------------------------------------------------------------------------- #
def test_highest_and_lowest_look_only_at_the_last_period_values():
    data = [9, 1, 5, 3, 7, 4]
    assert ind.highest(data, 3) == 7 and ind.lowest(data, 3) == 3
    assert ind.highest(data, 6) == 9 and ind.lowest(data, 6) == 1
    assert ind.highest(data, 1) == 4 and ind.lowest(data, 1) == 4
    for fn in (ind.highest, ind.lowest):
        with pytest.raises(ValueError, match="부족"):
            fn(data, 7)
        for period in BAD_PERIODS:
            with pytest.raises(ValueError, match="period"):
                fn(data, period)


def test_rate_of_change_hand_computed():
    data = [100.0, 110.0, 121.0, 108.9]
    assert ind.rate_of_change(data, 1) == pytest.approx(-0.10)
    assert ind.rate_of_change(data, 2) == pytest.approx(-0.01)
    assert ind.rate_of_change(data, 3) == pytest.approx(0.089)
    assert ind.rate_of_change([50_000.0, 50_000.0], 1) == 0.0


def test_rate_of_change_boundary_and_invalid_input():
    with pytest.raises(ValueError, match="부족"):
        ind.rate_of_change([100.0, 110.0], 2)             # period + 1 개가 필요
    for base in (0.0, -5.0, math.nan):
        with pytest.raises(ValueError, match="기준값"):
            ind.rate_of_change([base, 110.0], 1)
    for period in BAD_PERIODS:
        with pytest.raises(ValueError, match="period"):
            ind.rate_of_change([100.0, 110.0, 121.0], period)


# --------------------------------------------------------------------------- #
# true_range / atr
# --------------------------------------------------------------------------- #
def test_true_range_includes_gaps_from_the_previous_close():
    assert ind.true_range(100, 103, 99) == 4              # 갭 없음: 고가 − 저가
    assert ind.true_range(100, 110, 105) == 10            # 갭 상승: 고가 − 전일 종가
    assert ind.true_range(100, 98, 90) == 10              # 갭 하락: 전일 종가 − 저가
    assert ind.true_range(100, 100, 100) == 0


@pytest.mark.parametrize(
    "prev_close, high, low",
    [(100, 99, 101), (100, 0, 0), (0, 105, 95), (-1, 105, 95), (100, 105, -1),
     (math.nan, 105, 95), (100, math.nan, 95), (100, 105, math.nan), (100, math.inf, 95)],
)
def test_true_range_rejects_broken_prices(prev_close, high, low):
    with pytest.raises(ValueError, match="가격이 올바르지 않습니다"):
        ind.true_range(prev_close, high, low)


def test_atr_hand_computed_and_boundary():
    bars = [
        bar(0, 100, 101, 99, 100),
        bar(1, 100, 105, 99, 104),      # TR = max(6, 5, 1) = 6
        bar(2, 106, 110, 106, 108),     # TR = max(4, 6, 2) = 6  (갭 상승)
        bar(3, 107, 107, 100, 101),     # TR = max(7, 1, 8) = 8
    ]
    assert ind.atr(bars, 3) == pytest.approx(20 / 3)
    assert ind.atr(bars, 2) == pytest.approx(7.0)
    assert ind.atr(bars, 1) == pytest.approx(8.0)
    with pytest.raises(ValueError, match="부족"):
        ind.atr(bars, 4)                                  # period + 1 개가 필요
    with pytest.raises(ValueError, match="부족"):
        ind.atr(bars)                                     # 기본 14일
    for period in BAD_PERIODS:
        with pytest.raises(ValueError, match="period"):
            ind.atr(bars, period)


def test_atr_rejects_broken_bars_inside_its_window_only():
    good = [bar(i, 100, 102, 98, 100) for i in range(4)]
    halted = bar(9, 0, 0, 0, 100)                         # 거래정지일처럼 고가·저가가 0 인 봉
    with pytest.raises(ValueError, match="가격이 올바르지 않습니다"):
        ind.atr(good + [halted], 2)
    assert ind.atr([halted, halted] + good, 2) == pytest.approx(4.0)   # 구간 밖의 깨진 봉은 무관


# --------------------------------------------------------------------------- #
# 일봉 → 가격 목록
# --------------------------------------------------------------------------- #
def test_recent_bars_returns_the_tail_and_requires_enough_bars():
    bars = [bar(i, 100, 101, 99, 100 + i) for i in range(5)]
    assert list(ind.recent_bars(bars, 2)) == bars[-2:]
    assert list(ind.recent_bars(tuple(bars), 5)) == bars
    with pytest.raises(ValueError, match=r"일봉이 부족합니다 \(필요 6개, 현재 5개\)"):
        ind.recent_bars(bars, 6)
    for count in (0, -1, 2.0, True):
        with pytest.raises(ValueError, match="count"):
            ind.recent_bars(bars, count)


def test_price_extractors_return_floats_in_order():
    bars = [bar(0, 100, 105, 95, 101), bar(1, 101, 108, 100, 107)]
    assert ind.close_prices(bars) == [101.0, 107.0]
    assert ind.high_prices(bars) == [105.0, 108.0]
    assert ind.low_prices(bars) == [95.0, 100.0]
    assert ind.close_prices([]) == []


@pytest.mark.parametrize("broken", [0.0, -100.0, math.nan, math.inf])
def test_price_extractors_reject_broken_prices_and_name_the_date(broken):
    good = bar(0, 100, 105, 95, 101)
    cases: list[tuple[Callable[[Sequence[Bar]], list[float]], Bar, str]] = [
        (ind.close_prices, bar(1, 100, 105, 95, broken), "종가"),
        (ind.high_prices, bar(1, 100, broken, 95, 101), "고가"),
        (ind.low_prices, bar(1, 100, 105, broken, 101), "저가"),
    ]
    for extract, bad_bar, label in cases:
        with pytest.raises(ValueError, match=f"2024-01-02 일봉의 {label}가 올바르지 않습니다"):
            extract([good, bad_bar])


def test_price_extractors_check_only_the_field_they_read():
    halted = bar(1, 0, 0, 0, 101)                         # 시가·고가·저가만 0 (거래정지일 형태)
    assert ind.close_prices([halted]) == [101.0]


# --------------------------------------------------------------------------- #
# 공통 성질: 최근 구간만 본다 / 입력을 바꾸지 않는다
# --------------------------------------------------------------------------- #
SERIES_INDICATORS: dict[str, tuple[Callable[[Sequence[float]], object], int]] = {
    # 이름: (지표 함수, 그 함수가 읽는 값의 개수)
    "sma": (lambda v: ind.sma(v, 20), 20),
    "ema(기본 구간)": (lambda v: ind.ema(v, 12), 120),
    "ema(구간 지정)": (lambda v: ind.ema(v, 5, window=17), 17),
    "rsi(기본 구간)": (lambda v: ind.rsi(v, 14), 141),
    "rsi(구간 지정)": (lambda v: ind.rsi(v, 3, window=8), 9),
    "stdev": (lambda v: ind.stdev(v, 20), 20),
    "bollinger": (lambda v: ind.bollinger(v, 20, 2.0), 20),
    "highest": (lambda v: ind.highest(v, 30), 30),
    "lowest": (lambda v: ind.lowest(v, 30), 30),
    "rate_of_change": (lambda v: ind.rate_of_change(v, 60), 61),
}


@pytest.mark.parametrize("name", SERIES_INDICATORS)
def test_older_data_never_changes_the_result(name):
    """백테스트(긴 일봉)와 실전(짧은 일봉)이 같은 값을 얻는지: 완전히 같은 값이어야 합니다."""
    fn, needed = SERIES_INDICATORS[name]
    for seed in range(3):
        values = random_walk(seed, 400)
        expected = fn(values[-needed:])
        assert fn(values) == expected
        assert fn(values[-(needed + 1):]) == expected
        assert fn([1.0, 9e9, 0.5] + values) == expected   # 앞에 엉뚱한 값이 붙어도 무관
        with pytest.raises(ValueError, match="부족"):
            fn(values[-(needed - 1):])


def test_atr_ignores_bars_before_its_window():
    closes = random_walk(9, 60)
    bars = [bar(i, c, c * 1.01, c * 0.99, c) for i, c in enumerate(closes)]
    assert ind.atr(bars, 14) == ind.atr(bars[-15:], 14)


def test_indicators_do_not_modify_their_input():
    values = random_walk(6, 200)
    snapshot = list(values)
    for fn, _ in SERIES_INDICATORS.values():
        fn(values)
    assert values == snapshot
    bars = [bar(i, c, c * 1.01, c * 0.99, c) for i, c in enumerate(values[:30])]
    bars_snapshot = list(bars)
    ind.atr(bars, 14)
    ind.close_prices(ind.recent_bars(bars, 5))
    assert bars == bars_snapshot

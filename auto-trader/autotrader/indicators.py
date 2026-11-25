"""기술적 지표 계산 (표준 라이브러리만 사용).

모든 함수는 **가장 최근 시점의 값 하나**만 돌려주는 순수 함수입니다.

설계 원칙 — "정해진 길이의 최근 구간만 본다"
---------------------------------------------
백테스트는 날마다 길어지는 일봉 전체를 넘기고, 실전 매매는 최근 몇 달 치만
넘깁니다. 두 경우의 지표 값이 조금이라도 다르면 "백테스트에서는 샀는데 실전에서는
사지 않는" 일이 생깁니다. 그래서 여기 있는 모든 지표는 입력의 **맨 뒤에서 정해진
개수만** 사용합니다. 더 오래된 데이터가 앞에 얼마나 붙어 있든 결과는 완전히 같습니다.

EMA·RSI 처럼 원래는 "처음부터 누적"하는 지표도 같은 이유로 최근 ``window`` 개
구간 안에서만 계산합니다 (기본값은 period 의 10배 — 누적 방식과의 차이가 매우 작습니다).
그 대신 데이터가 ``window`` 개보다 적으면 "있는 만큼만" 계산하지 않고 오류를 냅니다.

입력 검증
---------
* 데이터가 모자라거나 파라미터가 잘못되면 ValueError (한국어 메시지).
* 숫자열을 받는 함수는 값 자체는 검사하지 않습니다. 일봉(Bar)에서 가격을 꺼내는
  ``close_prices`` 등이 0 이하·NaN 같은 깨진 시세를 걸러 주므로, 전략은 반드시
  그 함수들을 거쳐 숫자열을 만듭니다.
"""

from __future__ import annotations

import math
from typing import Sequence, TypeVar

from .models import Bar

DEFAULT_WINDOW_MULTIPLE = 10   # EMA·RSI 의 기본 계산 구간 = period × 10

_T = TypeVar("_T")


# --------------------------------------------------------------------------- #
# 파라미터 검증 (지표와 전략이 함께 사용)
# --------------------------------------------------------------------------- #
def require_int(value: object, name: str, minimum: int | None = None) -> int:
    """정수 파라미터를 확인하고 그대로 돌려줍니다. 잘못되면 ValueError.

    True/False 는 파이썬에서 1/0 으로 계산되지만 설정 실수일 가능성이 높아 거부합니다.
    5.0 같은 실수도 거부합니다 (일봉 개수는 소수점 없는 정수여야 하므로).
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} 값은 소수점 없는 정수여야 합니다 (입력값: {value!r})")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} 값은 {minimum} 이상이어야 합니다 (입력값: {value})")
    return value


def require_number(value: object, name: str) -> float:
    """숫자(정수 또는 실수) 파라미터를 확인하고 float 로 돌려줍니다. 잘못되면 ValueError."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 값은 숫자여야 합니다 (입력값: {value!r})")
    try:
        number = float(value)
    except OverflowError:   # float 로 표현할 수 없을 만큼 큰 정수
        number = math.inf
    if not math.isfinite(number):
        raise ValueError(f"{name} 값은 유한한 숫자여야 합니다 (입력값: {value!r})")
    return number


def _tail(items: Sequence[_T], count: int) -> Sequence[_T]:
    """맨 뒤 count 개. 모자라면 ValueError (모자란 채로 계산하면 결과가 데이터 길이에 따라 달라지므로)."""
    if len(items) < count:
        raise ValueError(f"데이터가 부족합니다 (필요 {count}개, 현재 {len(items)}개)")
    return items[len(items) - count:]


def _smoothing_window(period: int, window: int | None) -> int:
    """EMA·RSI 가 실제로 사용할 구간 길이. window 를 생략하면 period × 10."""
    require_int(period, "period", minimum=1)
    if window is None:
        return period * DEFAULT_WINDOW_MULTIPLE
    return require_int(window, "window", minimum=period)


def _mean(data: Sequence[float]) -> float:
    """평균. 마지막 값을 기준으로 삼아 '기준과의 차이'를 평균한 뒤 다시 더합니다.

    값이 모두 같으면 차이가 정확히 0 이라 평균도 정확히 그 값이 됩니다. 그냥 더해서
    나누면 소수점이 있는 가격에서 마지막 자리 오차가 생겨, 전혀 움직이지 않은 종목에서
    "5일선 > 20일선" 같은 가짜 신호가 나올 수 있습니다.
    """
    anchor = data[-1]
    return anchor + math.fsum(x - anchor for x in data) / len(data)


# --------------------------------------------------------------------------- #
# 숫자열 지표
# --------------------------------------------------------------------------- #
def sma(values: Sequence[float], period: int) -> float:
    """단순이동평균: 최근 period 개 값의 평균."""
    require_int(period, "period", minimum=1)
    return _mean(_tail(values, period))


def ema(values: Sequence[float], period: int, window: int | None = None) -> float:
    """지수이동평균 (alpha = 2 / (period + 1)).

    최근 window 개(기본 period × 10) 안에서만 계산합니다: 그 구간의 처음 period 개
    평균으로 시작해서 나머지 값을 차례로 반영합니다.
    """
    span = _smoothing_window(period, window)
    data = _tail(values, span)
    alpha = 2.0 / (period + 1)
    value = _mean(data[:period])
    for x in data[period:]:
        value += alpha * (x - value)
    return value


def rsi_min_bars(period: int, window: int | None = None) -> int:
    """rsi() 계산에 필요한 종가 개수 (변화량 window 개를 얻으려면 종가가 하나 더 필요)."""
    return _smoothing_window(period, window) + 1


def rsi(closes: Sequence[float], period: int = 14, window: int | None = None) -> float:
    """와일더(Wilder) 방식 RSI. 0 ~ 100 사이 값 (낮을수록 과매도).

    최근 (window + 1) 개 종가(기본 window = period × 10)만 사용합니다: 그 구간의 처음
    period 개 변화량의 단순 평균으로 시작해서 와일더 평활을 이어 갑니다.
    가격이 전혀 움직이지 않았으면 중립값 50, 하락이 한 번도 없었으면 100 입니다.
    """
    data = _tail(closes, rsi_min_bars(period, window))
    changes = [after - before for before, after in zip(data, data[1:])]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = math.fsum(gains[:period]) / period
    avg_loss = math.fsum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 50.0 if avg_gain == 0 else 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def stdev(values: Sequence[float], period: int) -> float:
    """최근 period 개 값의 모표준편차 (N 으로 나눔 — 볼린저밴드의 관례)."""
    require_int(period, "period", minimum=1)
    data = _tail(values, period)
    mean = _mean(data)
    return math.sqrt(math.fsum((x - mean) ** 2 for x in data) / period)


def bollinger(values: Sequence[float], period: int = 20, num_std: float = 2.0) -> tuple[float, float, float]:
    """볼린저밴드 (하단, 중심선, 상단) = 이동평균 ∓ num_std × 표준편차."""
    width = require_number(num_std, "num_std")
    if width <= 0:
        raise ValueError(f"num_std 값은 0보다 커야 합니다 (입력값: {num_std!r})")
    middle = sma(values, period)
    band = width * stdev(values, period)
    return middle - band, middle, middle + band


def highest(values: Sequence[float], period: int) -> float:
    """최근 period 개 값 중 가장 큰 값."""
    require_int(period, "period", minimum=1)
    return max(_tail(values, period))


def lowest(values: Sequence[float], period: int) -> float:
    """최근 period 개 값 중 가장 작은 값."""
    require_int(period, "period", minimum=1)
    return min(_tail(values, period))


def rate_of_change(values: Sequence[float], period: int) -> float:
    """period 개 전 값 대비 변화율 (0.05 = +5%)."""
    require_int(period, "period", minimum=1)
    data = _tail(values, period + 1)
    base = data[0]
    if not base > 0:
        raise ValueError(f"변화율의 기준값은 0보다 커야 합니다 (기준값: {base!r})")
    return data[-1] / base - 1.0


# --------------------------------------------------------------------------- #
# 일봉(Bar) 을 직접 받는 함수 — 여기서 깨진 시세를 걸러 냅니다
# --------------------------------------------------------------------------- #
def recent_bars(bars: Sequence[Bar], count: int) -> Sequence[Bar]:
    """가장 최근 count 개 일봉 (오래된 것 → 최신 순). 모자라면 ValueError.

    전략은 plan() 의 첫 줄에서 이 함수로 자신의 warmup 만큼만 잘라 내고, 그 뒤로는
    잘라 낸 구간만 사용합니다. 그러면 넘겨받은 일봉이 아무리 길어도 결과가 같습니다.
    """
    require_int(count, "count", minimum=1)
    if len(bars) < count:
        raise ValueError(f"일봉이 부족합니다 (필요 {count}개, 현재 {len(bars)}개)")
    return bars[len(bars) - count:]


def close_prices(bars: Sequence[Bar]) -> list[float]:
    """일봉들의 종가 (입력 순서 그대로). 0 이하이거나 숫자가 아닌 값이 있으면 ValueError."""
    return [_checked_price(bar, bar.close, "종가") for bar in bars]


def high_prices(bars: Sequence[Bar]) -> list[float]:
    """일봉들의 고가 (입력 순서 그대로). 0 이하이거나 숫자가 아닌 값이 있으면 ValueError."""
    return [_checked_price(bar, bar.high, "고가") for bar in bars]


def low_prices(bars: Sequence[Bar]) -> list[float]:
    """일봉들의 저가 (입력 순서 그대로). 0 이하이거나 숫자가 아닌 값이 있으면 ValueError."""
    return [_checked_price(bar, bar.low, "저가") for bar in bars]


def _checked_price(bar: Bar, value: float, label: str) -> float:
    # 깨진 시세로 조용히 엉뚱한 매매 신호를 내느니, 멈추고 사용자에게 알리는 편이 안전합니다.
    if not 0 < value < math.inf:   # NaN 은 어떤 비교도 거짓이라 여기서 함께 걸러짐
        raise ValueError(f"{bar.date} 일봉의 {label}가 올바르지 않습니다 ({value!r}) — 시세 데이터를 확인해 주세요")
    return float(value)


def true_range(prev_close: float, high: float, low: float) -> float:
    """하루의 실제 변동폭(True Range): 전일 종가 대비 갭까지 포함한 고가-저가 폭."""
    if not (0 < low <= high < math.inf and 0 < prev_close < math.inf):
        raise ValueError(
            f"가격이 올바르지 않습니다 (전일 종가 {prev_close!r}, 고가 {high!r}, 저가 {low!r})"
        )
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr(bars: Sequence[Bar], period: int = 14) -> float:
    """평균 실제 변동폭(ATR): 최근 period 개 일봉의 True Range 단순 평균.

    각 봉의 True Range 에는 그 전날 종가가 필요하므로 일봉이 period + 1 개 있어야 합니다.
    """
    require_int(period, "period", minimum=1)
    window = _tail(bars, period + 1)
    ranges = [true_range(prev.close, bar.high, bar.low) for prev, bar in zip(window, window[1:])]
    return _mean(ranges)

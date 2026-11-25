"""백테스트 드라이버.

이 모듈에는 **매매 판단 로직이 없습니다.** 과거 일봉을 하루씩 꺼내 실전과 똑같은
TradingCore 에 "장 시작 전 → 시가 → 장중 → 종가 → 마감" 순서로 알려 주기만 합니다.
그래서 백테스트에서 본 매매 규칙이 실전에서도 그대로 실행됩니다.

하루를 재생하는 방법
--------------------
1. ``start_day``  : 오늘 **이전** 일봉만 전략에 넘깁니다. 오늘 봉은 절대 넘기지 않으므로
                    전략이 미래를 훔쳐볼 수 없습니다.
2. ``on_open``    : 오늘 시가를 알려 줍니다 (시가 매수/매도, 갭으로 넘어선 손절·익절).
3. 장중 합성      : 일봉의 고가/저가로 "손절가·익절가·돌파 목표가에 닿았는가"를 판단해,
                    닿았다면 그 가격을 ``on_price`` 로 알려 줍니다.
4. ``on_close``   : 종가를 알려 줍니다 (종가 청산).
5. ``end_day``    : 종가로 평가금을 기록합니다.

일봉만으로 장중을 흉내 낼 때의 가정 (결과를 읽을 때 꼭 알아야 할 것)
--------------------------------------------------------------------
일봉은 하루에 시가·고가·저가·종가 네 숫자뿐이라 장중에 **어떤 순서로** 움직였는지는
알 수 없습니다. 애매한 경우에는 항상 투자자에게 **불리한 쪽**으로 가정합니다.

* 시가 갭: 시가가 이미 손절가 아래(또는 익절가 위)에서 시작하면 손절가가 아니라
  **시가**에 체결됩니다. 이 처리는 코어의 ``on_open`` 이 합니다.
* 장중 손절: 저가가 손절가 이하이면 **손절가**에 팔린 것으로 봅니다 (슬리피지만큼 더 불리하게).
* 손절과 익절이 모두 그날 범위 안에 있으면 **손절이 먼저** 일어났다고 가정합니다.
* 돌파 매수 후 당일 손절: 오늘 돌파 매수한 종목도 그날 저가가 손절가 이하이면 당일
  손절된 것으로 처리합니다. 실제로는 저가가 돌파 **전에** 찍혔을 수도 있지만 일봉으로는
  구분할 수 없으므로 최악의 경우를 택합니다.
* 돌파 매수 후 당일 익절: 익절가는 항상 매수가보다 높으므로, 고가가 익절가 이상이면
  매수 **이후에** 그 가격에 닿은 것이 확실합니다. 이 경우는 근사가 아니라 정확합니다.
* 종목 사이의 시간 순서도 알 수 없습니다. 종목을 설정 순서대로 하나씩 처리하므로,
  일일 손실 한도는 "모든 종목의 시가 → 종목별 장중 사건" 순으로 평가한 근사입니다.
  한도 초과로 전량 청산할 때 다른 종목은 그 시점에 마지막으로 알려진 가격(대개 시가)에
  체결된 것으로 봅니다.
* 일봉이 없는 날(거래정지·데이터 누락)의 종목은 그날 매매하지 않습니다. 보유 중이면
  마지막 종가로 평가만 하고, 그날 나온 매도 주문은 실제 시장처럼 거부됩니다.
* 주문은 기준가에서 슬리피지만큼 불리한 가격에 **전량** 체결된다고 봅니다. 거래량 부족,
  상·하한가로 인한 미체결은 반영하지 않으므로 거래량이 적은 종목은 실제보다 좋게 나옵니다.

최대 낙폭 한도(max_drawdown_pct)에 의한 매수 중단은 백테스트에서는 적용하지 않습니다
(한 번 걸리면 사람이 풀어 줄 때까지 멈추는 장치라, 적용하면 그 뒤 기간을 평가할 수 없습니다).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Callable, Mapping, Sequence

from ..brokers.paper import PaperBroker
from ..config import CostConfig, RiskConfig
from ..core import TradingCore, WatchLevels
from ..models import KST, Bar, OrderRequest, OrderResult, OrderStatus
from ..state import MemoryStore
from ..strategies.base import Strategy
from .metrics import Metrics, compute_metrics

# 기록에 남는 가상 시각 (KST). 실제 장 운영 시간과 같은 순서가 되도록 정했습니다.
_OPEN_TIME = time(9, 0)
_INTRADAY_TIME = time(12, 0)
_CLOSE_TIME = time(15, 20)
_END_TIME = time(15, 30)

# 한 종목에서 하루에 일어날 수 있는 장중 사건은 "돌파 매수 → 손절/익절" 2건이 최대입니다.
# 코어가 예상과 다르게 반응해도 무한 반복하지 않도록 여유를 둔 상한입니다.
_MAX_EVENTS_PER_SYMBOL = 4
_MAX_PROGRESS_CALLS = 100
_OHLC_TOLERANCE = 1e-9          # 수정주가 계산에서 생기는 부동소수점 잡음은 오류로 보지 않음


@dataclass
class BacktestResult:
    """백테스트 한 번의 결과."""

    strategy_name: str
    strategy_params: dict[str, Any]
    symbols: list[str]
    start: date                                   # 실제로 매매를 시뮬레이션한 첫 거래일
    end: date                                     # 마지막 거래일
    initial_capital: float
    equity_curve: list[tuple[date, float]]        # 날짜별 장 마감 평가금
    cash_curve: list[tuple[date, float]]          # 날짜별 장 마감 현금
    benchmark_curve: list[tuple[date, float]]     # 같은 날짜의 단순보유(동일 비중) 평가금
    orders: list[dict[str, Any]]                  # 주문 기록 (오래된 것 → 최신 순, state.ORDER_FIELDS 형식)
    final_positions: list[dict[str, Any]]         # 마지막 날 장 마감 후 보유 종목
    metrics: Metrics
    names: dict[str, str]                         # 종목코드 → 표시 이름 (없을 수 있음)


class _SimClock:
    """코어에 넘기는 가상 시계. 드라이버가 하루의 단계마다 시각을 옮겨 줍니다.

    실제 시계를 쓰지 않으므로 같은 데이터로 돌리면 주문 기록의 시각까지 똑같이 나옵니다.
    """

    def __init__(self, day: date) -> None:
        self._now = datetime.combine(day, _OPEN_TIME, tzinfo=KST)

    def set(self, day: date, at: time) -> None:
        self._now = datetime.combine(day, at, tzinfo=KST)

    def __call__(self) -> datetime:
        return self._now


class _DailyBarBroker(PaperBroker):
    """오늘 일봉이 있는 종목의 주문만 체결시키는 가상 브로커.

    코어의 '일일 손실 한도 청산'은 보유 종목을 전부 마지막으로 알려진 가격에 팔려고 합니다.
    거래정지로 오늘 거래가 없는 종목까지 며칠 전 종가에 팔린 것으로 치면 결과가 현실보다
    좋게 나오므로, 그런 주문은 실제 시장에서처럼 거부합니다.
    """

    def __init__(self, slippage_rate: float) -> None:
        super().__init__(slippage_rate)
        self.tradable: frozenset[str] = frozenset()

    def submit_order(self, req: OrderRequest) -> OrderResult:
        if req.symbol not in self.tradable:
            return OrderResult(
                req,
                OrderStatus.REJECTED,
                message="오늘 거래가 없는 종목(거래정지 등)이라 주문이 체결되지 않았습니다",
            )
        return super().submit_order(req)


# --------------------------------------------------------------------------- #
# 입력 검증
# --------------------------------------------------------------------------- #
def _resolve_universe(data: Mapping[str, Sequence[Bar]], universe: Sequence[str] | None) -> list[str]:
    symbols = list(data) if universe is None else list(universe)
    if not symbols:
        raise ValueError("백테스트할 종목이 없습니다. 종목을 1개 이상 지정해 주세요")
    duplicates = sorted(sym for sym, count in Counter(symbols).items() if count > 1)
    if duplicates:
        raise ValueError(f"종목 목록에 중복된 종목이 있습니다: {', '.join(duplicates)}")
    for sym in symbols:
        if sym not in data or len(data[sym]) == 0:
            raise ValueError(f"{sym}: 일봉 데이터가 없습니다. 종목코드와 데이터 기간을 확인해 주세요")
    return symbols


def _validate_bars(symbol: str, bars: Sequence[Bar]) -> None:
    """일봉이 날짜순이고 가격이 말이 되는지 확인합니다. 잘못된 데이터로 낸 결과는 믿을 수 없으므로 바로 멈춥니다."""
    prev_day: date | None = None
    for bar in bars:
        if prev_day is not None and bar.date <= prev_day:
            raise ValueError(
                f"{symbol} {bar.date}: 일봉 날짜가 순서대로가 아닙니다 "
                f"({prev_day} 다음에 {bar.date}). 날짜가 중복되었거나 순서가 뒤섞여 있습니다"
            )
        prices = (bar.open, bar.high, bar.low, bar.close)
        if not all(math.isfinite(p) and p > 0 for p in prices):
            raise ValueError(
                f"{symbol} {bar.date}: 시가·고가·저가·종가는 모두 0보다 큰 숫자여야 합니다 "
                f"(시가 {bar.open}, 고가 {bar.high}, 저가 {bar.low}, 종가 {bar.close})"
            )
        if bar.low > min(bar.open, bar.close) * (1.0 + _OHLC_TOLERANCE):
            raise ValueError(
                f"{symbol} {bar.date}: 저가({bar.low})가 시가({bar.open}) 또는 종가({bar.close})보다 높습니다"
            )
        if bar.high < max(bar.open, bar.close) * (1.0 - _OHLC_TOLERANCE):
            raise ValueError(
                f"{symbol} {bar.date}: 고가({bar.high})가 시가({bar.open}) 또는 종가({bar.close})보다 낮습니다"
            )
        prev_day = bar.date


def _trading_days(
    series: Mapping[str, Sequence[Bar]], start: date | None, end: date | None
) -> list[date]:
    """기간 안에서 한 종목이라도 일봉이 있는 날 (오름차순)."""
    days = {
        bar.date
        for bars in series.values()
        for bar in bars
        if (start is None or bar.date >= start) and (end is None or bar.date <= end)
    }
    return sorted(days)


def _describe_period(start: date | None, end: date | None) -> str:
    return f"{start or '처음'} ~ {end or '끝'}"


# --------------------------------------------------------------------------- #
# 장중 사건 합성
# --------------------------------------------------------------------------- #
def _next_event_price(levels: WatchLevels, held: bool, bar: Bar, last_price: float) -> float | None:
    """오늘 일봉 범위 안에서 다음에 일어날 장중 사건의 가격. 일어날 일이 없으면 None.

    보유 중이면 손절을 익절보다 먼저 봅니다 (둘 다 범위 안이면 손절이 먼저였다고 보수적으로 가정).
    """
    if held:
        if levels.stop > 0 and bar.low <= levels.stop:
            # 손절가가 방금 체결된 가격보다 높은 경우(손절폭이 슬리피지보다 작은 설정)에는
            # 가격이 '올라가서' 손절될 수는 없으므로 지금 가격에 바로 팔린 것으로 봅니다.
            return min(levels.stop, last_price)
        if levels.take_profit > 0 and bar.high >= levels.take_profit:
            return levels.take_profit
        return None
    if levels.breakout > 0 and bar.high >= levels.breakout:
        return levels.breakout
    return None


def _replay_intraday(core: TradingCore, symbol: str, bar: Bar) -> None:
    """한 종목의 오늘 장중 사건(돌파 매수, 손절, 익절)을 일봉으로 합성해 코어에 알립니다."""
    last_price = bar.open
    for _ in range(_MAX_EVENTS_PER_SYMBOL):
        levels = core.watch_levels(symbol)
        held = symbol in core.positions
        price = _next_event_price(levels, held, bar, last_price)
        if price is None:
            return
        core.on_price(symbol, price)
        last_price = price
        if (symbol in core.positions) == held and core.watch_levels(symbol) == levels:
            return  # 코어가 반응하지 않았음 → 같은 가격을 또 알려 봐야 달라질 것이 없음


# --------------------------------------------------------------------------- #
# 벤치마크
# --------------------------------------------------------------------------- #
def benchmark_curve(
    data: Mapping[str, Sequence[Bar]],
    symbols: Sequence[str],
    days: Sequence[date],
    initial_capital: float,
) -> list[tuple[date, float]]:
    """단순보유 벤치마크: 첫날 초기 자금을 종목 수만큼 똑같이 나눠 사서 끝까지 들고 있는 경우.

    * 각 종목은 기간 중 처음 일봉이 있는 날의 종가에 산 것으로 봅니다 (그 전까지는 현금 = 1.0배).
    * 일봉이 없는 날은 직전 값을 그대로 씁니다.
    * 수수료·세금·슬리피지는 넣지 않습니다 (전략과 비교하는 기준선이므로 단순하게).
    """
    if not days:
        return []
    first, last = days[0], days[-1]
    closes = {
        sym: {bar.date: bar.close for bar in data[sym] if first <= bar.date <= last} for sym in symbols
    }
    base: dict[str, float] = {}
    relative = {sym: 1.0 for sym in symbols}
    curve: list[tuple[date, float]] = []
    for day in days:
        for sym in symbols:
            close = closes[sym].get(day)
            if close is not None:
                relative[sym] = close / base.setdefault(sym, close)
        curve.append((day, initial_capital * sum(relative.values()) / len(relative)))
    return curve


# --------------------------------------------------------------------------- #
# 실행
# --------------------------------------------------------------------------- #
def run_backtest(
    *,
    data: Mapping[str, Sequence[Bar]],
    strategy: Strategy,
    risk: RiskConfig,
    costs: CostConfig,
    start: date | None = None,
    end: date | None = None,
    universe: Sequence[str] | None = None,
    names: Mapping[str, str] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> BacktestResult:
    """과거 일봉으로 전략을 모의 운용합니다.

    data     : 종목코드 → 일봉 목록 (오래된 것 → 최신 순)
    start    : 매매를 시작할 날짜. 그 전의 일봉은 매매하지 않고 전략의 '과거 자료'로만 씁니다
    end      : 매매를 끝낼 날짜 (포함)
    universe : 매매 대상 종목과 순서. 생략하면 data 의 종목 전부
    names    : 종목코드 → 표시 이름
    progress : progress(끝낸 거래일 수, 전체 거래일 수) — 진행률 표시용, 최대 약 100번 호출
    """
    symbols = _resolve_universe(data, universe)
    series = {sym: list(data[sym]) for sym in symbols}
    for sym in symbols:
        _validate_bars(sym, series[sym])
    if start is not None and end is not None and start > end:
        raise ValueError(f"백테스트 시작일({start})이 종료일({end})보다 늦습니다")
    risk.validate()
    costs.validate()

    days = _trading_days(series, start, end)
    if not days:
        first = min(bars[0].date for bars in series.values())
        last = max(bars[-1].date for bars in series.values())
        raise ValueError(
            f"백테스트 기간({_describe_period(start, end)})에 해당하는 일봉이 없습니다. "
            f"가지고 있는 데이터는 {first} ~ {last} 입니다"
        )

    display_names = dict(names or {})
    clock = _SimClock(days[0])
    broker = _DailyBarBroker(costs.slippage_rate)
    store = MemoryStore()
    core = TradingCore(
        strategy=strategy,
        universe=symbols,
        risk=risk,
        costs=costs,
        broker=broker,
        store=store,
        clock=clock,
        name_of=lambda sym: display_names.get(sym, sym),
        enforce_drawdown_halt=False,
    )

    total = len(days)
    progress_step = max(1, math.ceil(total / _MAX_PROGRESS_CALLS))
    cursor = {sym: 0 for sym in symbols}    # 종목별: 오늘 이전 일봉의 개수 (= 오늘 봉이 있을 위치)
    for done, day in enumerate(days, start=1):
        histories: dict[str, list[Bar]] = {}
        today: dict[str, Bar] = {}
        for sym in symbols:
            bars = series[sym]
            k = cursor[sym]
            while k < len(bars) and bars[k].date < day:
                k += 1
            cursor[sym] = k
            histories[sym] = bars[:k]           # 오늘 이전 봉만 — 전략이 볼 수 있는 전부
            if k < len(bars) and bars[k].date == day:
                today[sym] = bars[k]
        broker.tradable = frozenset(today)

        clock.set(day, _OPEN_TIME)
        core.start_day(day, histories)
        core.on_open({sym: bar.open for sym, bar in today.items()})

        clock.set(day, _INTRADAY_TIME)
        for sym, bar in today.items():          # today 는 universe 순서로 채워져 있습니다
            _replay_intraday(core, sym, bar)

        closes = {sym: bar.close for sym, bar in today.items()}
        clock.set(day, _CLOSE_TIME)
        core.on_close(closes)
        clock.set(day, _END_TIME)
        core.end_day(closes, {sym: bar.high for sym, bar in today.items()})

        if progress is not None and (done % progress_step == 0 or done == total):
            progress(done, total)

    history = store.equity_history()
    equity_curve = [(day, equity) for day, equity, _ in history]
    cash_curve = [(day, cash) for day, _, cash in history]
    bench = benchmark_curve(series, symbols, days, float(risk.capital))
    orders = store.orders()
    return BacktestResult(
        strategy_name=strategy.name or type(strategy).__name__,
        strategy_params=dict(strategy.params),
        symbols=symbols,
        start=days[0],
        end=days[-1],
        initial_capital=float(risk.capital),
        equity_curve=equity_curve,
        cash_curve=cash_curve,
        benchmark_curve=bench,
        orders=orders,
        final_positions=core.snapshot()["positions"],
        metrics=compute_metrics(equity_curve, orders, float(risk.capital), bench, cash_curve),
        names=display_names,
    )

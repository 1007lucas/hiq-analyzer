"""성과 지표 계산.

백테스트(또는 실전 운용)의 **일별 평가금 곡선**과 **주문 기록**을 사람이 읽는
성과 지표로 바꿉니다. 이 모듈의 함수는 모두 순수 함수입니다 — 같은 입력이면
항상 같은 결과가 나오고, 시계·난수·네트워크를 쓰지 않습니다.

용어와 계산 기준
----------------
* 일간 수익률   : 오늘 평가금 / 어제 평가금 - 1. 첫날의 '어제'는 초기 자금입니다.
* 연환산(CAGR)  : (최종/초기) ** (365.25 / 달력 일수) - 1.
                  기간이 30일보다 짧으면 연환산이 터무니없는 숫자가 되므로 총수익률을 그대로 씁니다.
* 최대낙폭(MDD) : 그때까지의 최고 평가금 대비 가장 크게 떨어진 비율 (음수, 예: -0.23 = -23%).
                  초기 자금도 '최고점' 후보에 포함합니다 (첫날부터 손실이면 그것도 낙폭).
* 변동성        : 일간 수익률의 표본 표준편차 × √252.
* 샤프지수      : 일간 수익률 평균 / 표준편차 × √252 (무위험 수익률 0 가정).
* 거래          : 체결된 매도 주문 1건 = 거래 1회 (손익은 매수·매도 비용을 모두 뺀 값).
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Mapping, Sequence

TRADING_DAYS_PER_YEAR = 252     # 변동성·샤프지수 연환산에 쓰는 1년 거래일 수
DAYS_PER_YEAR = 365.25          # CAGR 연환산에 쓰는 1년 달력 일수
MIN_ANNUALIZE_DAYS = 30         # 이보다 짧은 기간은 연환산하지 않음
_EXPOSURE_EPS = 1e-6            # 현금과 평가금이 '같다'고 볼 오차 (부동소수점 잡음 무시)
_ZERO_STDEV = 1e-12             # 이보다 작은 표준편차는 0 으로 봄 (샤프지수 폭주 방지)

Curve = Sequence[tuple[date, float]]


@dataclass(frozen=True)
class Metrics:
    """성과 지표 묶음. 비율은 모두 소수입니다 (0.05 = 5%)."""

    start: date                     # 첫 거래일
    end: date                       # 마지막 거래일
    trading_days: int               # 거래일 수 (평가금 기록 수)
    initial_capital: float          # 초기 자금 (원)
    final_equity: float             # 최종 평가금 (원)
    total_return: float             # 총수익률
    cagr: float                     # 연환산수익률
    max_drawdown: float             # 최대낙폭 (음수, 낙폭이 없으면 0.0)
    max_drawdown_peak: date         # 최대낙폭이 시작된 고점 날짜 (낙폭이 없으면 첫 거래일)
    max_drawdown_trough: date       # 최대낙폭의 저점 날짜 (낙폭이 없으면 첫 거래일)
    volatility: float               # 연환산 변동성
    sharpe: float                   # 샤프지수 (변동성이 0 이면 0.0)
    num_trades: int                 # 거래횟수 (체결된 매도 주문 수)
    num_wins: int                   # 수익 거래 수
    win_rate: float                 # 승률 (거래가 없으면 0.0)
    profit_factor: float            # 총이익 / 총손실 (손실 거래가 없으면 inf, 거래가 없으면 0.0)
    avg_win_pct: float              # 수익 거래의 평균 수익률
    avg_loss_pct: float             # 손실 거래의 평균 수익률 (음수)
    best_trade_pct: float           # 가장 좋았던 거래의 수익률
    worst_trade_pct: float          # 가장 나빴던 거래의 수익률
    avg_holding_days: float         # 평균 보유기간 (달력 일수)
    total_fees: float               # 수수료 합계 (원)
    total_taxes: float              # 거래세 합계 (원)
    exposure: float                 # 시장 노출도: 장 마감 시 주식을 들고 있던 날의 비율
    benchmark_return: float         # 단순보유(벤치마크) 총수익률
    benchmark_cagr: float           # 단순보유 연환산수익률
    benchmark_max_drawdown: float   # 단순보유 최대낙폭 (음수)


# --------------------------------------------------------------------------- #
# 평가금 곡선에서 나오는 지표
# --------------------------------------------------------------------------- #
def annualized_return(growth: float, calendar_days: int) -> float:
    """성장 배수(최종/초기)를 연환산수익률로 바꿉니다.

    * 기간이 30일 미만이면 연환산하지 않고 (배수 - 1) 을 그대로 돌려줍니다.
    * 자금을 전부 잃었으면(배수 <= 0) -100% 입니다. 음수의 거듭제곱은 복소수가 되므로 따로 처리합니다.
    """
    if growth <= 0:
        return -1.0
    if calendar_days < MIN_ANNUALIZE_DAYS:
        return growth - 1.0
    try:
        return growth ** (DAYS_PER_YEAR / calendar_days) - 1.0
    except OverflowError:   # 짧은 기간에 수천 배가 된 비현실적 입력
        return math.inf


def daily_returns(values: Sequence[float], initial_capital: float) -> list[float]:
    """일간 수익률 목록. 첫날은 초기 자금 대비입니다. 전날 평가금이 0 이하면 그날은 0 으로 둡니다."""
    out: list[float] = []
    prev = initial_capital
    for v in values:
        out.append(v / prev - 1.0 if prev > 0 else 0.0)
        prev = v
    return out


def drawdown_series(curve: Curve, initial_capital: float) -> list[tuple[date, float]]:
    """날짜별 낙폭 (그때까지의 최고 평가금 대비 하락률, 0 이하)."""
    out: list[tuple[date, float]] = []
    peak = initial_capital
    for day, value in curve:
        peak = max(peak, value)
        out.append((day, value / peak - 1.0 if peak > 0 else 0.0))
    return out


def max_drawdown(curve: Curve, initial_capital: float) -> tuple[float, date, date]:
    """(최대낙폭, 고점 날짜, 저점 날짜).

    고점이 '초기 자금'(첫 거래일 장 시작 전)인 경우 고점 날짜는 첫 거래일로 표시합니다.
    같은 높이의 고점이 여러 번이면 가장 최근 날짜를 고점으로 봅니다 (낙폭이 실제로 시작된 날).
    """
    if not curve:
        raise ValueError("평가금 기록이 없어 낙폭을 계산할 수 없습니다")
    first_day = curve[0][0]
    peak, peak_day = initial_capital, first_day
    worst, worst_peak_day, trough_day = 0.0, first_day, first_day
    for day, value in curve:
        if value >= peak:
            peak, peak_day = value, day
        drawdown = value / peak - 1.0 if peak > 0 else 0.0
        if drawdown < worst:
            worst, worst_peak_day, trough_day = drawdown, peak_day, day
    return worst, worst_peak_day, trough_day


def monthly_returns(curve: Curve, initial_capital: float) -> dict[int, dict[int, float]]:
    """{연도: {월: 그 달의 수익률}}. 각 달은 전달 마지막 평가금(첫 달은 초기 자금) 대비입니다."""
    return _period_returns(curve, initial_capital, lambda d: (d.year, d.month))


def yearly_returns(curve: Curve, initial_capital: float) -> dict[int, float]:
    """{연도: 그 해의 수익률}. 각 해는 전년도 마지막 평가금(첫 해는 초기 자금) 대비입니다."""
    by_year = _period_returns(curve, initial_capital, lambda d: (d.year, 0))
    return {year: months[0] for year, months in by_year.items()}


def _period_returns(
    curve: Curve, initial_capital: float, key: Callable[[date], tuple[int, int]]
) -> dict[int, dict[int, float]]:
    """곡선을 key(날짜) → (연도, 하위구간) 로 묶어, 구간 마지막 값끼리의 수익률을 구합니다.

    curve 는 날짜순이어야 합니다 (구간의 순서와 '마지막 값'을 입력 순서로 판단합니다).
    """
    last_value: dict[tuple[int, int], float] = {}
    for day, value in curve:            # 날짜순이므로 같은 구간의 마지막 값이 남습니다
        last_value[key(day)] = value
    out: dict[int, dict[int, float]] = {}
    prev = initial_capital
    for (year, sub), value in last_value.items():
        out.setdefault(year, {})[sub] = value / prev - 1.0 if prev > 0 else 0.0
        prev = value
    return out


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _sample_stdev(xs: Sequence[float]) -> float:
    """표본 표준편차 (n-1). 값이 2개 미만이면 0."""
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _volatility_and_sharpe(returns: Sequence[float]) -> tuple[float, float]:
    stdev = _sample_stdev(returns)
    if stdev < _ZERO_STDEV:
        return 0.0, 0.0
    annual = math.sqrt(TRADING_DAYS_PER_YEAR)
    return stdev * annual, _mean(returns) / stdev * annual


def _exposure(curve: Curve, cash_curve: Curve | None) -> float:
    """장 마감 시 주식을 들고 있던 날의 비율 (현금 < 평가금 인 날)."""
    if not cash_curve:
        return 0.0
    cash_by_day = dict(cash_curve)
    pairs = [(value, cash_by_day[day]) for day, value in curve if day in cash_by_day]
    if not pairs:
        return 0.0
    return sum(1 for value, cash in pairs if cash < value - _EXPOSURE_EPS) / len(pairs)


# --------------------------------------------------------------------------- #
# 주문 기록에서 나오는 지표
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _TradeStats:
    num_trades: int
    num_wins: int
    win_rate: float
    profit_factor: float
    avg_win_pct: float
    avg_loss_pct: float
    best_trade_pct: float
    worst_trade_pct: float
    avg_holding_days: float


def _num(value: Any) -> float:
    """주문 기록의 숫자 칸 (비어 있으면 0)."""
    return float(value) if value is not None else 0.0


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return None


def _holding_days(order: Mapping[str, Any]) -> int | None:
    entry, exit_ = _as_date(order.get("entry_day")), _as_date(order.get("day"))
    if entry is None or exit_ is None:
        return None
    return (exit_ - entry).days


def _trade_stats(orders: Sequence[Mapping[str, Any]]) -> _TradeStats:
    sells = [o for o in orders if o.get("side") == "sell" and _num(o.get("filled_qty")) > 0]
    if not sells:
        return _TradeStats(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    pnls = [_num(o.get("pnl")) for o in sells]
    pcts = [_num(o.get("pnl_pct")) for o in sells]
    win_pcts = [pct for pnl, pct in zip(pnls, pcts) if pnl > 0]
    loss_pcts = [pct for pnl, pct in zip(pnls, pcts) if pnl < 0]
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = math.inf if gross_profit > 0 else 0.0
    holdings = [h for h in map(_holding_days, sells) if h is not None]
    return _TradeStats(
        num_trades=len(sells),
        num_wins=len(win_pcts),
        win_rate=len(win_pcts) / len(sells),
        profit_factor=profit_factor,
        avg_win_pct=_mean(win_pcts),
        avg_loss_pct=_mean(loss_pcts),
        best_trade_pct=max(pcts),
        worst_trade_pct=min(pcts),
        avg_holding_days=_mean(holdings),
    )


# --------------------------------------------------------------------------- #
# 종합
# --------------------------------------------------------------------------- #
def compute_metrics(
    equity_curve: Curve,
    orders: Sequence[Mapping[str, Any]],
    initial_capital: float,
    benchmark_curve: Curve | None = None,
    cash_curve: Curve | None = None,
) -> Metrics:
    """평가금 곡선과 주문 기록으로 성과 지표를 계산합니다.

    equity_curve    : [(날짜, 장 마감 평가금)] — 최소 1일
    orders          : 주문 기록 dict 목록 (state.ORDER_FIELDS 형식)
    initial_capital : 초기 자금 (0보다 커야 함)
    benchmark_curve : 비교 대상(단순보유) 곡선. 없으면 벤치마크 지표는 0.0
    cash_curve      : [(날짜, 장 마감 현금)]. 없으면 시장 노출도는 0.0
    """
    if not equity_curve:
        raise ValueError("평가금 기록이 하루도 없어 성과를 계산할 수 없습니다")
    if not (math.isfinite(initial_capital) and initial_capital > 0):
        raise ValueError(f"초기 자금은 0보다 큰 숫자여야 합니다 (입력값: {initial_capital})")

    curve = sorted(equity_curve, key=lambda point: point[0])
    start, end = curve[0][0], curve[-1][0]
    final_equity = curve[-1][1]
    growth = final_equity / initial_capital
    worst, peak_day, trough_day = max_drawdown(curve, initial_capital)
    volatility, sharpe = _volatility_and_sharpe(daily_returns([v for _, v in curve], initial_capital))
    trades = _trade_stats(orders)

    bench_return = bench_cagr = bench_mdd = 0.0
    if benchmark_curve:
        bench = sorted(benchmark_curve, key=lambda point: point[0])
        bench_growth = bench[-1][1] / initial_capital
        bench_return = bench_growth - 1.0
        bench_cagr = annualized_return(bench_growth, (bench[-1][0] - bench[0][0]).days)
        bench_mdd = max_drawdown(bench, initial_capital)[0]

    return Metrics(
        start=start,
        end=end,
        trading_days=len(curve),
        initial_capital=float(initial_capital),
        final_equity=final_equity,
        total_return=growth - 1.0,
        cagr=annualized_return(growth, (end - start).days),
        max_drawdown=worst,
        max_drawdown_peak=peak_day,
        max_drawdown_trough=trough_day,
        volatility=volatility,
        sharpe=sharpe,
        num_trades=trades.num_trades,
        num_wins=trades.num_wins,
        win_rate=trades.win_rate,
        profit_factor=trades.profit_factor,
        avg_win_pct=trades.avg_win_pct,
        avg_loss_pct=trades.avg_loss_pct,
        best_trade_pct=trades.best_trade_pct,
        worst_trade_pct=trades.worst_trade_pct,
        avg_holding_days=trades.avg_holding_days,
        total_fees=sum(_num(o.get("fee")) for o in orders),
        total_taxes=sum(_num(o.get("tax")) for o in orders),
        exposure=_exposure(curve, cash_curve),
        benchmark_return=bench_return,
        benchmark_cagr=bench_cagr,
        benchmark_max_drawdown=bench_mdd,
    )


# --------------------------------------------------------------------------- #
# 콘솔 출력
# --------------------------------------------------------------------------- #
def format_signed_pct(value: float) -> str:
    """부호가 붙은 퍼센트 (소수 둘째 자리). 예: +12.34%"""
    return f"{value * 100:+.2f}%"


def format_pct(value: float) -> str:
    """부호 없는 퍼센트 (소수 둘째 자리). 예: 12.34%"""
    return f"{value * 100:.2f}%"


def format_won(value: float) -> str:
    """원 단위 금액 (천 단위 쉼표). 예: 1,234,567원"""
    return f"{value:,.0f}원"


def format_profit_factor(value: float) -> str:
    """손익비. 손실 거래가 하나도 없으면 숫자 대신 말로 풀어 씁니다."""
    return "무한대 (손실 거래 없음)" if math.isinf(value) else f"{value:.2f}"


def _display_width(text: str) -> int:
    """터미널에서 차지하는 칸 수. 한글은 2칸을 차지하므로 len() 으로는 줄이 맞지 않습니다."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def format_metrics(m: Metrics) -> str:
    """콘솔에 찍을 여러 줄짜리 요약 (라벨 정렬, 퍼센트는 소수 둘째 자리, 금액은 천 단위 쉼표)."""
    rows: list[tuple[str, str]] = [
        ("기간", f"{m.start} ~ {m.end} ({m.trading_days:,}거래일)"),
        ("초기 자금", format_won(m.initial_capital)),
        ("최종 평가금", format_won(m.final_equity)),
        ("총수익률", format_signed_pct(m.total_return)),
        ("연환산수익률(CAGR)", format_signed_pct(m.cagr)),
        ("최대낙폭(MDD)", f"{format_pct(m.max_drawdown)} ({m.max_drawdown_peak} ~ {m.max_drawdown_trough})"),
        ("연환산 변동성", format_pct(m.volatility)),
        ("샤프지수", f"{m.sharpe:.2f}"),
        ("거래횟수", f"{m.num_trades:,}회 (수익 거래 {m.num_wins:,}회)"),
        ("승률", format_pct(m.win_rate)),
        ("손익비(총이익/총손실)", format_profit_factor(m.profit_factor)),
        ("평균 수익 거래", format_signed_pct(m.avg_win_pct)),
        ("평균 손실 거래", format_signed_pct(m.avg_loss_pct)),
        ("최고 / 최악 거래", f"{format_signed_pct(m.best_trade_pct)} / {format_signed_pct(m.worst_trade_pct)}"),
        ("평균 보유기간", f"{m.avg_holding_days:.1f}일"),
        ("총 수수료", format_won(m.total_fees)),
        ("총 거래세", format_won(m.total_taxes)),
        ("시장 노출도", format_pct(m.exposure)),
        ("단순보유 총수익률", format_signed_pct(m.benchmark_return)),
        ("단순보유 연환산수익률", format_signed_pct(m.benchmark_cagr)),
        ("단순보유 최대낙폭", format_pct(m.benchmark_max_drawdown)),
    ]
    width = max(_display_width(label) for label, _ in rows)
    return "\n".join(f"{label}{' ' * (width - _display_width(label))} : {value}" for label, value in rows)

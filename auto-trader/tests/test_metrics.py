"""성과 지표 테스트 — 작은 곡선에서 손으로 계산한 값과 비교합니다."""

from __future__ import annotations

import math
import unicodedata
from datetime import date, timedelta

import pytest

from autotrader.backtest.metrics import (
    Metrics,
    annualized_return,
    compute_metrics,
    daily_returns,
    drawdown_series,
    format_metrics,
    max_drawdown,
    monthly_returns,
    yearly_returns,
)

J2, J3, J4, J5, J8 = (date(2024, 1, d) for d in (2, 3, 4, 5, 8))

# 초기 자금 100만원에서 +10%, +10%, −20%, +10%, +10%
CURVE = [(J2, 1_100_000.0), (J3, 1_210_000.0), (J4, 968_000.0), (J5, 1_064_800.0), (J8, 1_171_280.0)]


def sell(pnl: float, pct: float, entry: str, day: str, fee: float = 0.0, tax: float = 0.0) -> dict:
    return {"side": "sell", "filled_qty": 10, "pnl": pnl, "pnl_pct": pct, "entry_day": entry, "day": day,
            "fee": fee, "tax": tax}


def buy(fee: float = 0.0, filled_qty: int = 10) -> dict:
    return {"side": "buy", "filled_qty": filled_qty, "pnl": None, "pnl_pct": None, "entry_day": None,
            "day": "2024-01-02", "fee": fee, "tax": 0.0}


# --------------------------------------------------------------------------- #
# 수익률 / 낙폭 / 변동성
# --------------------------------------------------------------------------- #
def test_return_drawdown_volatility_and_sharpe_on_a_small_curve():
    m = compute_metrics(CURVE, [], 1_000_000)
    assert isinstance(m, Metrics)
    assert (m.start, m.end, m.trading_days) == (J2, J8, 5)
    assert m.initial_capital == 1_000_000 and m.final_equity == 1_171_280
    assert m.total_return == pytest.approx(0.17128)
    assert m.cagr == pytest.approx(0.17128)                     # 6일짜리 기간은 연환산하지 않음
    assert m.max_drawdown == pytest.approx(-0.20)               # 1,210,000 → 968,000
    assert (m.max_drawdown_peak, m.max_drawdown_trough) == (J3, J4)
    # 일간 수익률 평균 0.04, 편차제곱합 4×0.06² + 0.24² = 0.072 → 표본분산 0.018
    assert m.volatility == pytest.approx(math.sqrt(0.018 * 252))
    assert m.volatility == pytest.approx(2.129789, abs=1e-6)
    assert m.sharpe == pytest.approx(0.04 * math.sqrt(252 / 0.018))
    assert m.sharpe == pytest.approx(4.732864, abs=1e-6)


def test_daily_returns_use_initial_capital_before_the_first_day():
    assert daily_returns([1_100_000, 1_210_000, 968_000], 1_000_000) == pytest.approx([0.10, 0.10, -0.20])
    assert daily_returns([], 1_000_000) == []
    assert daily_returns([0.0, 100.0], 1_000_000) == [-1.0, 0.0]    # 전날 평가금이 0 이면 계산 불가 → 0


def test_cagr_annualises_by_calendar_days():
    one_year = [(date(2023, 1, 2), 1_000_000.0), (date(2024, 1, 2), 1_210_000.0)]      # 365일
    m = compute_metrics(one_year, [], 1_000_000)
    assert m.total_return == pytest.approx(0.21)
    assert m.cagr == pytest.approx(1.21 ** (365.25 / 365) - 1)
    assert m.cagr == pytest.approx(0.210158, abs=1e-6)

    two_years = [(date(2022, 1, 3), 1_000_000.0), (date(2024, 1, 3), 1_440_000.0)]     # 730일
    m = compute_metrics(two_years, [], 1_000_000)
    assert m.total_return == pytest.approx(0.44)
    assert m.cagr == pytest.approx(0.20015, abs=1e-5)           # 대략 연 20%

    loss = [(date(2022, 1, 3), 1_000_000.0), (date(2024, 1, 3), 640_000.0)]
    assert compute_metrics(loss, [], 1_000_000).cagr == pytest.approx(-0.19990, abs=1e-5)


def test_cagr_equals_total_return_for_spans_shorter_than_30_days():
    start = date(2024, 1, 2)
    short = [(start, 1_000_000.0), (start + timedelta(days=29), 1_100_000.0)]
    assert compute_metrics(short, [], 1_000_000).cagr == pytest.approx(0.10)
    month = [(start, 1_000_000.0), (start + timedelta(days=30), 1_100_000.0)]
    assert compute_metrics(month, [], 1_000_000).cagr == pytest.approx(1.1 ** (365.25 / 30) - 1)
    assert annualized_return(1.1, 0) == pytest.approx(0.10)
    assert annualized_return(1e30, 30) == math.inf               # 계산 범위를 넘는 비현실적 입력도 예외 없이


def test_drawdown_counts_a_loss_on_the_very_first_day():
    curve = [(J2, 900_000.0), (J3, 950_000.0), (J4, 990_000.0)]
    m = compute_metrics(curve, [], 1_000_000)
    assert m.max_drawdown == pytest.approx(-0.10)               # 초기 자금 100만 → 90만
    assert (m.max_drawdown_peak, m.max_drawdown_trough) == (J2, J2)
    assert [dd for _, dd in drawdown_series(curve, 1_000_000)] == pytest.approx([-0.10, -0.05, -0.01])


def test_no_drawdown_reports_zero_and_the_first_day():
    rising = [(J2, 1_010_000.0), (J3, 1_020_000.0), (J4, 1_020_000.0), (J5, 1_050_000.0)]
    m = compute_metrics(rising, [], 1_000_000)
    assert m.max_drawdown == 0.0
    assert (m.max_drawdown_peak, m.max_drawdown_trough) == (J2, J2)
    assert all(dd == 0.0 for _, dd in drawdown_series(rising, 1_000_000))


def test_drawdown_peak_is_the_most_recent_day_at_the_high():
    curve = [(J2, 1_100_000.0), (J3, 1_000_000.0), (J4, 1_100_000.0), (J5, 990_000.0)]
    worst, peak, trough = max_drawdown(curve, 1_000_000)
    assert worst == pytest.approx(-0.10)                        # 110만 → 99만
    assert (peak, trough) == (J4, J5)                           # 고점을 회복한 J4 부터 다시 시작된 낙폭
    with pytest.raises(ValueError, match="평가금 기록이 없어"):
        max_drawdown([], 1_000_000)


def test_drawdown_series_matches_the_running_peak():
    assert [dd for _, dd in drawdown_series(CURVE, 1_000_000)] == pytest.approx([0.0, 0.0, -0.20, -0.12, -0.032])
    assert [d for d, _ in drawdown_series(CURVE, 1_000_000)] == [J2, J3, J4, J5, J8]


def test_monthly_and_yearly_returns():
    curve = [
        (date(2023, 11, 30), 1_100_000.0),
        (date(2023, 12, 15), 1_050_000.0),
        (date(2023, 12, 29), 1_210_000.0),
        (date(2024, 1, 31), 1_089_000.0),
    ]
    monthly = monthly_returns(curve, 1_000_000)
    assert set(monthly) == {2023, 2024}
    assert monthly[2023] == pytest.approx({11: 0.10, 12: 0.10})     # 11월은 초기 자금 대비, 12월은 11월 말 대비
    assert monthly[2024] == pytest.approx({1: -0.10})
    assert yearly_returns(curve, 1_000_000) == pytest.approx({2023: 0.21, 2024: -0.10})
    assert monthly_returns([], 1_000_000) == {} and yearly_returns([], 1_000_000) == {}


# --------------------------------------------------------------------------- #
# 거래 통계
# --------------------------------------------------------------------------- #
def test_trade_statistics():
    orders = [
        buy(fee=100),
        sell(30_000, 0.03, "2024-01-02", "2024-01-05", fee=150, tax=600),       # 3일 보유
        buy(fee=100),
        sell(-10_000, -0.01, "2024-01-08", "2024-01-09", fee=140, tax=580),     # 1일 보유
        buy(fee=100),
        sell(5_000, 0.005, "2024-01-10", "2024-01-10", fee=145, tax=590),       # 당일 청산
        {**sell(0.0, 0.0, "2024-01-10", "2024-01-11"), "filled_qty": 0, "pnl": None, "pnl_pct": None},   # 거부된 매도
        buy(filled_qty=0),                                                      # 거부된 매수
    ]
    m = compute_metrics(CURVE, orders, 1_000_000)
    assert (m.num_trades, m.num_wins) == (3, 2)
    assert m.win_rate == pytest.approx(2 / 3)
    assert m.profit_factor == pytest.approx(3.5)                # 35,000 / 10,000
    assert m.avg_win_pct == pytest.approx(0.0175)
    assert m.avg_loss_pct == pytest.approx(-0.01)
    assert (m.best_trade_pct, m.worst_trade_pct) == (0.03, -0.01)
    assert m.avg_holding_days == pytest.approx(4 / 3)
    assert m.total_fees == pytest.approx(735)                   # 매수·매도 수수료 모두
    assert m.total_taxes == pytest.approx(1_770)


def test_profit_factor_edge_cases():
    only_wins = [sell(10_000, 0.01, "2024-01-02", "2024-01-03"), sell(5_000, 0.005, "2024-01-03", "2024-01-04")]
    m = compute_metrics(CURVE, only_wins, 1_000_000)
    assert m.profit_factor == math.inf and m.win_rate == 1.0
    assert m.avg_loss_pct == 0.0 and m.worst_trade_pct == 0.005

    only_losses = [sell(-10_000, -0.01, "2024-01-02", "2024-01-03")]
    m = compute_metrics(CURVE, only_losses, 1_000_000)
    assert m.profit_factor == 0.0 and m.win_rate == 0.0 and m.num_wins == 0
    assert m.avg_win_pct == 0.0 and m.best_trade_pct == -0.01

    break_even = [sell(0.0, 0.0, "2024-01-02", "2024-01-03")]
    m = compute_metrics(CURVE, break_even, 1_000_000)
    assert (m.num_trades, m.num_wins, m.profit_factor) == (1, 0, 0.0)   # 본전은 수익도 손실도 아님


def test_no_orders_gives_zero_trade_statistics():
    m = compute_metrics(CURVE, [], 1_000_000)
    assert (m.num_trades, m.num_wins, m.win_rate, m.profit_factor) == (0, 0, 0.0, 0.0)
    assert (m.avg_win_pct, m.avg_loss_pct, m.best_trade_pct, m.worst_trade_pct, m.avg_holding_days) == (0.0,) * 5
    assert (m.total_fees, m.total_taxes) == (0.0, 0.0)
    # 매수만 있고 아직 팔지 않은 경우도 거래 0회
    assert compute_metrics(CURVE, [buy(fee=50)], 1_000_000).num_trades == 0


def test_sell_without_entry_information_still_counts_as_a_trade():
    orphan = {"side": "sell", "filled_qty": 5, "pnl": None, "pnl_pct": None, "entry_day": None,
              "day": "2024-01-03", "fee": 10.0, "tax": 20.0}
    m = compute_metrics(CURVE, [orphan], 1_000_000)
    assert (m.num_trades, m.num_wins, m.avg_holding_days) == (1, 0, 0.0)


# --------------------------------------------------------------------------- #
# 시장 노출도 / 벤치마크
# --------------------------------------------------------------------------- #
def test_exposure_is_the_share_of_days_holding_stock_at_the_close():
    equity = [(J2, 1_000_000.0), (J3, 1_010_000.0), (J4, 1_005_000.0), (J5, 1_005_000.0)]
    cash = [(J2, 1_000_000.0), (J3, 700_000.0), (J4, 1_005_000.0), (J5, 1_004_999.9999995)]
    assert compute_metrics(equity, [], 1_000_000, cash_curve=cash).exposure == pytest.approx(0.25)   # J3 하루
    assert compute_metrics(equity, [], 1_000_000).exposure == 0.0                                    # 현금 기록 없음
    assert compute_metrics(equity, [], 1_000_000, cash_curve=[]).exposure == 0.0
    always = [(d, 0.0) for d, _ in equity]
    assert compute_metrics(equity, [], 1_000_000, cash_curve=always).exposure == 1.0


def test_benchmark_metrics():
    bench = [(J2, 1_000_000.0), (J3, 1_200_000.0), (J4, 900_000.0), (J5, 1_080_000.0), (J8, 1_080_000.0)]
    m = compute_metrics(CURVE, [], 1_000_000, benchmark_curve=bench)
    assert m.benchmark_return == pytest.approx(0.08)
    assert m.benchmark_cagr == pytest.approx(0.08)
    assert m.benchmark_max_drawdown == pytest.approx(-0.25)     # 120만 → 90만
    none = compute_metrics(CURVE, [], 1_000_000)
    assert (none.benchmark_return, none.benchmark_cagr, none.benchmark_max_drawdown) == (0.0, 0.0, 0.0)


# --------------------------------------------------------------------------- #
# 극단적인 입력
# --------------------------------------------------------------------------- #
def test_single_day_curve():
    m = compute_metrics([(J2, 1_050_000.0)], [], 1_000_000)
    assert (m.start, m.end, m.trading_days) == (J2, J2, 1)
    assert m.total_return == pytest.approx(0.05) and m.cagr == pytest.approx(0.05)
    assert (m.volatility, m.sharpe, m.max_drawdown) == (0.0, 0.0, 0.0)


def test_flat_curve_has_no_volatility_and_zero_sharpe():
    flat = [(J2 + timedelta(days=i), 1_000_000.0) for i in range(40)]
    m = compute_metrics(flat, [], 1_000_000)
    assert (m.total_return, m.cagr, m.volatility, m.sharpe, m.max_drawdown) == (0.0, 0.0, 0.0, 0.0, 0.0)


def test_perfectly_steady_growth_does_not_produce_an_absurd_sharpe():
    value, steady = 1_000_000.0, []
    for i in range(60):
        value *= 1.001
        steady.append((J2 + timedelta(days=i), value))
    m = compute_metrics(steady, [], 1_000_000)
    assert m.volatility == 0.0 and m.sharpe == 0.0              # 표준편차가 사실상 0 → 샤프지수는 0 으로 표시
    assert m.total_return == pytest.approx(1.001 ** 60 - 1)


def test_equity_at_or_below_zero_does_not_crash():
    wiped = [(J2, 500_000.0), (J3, 0.0), (J4, 0.0)]
    m = compute_metrics(wiped, [], 1_000_000)
    assert m.total_return == -1.0 and m.cagr == -1.0 and m.max_drawdown == -1.0
    assert (m.max_drawdown_peak, m.max_drawdown_trough) == (J2, J3)
    assert math.isfinite(m.volatility) and math.isfinite(m.sharpe)

    long_wiped = [(date(2023, 1, 2), 500_000.0), (date(2024, 1, 2), -100.0)]
    m = compute_metrics(long_wiped, [], 1_000_000)
    assert m.cagr == -1.0 and isinstance(m.cagr, float)         # 음수의 거듭제곱(복소수)이 나오면 안 됨
    assert m.total_return == pytest.approx(-1.0001)
    assert format_metrics(m)                                    # 출력도 예외 없이


def test_invalid_inputs_raise_korean_errors():
    with pytest.raises(ValueError, match="평가금 기록이 하루도 없어"):
        compute_metrics([], [], 1_000_000)
    for bad in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="초기 자금"):
            compute_metrics(CURVE, [], bad)


def test_unsorted_curves_are_sorted_by_date():
    shuffled = [CURVE[3], CURVE[0], CURVE[4], CURVE[2], CURVE[1]]
    assert compute_metrics(shuffled, [], 1_000_000) == compute_metrics(CURVE, [], 1_000_000)


# --------------------------------------------------------------------------- #
# 콘솔 출력
# --------------------------------------------------------------------------- #
def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def test_format_metrics_has_korean_labels_aligned_values_and_number_formats():
    orders = [sell(30_000, 0.03, "2024-01-02", "2024-01-05", fee=1_234.5, tax=2_345.6),
              sell(-10_000, -0.01, "2024-01-08", "2024-01-09")]
    bench = [(J2, 1_000_000.0), (J8, 1_080_000.0)]
    cash = [(d, v) for d, v in CURVE[:-1]] + [(J8, 500_000.0)]
    text = format_metrics(compute_metrics(CURVE, orders, 1_000_000, bench, cash))
    lines = text.splitlines()
    assert len(lines) >= 15

    for label in ("기간", "초기 자금", "최종 평가금", "총수익률", "연환산수익률(CAGR)", "최대낙폭(MDD)",
                  "변동성", "샤프지수", "거래횟수", "승률", "손익비", "평균 보유기간", "총 수수료", "총 거래세",
                  "시장 노출도", "단순보유"):
        assert any(line.startswith(label) for line in lines), label

    row = {line.split(" : ")[0].strip(): line.split(" : ", 1)[1] for line in lines}
    assert row["기간"] == "2024-01-02 ~ 2024-01-08 (5거래일)"
    assert row["초기 자금"] == "1,000,000원"                    # 천 단위 쉼표
    assert row["최종 평가금"] == "1,171,280원"
    assert row["총수익률"] == "+17.13%"                          # 소수 둘째 자리, 부호 표시
    assert row["최대낙폭(MDD)"] == "-20.00% (2024-01-03 ~ 2024-01-04)"
    assert row["샤프지수"] == "4.73"
    assert row["거래횟수"] == "2회 (수익 거래 1회)"
    assert row["승률"] == "50.00%"
    assert row["총 수수료"] == "1,234원" and row["총 거래세"] == "2,346원"
    assert row["시장 노출도"] == "20.00%"
    assert row["단순보유 총수익률"] == "+8.00%"

    # 한글은 터미널에서 2칸을 차지하므로 '화면 폭' 기준으로 구분자 위치가 같아야 줄이 맞습니다.
    columns = {display_width(line.split(" : ")[0]) for line in lines}
    assert len(columns) == 1
    text.encode("cp949")                                        # 한국어 Windows 콘솔에서도 깨지지 않는 글자만 사용


def test_format_metrics_spells_out_an_infinite_profit_factor():
    m = compute_metrics(CURVE, [sell(10_000, 0.01, "2024-01-02", "2024-01-03")], 1_000_000)
    text = format_metrics(m)
    assert "무한대 (손실 거래 없음)" in text and "inf" not in text
    text.encode("cp949")

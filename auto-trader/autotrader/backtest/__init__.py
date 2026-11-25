"""백테스트: 과거 일봉으로 전략을 모의 운용하고 성과를 계산합니다."""

from .engine import BacktestResult, benchmark_curve, run_backtest
from .metrics import Metrics, compute_metrics, format_metrics
from .report import render_html_report, write_html_report, write_trades_csv

__all__ = [
    "BacktestResult",
    "Metrics",
    "benchmark_curve",
    "compute_metrics",
    "format_metrics",
    "render_html_report",
    "run_backtest",
    "write_html_report",
    "write_trades_csv",
]

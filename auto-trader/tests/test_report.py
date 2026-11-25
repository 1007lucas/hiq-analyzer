"""백테스트 리포트(HTML/CSV) 테스트."""

from __future__ import annotations

import csv
import re
from datetime import date
from html.parser import HTMLParser

from autotrader.backtest import render_html_report, run_backtest, write_html_report, write_trades_csv
from autotrader.config import CostConfig, RiskConfig
from autotrader.data import generate_bars
from autotrader.strategies import create_strategy
from autotrader.strategies.base import DayPlan

from conftest import ScriptedStrategy

RISK = RiskConfig(capital=10_000_000, max_positions=2, position_pct=0.4, stop_loss_pct=0.05)
COSTS = CostConfig()


def result(strategy=None, start=date(2022, 1, 1), end=date(2024, 6, 30), names=None, symbols=("005930", "000660")):
    data = {s: generate_bars(s, date(2021, 6, 1), end) for s in symbols}
    return run_backtest(data=data, strategy=strategy or create_strategy("sma_cross"), risk=RISK, costs=COSTS,
                        start=start, end=end, names=names or {"005930": "삼성전자"})


class Checker(HTMLParser):
    VOID = {"meta", "br", "line", "circle", "polyline", "polygon", "link", "img", "hr", "input"}

    def __init__(self):
        super().__init__()
        self.stack, self.errors, self.text = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append((tag, list(self.stack)))
        else:
            self.stack.pop()

    def handle_data(self, data):
        self.text.append(data)


def check(html_text: str) -> str:
    c = Checker()
    c.feed(html_text)
    c.close()
    assert not c.errors and not c.stack, (c.errors[:3], c.stack)
    assert "http://" not in html_text and "https://" not in html_text and "<script" not in html_text.lower()
    return " ".join(c.text)


def test_report_is_self_contained_well_formed_and_has_key_sections(tmp_path):
    r = result()
    html_text = render_html_report(r)
    text = check(html_text)
    for label in ("총수익률", "연환산수익률(CAGR)", "최대낙폭(MDD)", "샤프지수", "승률", "거래횟수", "평가금 추이",
                  "단순보유(벤치마크)", "월별 수익률", "성과 지표", "거래 내역", "과거 성과는 미래 수익을 보장하지 않습니다",
                  "삼성전자(005930)"):
        assert label in text, label
    assert 'name="viewport"' in html_text and "prefers-color-scheme:dark" in html_text
    assert html_text.count("<svg") == 2 and "NaN" not in html_text and "inf" not in html_text.lower().replace("info", "")
    points = re.findall(r'<polyline points="([^"]+)"', html_text)
    assert points and all(len(p.split()) <= 600 for p in points)
    p = write_html_report(r, tmp_path / "out" / "report.html")
    assert p.read_text(encoding="utf-8") == html_text


def test_report_escapes_untrusted_text():
    evil = '<script>alert(1)</script>'
    r = result(names={"005930": evil})
    r.strategy_params["note"] = '"><img src=x onerror=alert(1)>'
    html_text = render_html_report(r, title="<b>제목</b>")
    assert "<script>alert(1)</script>" not in html_text and "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text
    assert "<img src=x" not in html_text and "<b>제목</b>" not in html_text
    check(html_text)


def test_report_handles_no_trades_single_day_and_flat_curve():
    idle = ScriptedStrategy(default=DayPlan())
    text = check(render_html_report(result(strategy=idle)))
    assert "체결된 주문이 없습니다" in text and "보유 중인 종목이 없습니다" in text
    one = result(strategy=idle, start=date(2024, 6, 28), end=date(2024, 6, 28))
    assert len(one.equity_curve) == 1
    check(render_html_report(one))


def test_trades_csv_has_bom_korean_headers_and_all_orders(tmp_path):
    r = result()
    assert r.orders
    p = write_trades_csv(r, tmp_path / "trades.csv")
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(raw.decode("utf-8-sig").splitlines()))
    assert rows[0][:5] == ["날짜", "시각", "종목코드", "종목명", "구분"] and len(rows) == len(r.orders) + 1
    assert {row[4] for row in rows[1:]} <= {"매수", "매도"}
    first_sell = next(row for row in rows[1:] if row[4] == "매도")
    assert first_sell[11] != "" and first_sell[14] != ""           # 실현손익, 진입일

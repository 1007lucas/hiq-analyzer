"""백테스트 결과 리포트 (HTML 1개 파일, 거래 내역 CSV).

HTML 은 외부 파일·인터넷 없이 열리는 한 장짜리 문서입니다 (CSS·차트 모두 내장, 자바스크립트 없음).
데이터에서 온 모든 글자는 html.escape 로 처리합니다.
"""

from __future__ import annotations

import csv
import html
import math
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from .engine import BacktestResult
from .metrics import (
    drawdown_series,
    format_metrics,
    format_pct,
    format_profit_factor,
    format_signed_pct,
    format_won,
    monthly_returns,
    yearly_returns,
)

DISCLAIMER = (
    "과거 성과는 미래 수익을 보장하지 않습니다. 백테스트는 일봉 기준의 근사이며 실제 체결과 다를 수 있습니다."
)
MAX_CHART_POINTS = 600
MAX_TRADE_ROWS = 500

_W, _H = 800, 300                    # 차트 좌표계 (viewBox)
_L, _R, _T, _B = 78, 14, 14, 30      # 여백: 왼쪽(금액 눈금), 오른쪽, 위, 아래(날짜)

_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16202c;--mute:#5b6878;--line:#dfe4ea;--accent:#0f6fde;--bench:#7a8696;
--up:#d92b2b;--down:#1f5fd6;--warn-bg:#fff6dd;--warn-ink:#6b4a00;--grid:#e8ecf1}
@media (prefers-color-scheme:dark){:root{--bg:#10151c;--card:#19212b;--ink:#e8edf3;--mute:#9aa7b6;--line:#2b3644;
--accent:#59a6ff;--bench:#8d99a8;--up:#ff6b6b;--down:#6ea8ff;--warn-bg:#3a2f10;--warn-ink:#ffdf8a;--grid:#263140}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",sans-serif}
main{max-width:1040px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:0 0 10px}
.sub{color:var(--mute);font-size:13px;margin:0 0 14px;word-break:keep-all}
.warn{background:var(--warn-bg);color:var(--warn-ink);border-radius:10px;padding:10px 14px;margin:0 0 16px;font-size:14px;word-break:keep-all}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 16px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.tile .k{color:var(--mute);font-size:12px}.tile .v{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums}
.tile .b{color:var(--mute);font-size:12px;font-variant-numeric:tabular-nums}
.up{color:var(--up)}.down{color:var(--down)}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
th{color:var(--mute);font-weight:600}th.l,td.l{text-align:left}td.wrap{white-space:normal;min-width:180px;text-align:left}
svg{display:block;width:100%;height:auto}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--mute);margin:0 0 6px}
.legend i{display:inline-block;width:22px;height:0;border-top:3px solid var(--accent);vertical-align:middle;margin-right:6px}
.legend i.bench{border-top:3px dashed var(--bench)}
.axis{fill:var(--mute);font-size:11px}.grid{stroke:var(--grid);stroke-width:1}
.note{color:var(--mute);font-size:12px;margin:8px 0 0}
pre{margin:0;font:13px/1.6 ui-monospace,Consolas,"D2Coding",monospace;white-space:pre-wrap}
"""


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _sign_class(value: float | None) -> str:
    if value is None or value == 0 or (isinstance(value, float) and math.isnan(value)):
        return ""
    return "up" if value > 0 else "down"


def _downsample(points: Sequence[tuple[date, float]], limit: int = MAX_CHART_POINTS) -> list[tuple[date, float]]:
    """점이 너무 많으면 일정 간격으로 추립니다 (첫 점과 마지막 점은 항상 유지)."""
    n = len(points)
    if n <= limit:
        return list(points)
    step = (n - 1) / (limit - 1)
    idx = sorted({round(i * step) for i in range(limit)} | {0, n - 1})
    return [points[i] for i in idx]


def _won_short(value: float) -> str:
    """축 눈금용 짧은 금액 표기 (만/억)."""
    a = abs(value)
    if a >= 1e8:
        return f"{value / 1e8:,.2f}억"
    if a >= 1e4:
        return f"{value / 1e4:,.0f}만"
    return f"{value:,.0f}"


def _line_chart(series: Sequence[tuple[str, Sequence[tuple[date, float]]]], *, percent: bool = False) -> str:
    """꺾은선 차트 SVG. series = [(css 클래스, [(날짜, 값), ...]), ...]. 모든 계열은 같은 날짜 축을 씁니다."""
    series = [(cls, _downsample(pts)) for cls, pts in series if pts]
    if not series:
        return '<p class="note">표시할 데이터가 없습니다.</p>'
    values = [v for _, pts in series for _, v in pts]
    lo, hi = min(values), max(values)
    if percent:
        hi = max(hi, 0.0)
    if hi - lo < 1e-12:                       # 평평한 선 → 위아래로 여유를 줘서 0 으로 나누지 않게
        pad = abs(hi) * 0.05 or 1.0
        lo, hi = lo - pad, hi + pad
    else:
        pad = (hi - lo) * 0.06
        lo, hi = (lo - pad, hi + pad) if not percent else (lo - pad, hi)
    n = max(len(pts) for _, pts in series)
    plot_w, plot_h = _W - _L - _R, _H - _T - _B

    def x(i: int, count: int) -> float:
        return _L + (plot_w * i / (count - 1) if count > 1 else plot_w / 2)

    def y(v: float) -> float:
        return _T + plot_h * (1 - (v - lo) / (hi - lo))

    out = [f'<svg viewBox="0 0 {_W} {_H}" role="img" aria-label="{"낙폭" if percent else "평가금"} 추이 차트">']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        yy = y(v)
        label = f"{v * 100:.0f}%" if percent else _won_short(v)
        out.append(f'<line class="grid" x1="{_L}" y1="{yy:.1f}" x2="{_W - _R}" y2="{yy:.1f}"/>')
        out.append(f'<text class="axis" x="{_L - 6}" y="{yy + 4:.1f}" text-anchor="end">{_e(label)}</text>')
    dates = max((pts for _, pts in series), key=len)
    ticks = sorted({0, (n - 1) // 2, n - 1}) if n > 2 else list(range(n))
    for i in ticks:
        anchor = "start" if i == 0 and n > 1 else ("end" if i == n - 1 and n > 1 else "middle")
        out.append(
            f'<text class="axis" x="{x(i, n):.1f}" y="{_H - 8}" text-anchor="{anchor}">{_e(dates[i][0].isoformat())}</text>'
        )
    for cls, pts in series:
        count = len(pts)
        if count == 1:
            out.append(f'<circle class="{cls}" cx="{x(0, 1):.1f}" cy="{y(pts[0][1]):.1f}" r="4"/>')
            continue
        coords = " ".join(f"{x(i, count):.1f},{y(v):.1f}" for i, (_, v) in enumerate(pts))
        if percent:
            base = y(0.0)
            out.append(
                f'<polygon points="{x(0, count):.1f},{base:.1f} {coords} {x(count - 1, count):.1f},{base:.1f}" '
                f'fill="var(--down)" fill-opacity="0.18" stroke="none"/>'
            )
        style = {
            "strategy": 'stroke="var(--accent)" stroke-width="2.2"',
            "bench": 'stroke="var(--bench)" stroke-width="1.8" stroke-dasharray="6 4"',
            "dd": 'stroke="var(--down)" stroke-width="1.6"',
        }[cls]
        out.append(f'<polyline points="{coords}" fill="none" {style} stroke-linejoin="round"/>')
    out.append("</svg>")
    return "".join(out)


def _tile(label: str, value: str, bench: str = "", cls: str = "") -> str:
    b = f'<div class="b">단순보유 {_e(bench)}</div>' if bench else ""
    return f'<div class="tile"><div class="k">{_e(label)}</div><div class="v {cls}">{_e(value)}</div>{b}</div>'


def _monthly_table(result: BacktestResult) -> str:
    months = monthly_returns(result.equity_curve, result.initial_capital)
    years = yearly_returns(result.equity_curve, result.initial_capital)
    if not months:
        return '<p class="note">표시할 데이터가 없습니다.</p>'
    head = "".join(f"<th>{m}월</th>" for m in range(1, 13))
    rows = []
    for year in sorted(months):
        cells = []
        for m in range(1, 13):
            r = months[year].get(m)
            cells.append(f'<td class="{_sign_class(r)}">{_e(format_signed_pct(r))}</td>' if r is not None else "<td></td>")
        yr = years.get(year)
        total = f'<td class="{_sign_class(yr)}"><b>{_e(format_signed_pct(yr))}</b></td>' if yr is not None else "<td></td>"
        rows.append(f'<tr><td class="l">{year}</td>{"".join(cells)}{total}</tr>')
    return (
        f'<div class="scroll"><table><thead><tr><th class="l">연도</th>{head}<th>연간</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _positions_table(result: BacktestResult) -> str:
    if not result.final_positions:
        return '<p class="note">백테스트 종료 시점에 보유 중인 종목이 없습니다.</p>'
    rows = []
    for p in result.final_positions:
        pnl_pct = float(p.get("pnl_pct") or 0.0)
        rows.append(
            f'<tr><td class="l">{_e(p.get("name") or p.get("symbol"))}</td><td>{int(p.get("qty") or 0):,}</td>'
            f'<td>{float(p.get("avg_price") or 0):,.0f}</td><td>{float(p.get("price") or 0):,.0f}</td>'
            f'<td>{float(p.get("value") or 0):,.0f}</td>'
            f'<td class="{_sign_class(pnl_pct)}">{float(p.get("pnl") or 0):+,.0f} ({_e(format_signed_pct(pnl_pct))})</td>'
            f'<td class="l">{_e(p.get("entry_date", ""))}</td></tr>'
        )
    return (
        '<div class="scroll"><table><thead><tr><th class="l">종목</th><th>수량</th><th>평균단가</th><th>현재가</th>'
        f'<th>평가금액</th><th>평가손익</th><th class="l">진입일</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def _name(result: BacktestResult, symbol: Any) -> str:
    sym = str(symbol)
    name = result.names.get(sym)
    return f"{name}({sym})" if name else sym


def _trades_table(result: BacktestResult) -> str:
    orders = [o for o in result.orders if (o.get("filled_qty") or 0) > 0]
    if not orders:
        return '<p class="note">체결된 주문이 없습니다. 전략 조건이 한 번도 충족되지 않았거나 기간이 너무 짧을 수 있습니다.</p>'
    shown = orders[::-1][:MAX_TRADE_ROWS]
    rows = []
    for o in shown:
        is_sell = o.get("side") == "sell"
        pnl = o.get("pnl")
        pnl_cell = (
            f'<td class="{_sign_class(float(pnl))}">{float(pnl):+,.0f} ({_e(format_signed_pct(float(o.get("pnl_pct") or 0)))})</td>'
            if is_sell and pnl is not None
            else "<td></td>"
        )
        rows.append(
            f'<tr><td class="l">{_e(o.get("day", ""))}</td><td class="l">{_e(_name(result, o.get("symbol", "")))}</td>'
            f'<td class="l {"down" if is_sell else "up"}">{"매도" if is_sell else "매수"}</td>'
            f'<td>{int(o.get("filled_qty") or 0):,}</td><td>{float(o.get("price") or 0):,.0f}</td>'
            f'<td>{float(o.get("amount") or 0):,.0f}</td>{pnl_cell}<td class="wrap">{_e(o.get("reason", ""))}</td></tr>'
        )
    note = (
        f'<p class="note">최근 {MAX_TRADE_ROWS:,}건만 표시했습니다 (전체 {len(orders):,}건). 전체 내역은 CSV 파일을 확인하세요.</p>'
        if len(orders) > MAX_TRADE_ROWS
        else ""
    )
    return (
        '<div class="scroll"><table><thead><tr><th class="l">날짜</th><th class="l">종목</th><th class="l">구분</th>'
        '<th>수량</th><th>체결가</th><th>금액</th><th>실현손익</th><th class="l">사유</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>{note}'
    )


def render_html_report(result: BacktestResult, *, title: str | None = None) -> str:
    """백테스트 결과를 한 장짜리 HTML 문서로 만듭니다."""
    m = result.metrics
    title = title or f"백테스트 리포트 — {result.strategy_name}"
    params = ", ".join(f"{k}={v}" for k, v in result.strategy_params.items()) or "기본값"
    symbols = ", ".join(_name(result, s) for s in result.symbols)
    tiles = "".join(
        [
            _tile("총수익률", format_signed_pct(m.total_return), format_signed_pct(m.benchmark_return), _sign_class(m.total_return)),
            _tile("연환산수익률(CAGR)", format_signed_pct(m.cagr), format_signed_pct(m.benchmark_cagr), _sign_class(m.cagr)),
            _tile("최대낙폭(MDD)", format_pct(m.max_drawdown), format_pct(m.benchmark_max_drawdown), _sign_class(m.max_drawdown)),
            _tile("샤프지수", f"{m.sharpe:.2f}"),
            _tile("승률", format_pct(m.win_rate)),
            _tile("거래횟수", f"{m.num_trades:,}회"),
        ]
    )
    equity_chart = _line_chart([("bench", result.benchmark_curve), ("strategy", result.equity_curve)])
    dd_chart = _line_chart([("dd", drawdown_series(result.equity_curve, result.initial_capital))], percent=True)
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title><style>{_CSS}</style></head>
<body><main>
<h1>{_e(title)}</h1>
<p class="sub">전략 <b>{_e(result.strategy_name)}</b> ({_e(params)}) · 기간 {_e(result.start)} ~ {_e(result.end)} ({m.trading_days:,}거래일)
 · 초기 자금 {_e(format_won(result.initial_capital))} → 최종 {_e(format_won(m.final_equity))}<br>종목: {_e(symbols)}</p>
<p class="warn">⚠️ {_e(DISCLAIMER)}</p>
<div class="tiles">{tiles}</div>
<section class="card"><h2>평가금 추이</h2>
<div class="legend"><span><i></i>전략</span><span><i class="bench"></i>단순보유(벤치마크)</span></div>
{equity_chart}
<p class="note">단순보유(벤치마크)는 같은 종목들을 첫날 같은 비중으로 사서 끝까지 들고 있었을 때의 평가금입니다 (비용 미반영).</p></section>
<section class="card"><h2>낙폭 (고점 대비 하락률)</h2>{dd_chart}
<p class="note">최대낙폭 {_e(format_pct(m.max_drawdown))} ({_e(m.max_drawdown_peak)} ~ {_e(m.max_drawdown_trough)})</p></section>
<section class="card"><h2>월별 수익률</h2>{_monthly_table(result)}</section>
<section class="card"><h2>성과 지표</h2><pre>{_e(format_metrics(m))}</pre>
<p class="note">손익비 {_e(format_profit_factor(m.profit_factor))} · 수수료·거래세·슬리피지는 설정값으로 추정해 반영했습니다.</p></section>
<section class="card"><h2>종료 시점 보유 종목</h2>{_positions_table(result)}</section>
<section class="card"><h2>거래 내역 (최근 순)</h2>{_trades_table(result)}</section>
</main></body></html>
"""


def write_html_report(result: BacktestResult, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_html_report(result), encoding="utf-8")
    return p


_CSV_COLUMNS: tuple[tuple[str, str], ...] = (
    ("day", "날짜"),
    ("ts", "시각"),
    ("symbol", "종목코드"),
    ("name", "종목명"),
    ("side", "구분"),
    ("qty", "주문수량"),
    ("filled_qty", "체결수량"),
    ("price", "체결가"),
    ("amount", "체결금액"),
    ("fee", "수수료"),
    ("tax", "거래세"),
    ("pnl", "실현손익"),
    ("pnl_pct", "실현수익률(%)"),
    ("entry_price", "진입단가"),
    ("entry_day", "진입일"),
    ("reason", "사유"),
    ("status", "상태"),
    ("cash_after", "주문 후 현금"),
)


def write_trades_csv(result: BacktestResult, path: str | Path) -> Path:
    """주문 내역을 CSV 로 저장합니다 (한글 엑셀에서 바로 열리도록 BOM 포함 UTF-8)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([label for _, label in _CSV_COLUMNS])
        for o in result.orders:
            row = []
            for key, _ in _CSV_COLUMNS:
                if key == "name":
                    row.append(result.names.get(str(o.get("symbol", "")), ""))
                elif key == "side":
                    row.append("매도" if o.get("side") == "sell" else "매수")
                elif key == "pnl_pct":
                    row.append("" if o.get("pnl_pct") is None else f"{float(o['pnl_pct']) * 100:.2f}")
                else:
                    v = o.get(key)
                    row.append("" if v is None else v)
            w.writerow(row)
    return p

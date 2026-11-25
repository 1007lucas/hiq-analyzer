"""일봉 CSV 읽기/쓰기.

파일 형식: 첫 줄은 헤더, 이후 한 줄에 하루.
    date,open,high,low,close,volume
    2024-01-02,78200,79800,78200,79600,17142847

읽을 때는 한글 헤더(날짜/시가/고가/저가/종가/거래량)와 YYYYMMDD, YYYY.MM.DD, YYYY/MM/DD
날짜, 천 단위 쉼표가 들어간 숫자도 받아들입니다 (증권사 HTS 에서 내려받은 파일을 그대로 쓸 수 있도록).
"""

from __future__ import annotations

import csv
import os
import re
from datetime import date
from pathlib import Path
from typing import Iterable

from ..models import Bar

HEADER = ("date", "open", "high", "low", "close", "volume")

_ALIASES = {
    "date": {"date", "날짜", "일자", "datetime", "time", "영업일자"},
    "open": {"open", "시가"},
    "high": {"high", "고가"},
    "low": {"low", "저가"},
    "close": {"close", "종가", "현재가", "adj close", "adj_close"},
    "volume": {"volume", "거래량", "vol"},
}


class CsvFormatError(ValueError):
    """CSV 내용을 일봉으로 해석할 수 없음."""


def parse_day(text: str) -> date:
    """'2024-01-02', '20240102', '2024.01.02', '2024/1/2', '2024-01-02 00:00:00' → date."""
    s = str(text).strip().strip('"').strip("'")
    m = re.match(r"^(\d{4})[-./]?(\d{1,2})[-./]?(\d{1,2})(?:\D.*)?$", s)
    if not m:
        raise ValueError(f"날짜 형식을 알 수 없습니다: {text!r}")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _num(text: str) -> float:
    s = str(text).strip().strip('"').replace(",", "")
    if s == "":
        raise ValueError("빈 값")
    return float(s)


def is_valid_bar(bar: Bar) -> bool:
    """가격이 모두 양수이고 고가/저가가 시가·종가를 감싸는 정상 봉인지."""
    o, h, low, c = bar.open, bar.high, bar.low, bar.close
    if not (o > 0 and h > 0 and low > 0 and c > 0):
        return False
    return low <= min(o, c) and h >= max(o, c) and bar.volume >= 0


def clean_bars(bars: Iterable[Bar]) -> list[Bar]:
    """비정상 봉 제거, 날짜 오름차순 정렬, 같은 날짜는 마지막 것만 남김."""
    by_day: dict[date, Bar] = {}
    for b in bars:
        if is_valid_bar(b):
            by_day[b.date] = b
    return [by_day[d] for d in sorted(by_day)]


def read_csv(path: str | Path) -> list[Bar]:
    """CSV 파일에서 일봉을 읽습니다 (날짜 오름차순, 비정상 행은 오류).

    UTF-8(BOM 포함)과 CP949(한글 윈도우 엑셀 저장) 인코딩을 모두 시도합니다.
    """
    p = Path(path)
    raw = p.read_bytes()
    text: str | None = None
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise CsvFormatError(f"{p.name}: 파일 인코딩을 알 수 없습니다 (UTF-8 또는 CP949 로 저장해 주세요)")

    rows = list(csv.reader(text.splitlines()))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        raise CsvFormatError(f"{p.name}: 내용이 비어 있습니다")

    header = [h.strip().strip('"').lower() for h in rows[0]]
    col: dict[str, int] = {}
    for key, names in _ALIASES.items():
        for i, h in enumerate(header):
            if h in names and key not in col:
                col[key] = i
    missing = [k for k in ("date", "open", "high", "low", "close") if k not in col]
    if missing:
        raise CsvFormatError(
            f"{p.name}: 필요한 열이 없습니다: {missing}. 첫 줄에 date,open,high,low,close,volume "
            "(또는 날짜,시가,고가,저가,종가,거래량) 헤더가 있어야 합니다."
        )

    bars: list[Bar] = []
    for lineno, r in enumerate(rows[1:], start=2):
        try:
            bar = Bar(
                date=parse_day(r[col["date"]]),
                open=_num(r[col["open"]]),
                high=_num(r[col["high"]]),
                low=_num(r[col["low"]]),
                close=_num(r[col["close"]]),
                volume=_num(r[col["volume"]]) if "volume" in col and col["volume"] < len(r) and r[col["volume"]].strip() else 0.0,
            )
        except (ValueError, IndexError) as e:
            raise CsvFormatError(f"{p.name} {lineno}번째 줄을 읽을 수 없습니다: {e}") from e
        if not is_valid_bar(bar):
            raise CsvFormatError(
                f"{p.name} {lineno}번째 줄({bar.date})의 가격이 이상합니다 "
                f"(시가 {bar.open}, 고가 {bar.high}, 저가 {bar.low}, 종가 {bar.close})"
            )
        bars.append(bar)

    out = clean_bars(bars)
    if len(out) != len(bars):
        raise CsvFormatError(f"{p.name}: 같은 날짜가 두 번 이상 들어 있습니다")
    return out


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else repr(float(x))


def write_csv(path: str | Path, bars: Iterable[Bar]) -> Path:
    """일봉을 CSV 로 저장합니다 (임시 파일에 쓴 뒤 이름을 바꿔 반쯤 쓰인 파일이 남지 않게)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for b in bars:
            w.writerow([b.date.isoformat(), _fmt(b.open), _fmt(b.high), _fmt(b.low), _fmt(b.close), _fmt(b.volume)])
    os.replace(tmp, p)
    return p

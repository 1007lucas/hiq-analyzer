"""일봉 데이터 불러오기 (백테스트용).

load_bars() 하나로 여러 데이터 출처를 같은 방식으로 씁니다.

출처(source)
  kis        한국투자증권 Open API (공식, API 키 필요)
  naver      네이버 금융 (비공식, 키 불필요)
  yahoo      야후 파이낸스 (비공식, 키 불필요)
  csv        사용자가 준비한 CSV 파일 (<csv_dir>/<종목코드>.csv)
  synthetic  연습용 가짜 데이터 (실제 시세 아님)
  auto       kis 키가 있으면 kis, 없으면 naver → 실패 시 yahoo

네트워크 출처에서 받은 데이터는 cache_dir 에 CSV 로 저장해 같은 날 다시 받지 않습니다.
수정주가는 액면분할 등이 생기면 과거 값까지 통째로 바뀌므로, 캐시는 '이어 붙이기'가
아니라 하루에 한 번 전체를 새로 받는 방식입니다.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Sequence

from ..brokers.base import BrokerError, MarketData
from ..models import Bar, now_kst
from .store import CsvFormatError, clean_bars, read_csv, write_csv
from .synthetic import generate_bars

log = logging.getLogger("autotrader.data")

SOURCES = ("auto", "kis", "naver", "yahoo", "csv", "synthetic")
NETWORK_SOURCES = ("kis", "naver", "yahoo")
CACHE_START_SLACK_DAYS = 10     # 캐시의 첫 봉이 요청 시작일보다 이만큼까지 늦어도 '충분'하다고 봄 (휴일/상장일 고려)

Fetcher = Callable[[str, date, date], list[Bar]]


class DataError(Exception):
    """데이터를 불러오지 못함. 메시지는 사용자에게 그대로 보여 줄 수 있는 한국어 문장입니다."""


def _provider(source: str) -> Fetcher:
    # 비공식 출처 모듈은 필요할 때만 불러옵니다.
    from . import providers

    if source == "naver":
        return providers.fetch_naver_daily
    if source == "yahoo":
        return providers.fetch_yahoo_daily
    raise ValueError(source)


def _cache_path(cache_dir: Path, source: str, symbol: str) -> Path:
    return cache_dir / source / f"{symbol}.csv"


def _read_cache(path: Path, start: date, end: date, today: date) -> list[Bar] | None:
    """오늘 받아 둔 캐시가 요청 구간을 덮으면 그 내용을, 아니면 None."""
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=now_kst().tzinfo).date()
    except OSError:
        return None
    if mtime != today:
        return None
    try:
        bars = read_csv(path)
    except (OSError, CsvFormatError):
        return None
    if not bars:
        return None
    meta = path.with_suffix(".range")
    try:
        req_start_s, req_end_s = meta.read_text(encoding="utf-8").split()
        req_start, req_end = date.fromisoformat(req_start_s), date.fromisoformat(req_end_s)
    except (OSError, ValueError):
        return None
    if req_start > start or req_end < end:
        return None             # 캐시를 만들 때 요청했던 구간이 지금 요청보다 좁음
    return bars


def _fetch_one(
    symbol: str,
    start: date,
    end: date,
    source: str,
    *,
    kis: MarketData | None,
    csv_dir: Path | None,
    cache_dir: Path | None,
    refresh: bool,
    today: date,
) -> tuple[list[Bar], str]:
    """한 종목의 일봉과 실제로 사용된 출처 이름을 반환합니다."""
    if source == "synthetic":
        return generate_bars(symbol, start, end), "synthetic"

    if source == "csv":
        if csv_dir is None:
            raise DataError("CSV 폴더가 지정되지 않았습니다")
        path = csv_dir / f"{symbol}.csv"
        if not path.is_file():
            raise DataError(f"{symbol}: CSV 파일이 없습니다 → {path}")
        try:
            return read_csv(path), "csv"
        except CsvFormatError as e:
            raise DataError(str(e)) from e

    if source == "auto":
        order = ["kis"] if kis is not None else ["naver", "yahoo"]
    else:
        order = [source]

    errors: list[str] = []
    for src in order:
        cpath = _cache_path(cache_dir, src, symbol) if cache_dir is not None else None
        if cpath is not None and not refresh:
            cached = _read_cache(cpath, start, end, today)
            if cached is not None:
                return cached, src
        try:
            if src == "kis":
                if kis is None:
                    raise DataError("한국투자증권 API 키가 설정되지 않았습니다 (.env 파일 확인)")
                bars = kis.get_daily_bars(symbol, start, end)
            else:
                bars = _provider(src)(symbol, start, end)
        except (BrokerError, DataError, OSError) as e:
            errors.append(f"{src}: {e}")
            log.warning("%s 일봉 조회 실패 (%s): %s", symbol, src, e)
            continue
        bars = clean_bars(bars)
        if not bars:
            errors.append(f"{src}: 받은 데이터가 없습니다 (종목코드와 기간을 확인하세요)")
            continue
        if cpath is not None:
            try:
                write_csv(cpath, bars)
                cpath.with_suffix(".range").write_text(f"{start.isoformat()} {end.isoformat()}", encoding="utf-8")
            except OSError as e:
                log.warning("캐시 저장 실패 (%s): %s", cpath, e)
        return bars, src

    raise DataError(
        f"{symbol}: 일봉 데이터를 받지 못했습니다.\n    "
        + "\n    ".join(errors)
        + "\n  → 인터넷 연결과 종목코드를 확인하세요. 계속 안 되면 CSV 파일을 직접 준비하거나"
        " (--source csv), 기능 체험만 하려면 연습용 데이터(--source synthetic)를 쓸 수 있습니다."
    )


def load_bars(
    symbols: Sequence[str],
    start: date,
    end: date,
    *,
    source: str = "auto",
    cache_dir: Path | None = None,
    kis: MarketData | None = None,
    csv_dir: Path | None = None,
    refresh: bool = False,
    progress: Callable[[str, int, int], None] | None = None,
    today: date | None = None,
) -> tuple[dict[str, list[Bar]], dict[str, str]]:
    """여러 종목의 일봉을 불러옵니다.

    반환: (종목 → [start, end] 구간의 일봉(오름차순), 종목 → 실제 사용된 출처)
    progress(symbol, done, total) 는 종목 하나를 마칠 때마다 호출됩니다.
    한 종목이라도 실패하면 DataError.
    """
    if source not in SOURCES:
        raise DataError(f"알 수 없는 데이터 출처: {source} (사용 가능: {', '.join(SOURCES)})")
    if end < start:
        raise DataError(f"기간이 올바르지 않습니다: {start} ~ {end}")
    day = today or now_kst().date()
    out: dict[str, list[Bar]] = {}
    used: dict[str, str] = {}
    total = len(symbols)
    for i, sym in enumerate(symbols, start=1):
        bars, src = _fetch_one(
            sym, start, end, source, kis=kis, csv_dir=csv_dir, cache_dir=cache_dir, refresh=refresh, today=day
        )
        bars = [b for b in clean_bars(bars) if start <= b.date <= end]
        if not bars:
            raise DataError(f"{sym}: {start} ~ {end} 구간에 데이터가 없습니다 (출처: {src})")
        out[sym] = bars
        used[sym] = src
        if progress is not None:
            progress(sym, i, total)
    return out, used

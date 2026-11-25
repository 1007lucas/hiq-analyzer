"""비공식 무료 시세 출처 (네이버 금융, 야후 파이낸스).

API 키 없이 백테스트용 일봉과 페이퍼 트레이딩용 현재가를 받기 위한 **최선 노력(best effort)** 구현입니다.

주의
* 두 곳 모두 공식 공개 API 가 아닙니다. 예고 없이 형식이 바뀌거나 차단될 수 있고,
  이 프로그램을 만든 환경에서는 실제 서버에 접속해 검증하지 못했습니다.
* 그래서 응답 해석을 최대한 관대하게 하고, 해석에 실패하면 원인을 알려 주는 DataError 를 냅니다.
* 실전/모의투자에는 한국투자증권 공식 API 시세를 쓰는 것을 권장합니다.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from ..brokers.base import BrokerError, MarketData
from ..models import KST, Bar, Quote, now_kst
from .store import clean_bars

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TIMEOUT_SEC = 15.0

HttpGet = Callable[[str, dict[str, str]], bytes]      # (url, headers) → 본문. 실패 시 OSError


class ProviderError(Exception):
    """무료 시세 출처에서 데이터를 받지 못함 (loader 가 DataError 로 바꿔 사용자에게 보여 줍니다)."""


def _http_get(url: str, headers: dict[str, str]) -> bytes:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:  # noqa: S310 - 고정된 https 주소
        return resp.read()


def _get(url: str, headers: dict[str, str], http: HttpGet | None, what: str) -> bytes:
    try:
        return (http or _http_get)(url, headers)
    except urllib.error.HTTPError as e:
        raise ProviderError(f"{what}: 서버가 요청을 거부했습니다 (HTTP {e.code})") from None
    except OSError as e:
        raise ProviderError(f"{what}: 접속 실패 ({e})") from None


# --------------------------------------------------------------------------- #
# 네이버 금융 — 일봉
# --------------------------------------------------------------------------- #
_NAVER_ROW = re.compile(
    r"""\[\s*["']?(\d{8})["']?\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)"""
)


def parse_naver_daily(text: str) -> list[Bar]:
    """네이버 siseJson 응답(자바스크립트 배열 모양의 텍스트)에서 일봉을 뽑습니다.

    예)  [['날짜', '시가', '고가', '저가', '종가', '거래량', '외국인소진율'],
          ["20240102", 78200, 79800, 78200, 79600, 17142847, 54.01], ... ]
    """
    bars: list[Bar] = []
    for m in _NAVER_ROW.finditer(text):
        day = datetime.strptime(m.group(1), "%Y%m%d").date()
        o, h, low, c, v = (float(m.group(i)) for i in range(2, 7))
        bars.append(Bar(day, o, h, low, c, v))
    return clean_bars(bars)


def fetch_naver_daily(symbol: str, start: date, end: date, *, http: HttpGet | None = None) -> list[Bar]:
    url = "https://api.finance.naver.com/siseJson.naver?" + urllib.parse.urlencode(
        {
            "symbol": symbol,
            "requestType": "1",
            "startTime": start.strftime("%Y%m%d"),
            "endTime": end.strftime("%Y%m%d"),
            "timeframe": "day",
        }
    )
    raw = _get(url, {"User-Agent": USER_AGENT, "Referer": "https://finance.naver.com/"}, http, "네이버 금융")
    text = raw.decode("utf-8", errors="replace")
    bars = [b for b in parse_naver_daily(text) if start <= b.date <= end]
    if not bars and "[" not in text:
        raise ProviderError("네이버 금융: 예상과 다른 응답을 받았습니다 (형식이 바뀌었을 수 있습니다)")
    return bars


# --------------------------------------------------------------------------- #
# 야후 파이낸스 — 일봉
# --------------------------------------------------------------------------- #
def parse_yahoo_chart(payload: Any) -> list[Bar]:
    """야후 v8 chart 응답(JSON)에서 일봉을 뽑습니다. 값이 비어 있는(null) 날은 건너뜁니다."""
    try:
        chart = payload["chart"]
        if chart.get("error"):
            raise ProviderError(f"야후 파이낸스: {chart['error'].get('description') or chart['error']}")
        results = chart.get("result") or []
        if not results:
            return []
        result = results[0]
        stamps = result.get("timestamp") or []
        quote = result["indicators"]["quote"][0]
        offset = int((result.get("meta") or {}).get("gmtoffset", 9 * 3600))
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise ProviderError(f"야후 파이낸스: 예상과 다른 응답 형식입니다 ({e})") from None
    tz = timezone(timedelta(seconds=offset))
    bars: list[Bar] = []
    for i, ts in enumerate(stamps):
        try:
            o, h, low, c = quote["open"][i], quote["high"][i], quote["low"][i], quote["close"][i]
            v = (quote.get("volume") or [0] * len(stamps))[i] or 0
        except (IndexError, KeyError, TypeError):
            continue
        if None in (ts, o, h, low, c):
            continue
        day = datetime.fromtimestamp(int(ts), tz=tz).date()
        bars.append(Bar(day, float(o), float(h), float(low), float(c), float(v)))
    return clean_bars(bars)


def fetch_yahoo_daily(symbol: str, start: date, end: date, *, http: HttpGet | None = None) -> list[Bar]:
    """야후는 코스피(.KS)와 코스닥(.KQ)의 접미사가 달라, 두 가지를 차례로 시도합니다."""
    p1 = int(datetime.combine(start, datetime.min.time(), tzinfo=KST).timestamp())
    p2 = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=KST).timestamp())
    last_error: ProviderError | None = None
    for suffix in (".KS", ".KQ"):
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol + suffix)}?" + urllib.parse.urlencode(
            {"period1": p1, "period2": p2, "interval": "1d", "events": "div,splits"}
        )
        try:
            raw = _get(url, {"User-Agent": USER_AGENT, "Accept": "application/json"}, http, "야후 파이낸스")
            bars = [b for b in parse_yahoo_chart(json.loads(raw.decode("utf-8", errors="replace"))) if start <= b.date <= end]
        except ProviderError as e:
            last_error = e
            continue
        except ValueError:
            last_error = ProviderError("야후 파이낸스: 응답을 해석할 수 없습니다")
            continue
        if bars:
            return bars
    if last_error is not None:
        raise last_error
    return []


# --------------------------------------------------------------------------- #
# 네이버 금융 — 현재가 (페이퍼 트레이딩용 시세)
# --------------------------------------------------------------------------- #
def _n(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_naver_quote(symbol: str, payload: Any) -> Quote:
    """네이버 실시간 폴링 응답(JSON)을 Quote 로 바꿉니다."""
    try:
        item = payload["datas"][0]
    except (KeyError, IndexError, TypeError):
        raise ProviderError("네이버 금융: 예상과 다른 시세 응답 형식입니다") from None
    price = _n(item.get("closePrice"))
    if price <= 0:
        raise ProviderError(f"네이버 금융: {symbol} 현재가를 받지 못했습니다")
    change = abs(_n(item.get("compareToPreviousClosePrice")))
    direction = str((item.get("compareToPreviousPrice") or {}).get("name", "")).upper()
    if direction in ("FALLING", "LOWER_LIMIT"):
        change = -change
    volume = _n(item.get("accumulatedTradingVolume"))
    traded = volume > 0
    stop = item.get("tradeStopType") or {}
    halted = str(stop.get("name", "TRADING")).upper() not in ("TRADING", "") if isinstance(stop, dict) else False
    return Quote(
        symbol=symbol,
        price=price,
        open=_n(item.get("openPrice")) if traded else 0.0,
        high=_n(item.get("highPrice")) if traded else 0.0,
        low=_n(item.get("lowPrice")) if traded else 0.0,
        prev_close=price - change,
        volume=volume,
        halted=halted,
        time=now_kst(),
    )


class NaverMarketData(MarketData):
    """네이버 금융 기반 시세 (비공식). API 키 없이 페이퍼 트레이딩을 해 볼 때만 씁니다."""

    name = "naver"

    def __init__(self, *, http: HttpGet | None = None) -> None:
        self._http = http

    def get_quote(self, symbol: str) -> Quote:
        url = f"https://polling.finance.naver.com/api/realtime/domestic/stock/{urllib.parse.quote(symbol)}"
        try:
            raw = _get(url, {"User-Agent": USER_AGENT, "Referer": "https://finance.naver.com/"}, self._http, "네이버 금융")
            return parse_naver_quote(symbol, json.loads(raw.decode("utf-8", errors="replace")))
        except (ProviderError, ValueError) as e:
            raise BrokerError(str(e) or "네이버 금융 시세 응답을 해석할 수 없습니다") from None

    def get_daily_bars(self, symbol: str, start: date, end: date) -> list[Bar]:
        try:
            return fetch_naver_daily(symbol, start, end, http=self._http)
        except ProviderError as e:
            raise BrokerError(str(e)) from None

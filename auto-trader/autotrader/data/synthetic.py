"""연습용 가짜(합성) 일봉 생성기.

인터넷이나 API 키 없이도 백테스트 기능을 바로 체험할 수 있게 해 줍니다.
**실제 시장 데이터가 아니므로 이 데이터로 나온 수익률은 아무 의미가 없습니다.**

같은 (종목코드, seed) 로는 항상 같은 데이터가 나옵니다.
"""

from __future__ import annotations

import math
import random
import zlib
from datetime import date, timedelta

from ..market_calendar import MarketCalendar
from ..models import Bar


def _tick(price: float) -> int:
    """대략적인 호가 단위 (합성 데이터를 그럴듯한 가격으로 반올림하는 용도)."""
    if price < 2_000:
        return 1
    if price < 5_000:
        return 5
    if price < 20_000:
        return 10
    if price < 50_000:
        return 50
    if price < 200_000:
        return 100
    if price < 500_000:
        return 500
    return 1_000


def _round(price: float) -> float:
    t = _tick(price)
    return float(max(t, int(round(price / t)) * t))


def generate_bars(symbol: str, start: date, end: date, *, seed: int = 0) -> list[Bar]:
    """[start, end] 구간의 합성 일봉. 주말과 (달력상) 휴장일은 건너뜁니다.

    추세가 몇 달 단위로 바뀌는 랜덤워크 + 하루 변동폭으로 만듭니다.
    """
    if end < start:
        return []
    rng = random.Random(zlib.crc32(f"{symbol}:{seed}".encode("utf-8")))
    cal = MarketCalendar()
    price = float(rng.choice([8_000, 15_000, 32_000, 54_000, 71_000, 120_000, 240_000]))
    drift = 0.0
    regime_left = 0
    bars: list[Bar] = []
    d = start
    while d <= end:
        if cal.is_trading_day(d):
            if regime_left <= 0:
                drift = rng.gauss(0.0003, 0.0012)        # 하루 평균 수익률 (상승/하락/횡보 국면)
                regime_left = rng.randint(30, 120)
            regime_left -= 1
            vol = 0.018
            gap = rng.gauss(0.0, vol * 0.4)
            body = rng.gauss(drift, vol)
            o = price * math.exp(gap)
            c = o * math.exp(body)
            hi = max(o, c) * (1.0 + abs(rng.gauss(0.0, vol * 0.5)))
            lo = min(o, c) * (1.0 - abs(rng.gauss(0.0, vol * 0.5)))
            o_r, c_r = _round(o), _round(c)
            hi_r = max(_round(hi), o_r, c_r)
            lo_r = min(_round(lo), o_r, c_r)
            volume = float(int(rng.lognormvariate(13.0, 0.6)))
            bars.append(Bar(d, o_r, hi_r, lo_r, c_r, volume))
            price = max(c, 500.0)
        d += timedelta(days=1)
    return bars

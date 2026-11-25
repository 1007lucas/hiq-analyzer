"""장 달력과 호가 단위 테스트."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from autotrader.market_calendar import MarketCalendar
from autotrader.market_rules import round_to_tick, shift_ticks, tick_size
from autotrader.models import KST


def weekday_closures(cal: MarketCalendar, year: int) -> list[date]:
    d, out = date(year, 1, 1), []
    while d.year == year:
        if d.weekday() < 5 and not cal.is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def test_2026_has_17_weekday_closures_and_244_trading_days():
    cal = MarketCalendar()
    closed = weekday_closures(cal, 2026)
    assert len(closed) == 17
    for d in (date(2026, 1, 1), date(2026, 2, 17), date(2026, 3, 2), date(2026, 5, 1), date(2026, 6, 3),
              date(2026, 7, 17), date(2026, 9, 25), date(2026, 10, 5), date(2026, 12, 25), date(2026, 12, 31)):
        assert d in closed, d
    trading = sum(cal.is_trading_day(date(2026, 1, 1) + timedelta(days=i)) for i in range(365))
    assert trading == 244
    assert cal.is_trading_day(date(2026, 12, 30)) and cal.is_trading_day(date(2026, 11, 25))


def test_2027_expected_closures():
    cal = MarketCalendar()
    closed = weekday_closures(cal, 2027)
    assert len(closed) == 16
    assert {date(2027, 2, 8), date(2027, 2, 9), date(2027, 5, 3), date(2027, 7, 19), date(2027, 12, 27),
            date(2027, 12, 31)} <= set(closed)
    assert cal.is_covered(date(2027, 6, 1)) and not cal.is_covered(date(2028, 6, 1))


def test_weekends_extra_holidays_and_navigation():
    cal = MarketCalendar(extra_holidays=[date(2026, 11, 26)])
    assert not cal.is_trading_day(date(2026, 11, 28)) and not cal.is_trading_day(date(2026, 11, 26))
    assert cal.next_trading_day(date(2026, 11, 25)) == date(2026, 11, 27)
    assert cal.next_trading_day(date(2026, 12, 30)) == date(2027, 1, 4)        # 연말 휴장 + 신정 + 주말
    assert cal.previous_trading_day(date(2027, 1, 4)) == date(2026, 12, 30)
    assert cal.session(date(2026, 11, 28)) is None


def test_sessions_regular_and_special():
    cal = MarketCalendar()
    s = cal.session(date(2026, 11, 25))
    assert s.open == datetime(2026, 11, 25, 9, 0, tzinfo=KST) and s.close == datetime(2026, 11, 25, 15, 30, tzinfo=KST)
    first = cal.session(date(2027, 1, 4))
    assert first.open.time() == time(10, 0) and first.close.time() == time(15, 30)
    csat = cal.session(date(2027, 11, 18))
    assert csat.open.time() == time(10, 0) and csat.close.time() == time(16, 30)
    forced = cal.session_assuming_open(date(2026, 12, 31))
    assert forced.open.time() == time(9, 0)


@pytest.mark.parametrize(
    "price, tick",
    [(1, 1), (1_999, 1), (2_000, 5), (4_995, 5), (5_000, 10), (19_990, 10), (20_000, 50), (49_950, 50),
     (50_000, 100), (199_900, 100), (200_000, 500), (499_500, 500), (500_000, 1_000), (1_234_000, 1_000)],
)
def test_tick_size_bands(price, tick):
    assert tick_size(price) == tick


def test_round_and_shift_ticks():
    assert round_to_tick(71_234, up=True) == 71_300 and round_to_tick(71_234, up=False) == 71_200
    assert round_to_tick(71_200, up=True) == 71_200 and round_to_tick(71_200.0000001, up=False) == 71_200
    assert round_to_tick(1_999.5, up=True) == 2_000
    assert round_to_tick(19_995, up=True) == 20_000 and round_to_tick(0, up=True) == 0
    assert shift_ticks(71_200, 3) == 71_500 and shift_ticks(71_200, -3) == 70_900
    assert shift_ticks(49_950, 2) == 50_100            # 50원 단위 → 경계를 넘으면 100원 단위
    assert shift_ticks(50_000, -1) == 49_950           # 경계 바로 아래는 아래 가격대 단위
    assert shift_ticks(2_000, -2) == 1_998
    assert shift_ticks(3, -5) == 0
    for p in (1_500, 4_990, 19_990, 49_950, 199_900, 499_500, 750_000):
        for n in (-7, -1, 0, 1, 7):
            q = shift_ticks(p, n)
            assert q % tick_size(q) == 0, (p, n, q)

"""한국거래소(KRX) 정규장 달력.

* 주말, 매년 날짜가 고정된 공휴일, 연말 휴장일(12/31)은 규칙으로 판단합니다.
* 음력 명절·대체공휴일·선거일처럼 해마다 달라지는 휴장일은 아래 표에 들어 있습니다.
  표가 없는 연도는 규칙만으로 판단하므로 일부 휴장일을 모를 수 있습니다
  (그 경우에도 실전 루프가 '실제로 거래가 일어나는지'를 확인하므로 주문이 나가지는 않습니다).
* 사용자는 config.toml 의 [schedule] extra_holidays 로 휴장일을 추가할 수 있습니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, Mapping

from .models import KST

REGULAR_OPEN = time(9, 0)
REGULAR_CLOSE = time(15, 30)

# 매년 같은 날짜의 휴장일 (월, 일)
FIXED_HOLIDAYS: frozenset[tuple[int, int]] = frozenset(
    {
        (1, 1),     # 신정
        (3, 1),     # 삼일절
        (5, 1),     # 근로자의 날 (증시 휴장)
        (5, 5),     # 어린이날
        (6, 6),     # 현충일
        (7, 17),    # 제헌절 (2026년부터 다시 공휴일)
        (8, 15),    # 광복절
        (10, 3),    # 개천절
        (10, 9),    # 한글날
        (12, 25),   # 성탄절
        (12, 31),   # 연말 휴장일
    }
)

# 해마다 달라지는 휴장일 (음력 명절, 대체공휴일, 선거일 등). 연도 → 날짜들.
# 2026년: 거래소·증권사 공지 기준. 2027년: 정부 월력요항 기준의 '예상'이며 거래소 공식 발표 전입니다
# (임시공휴일·선거일이 새로 지정되면 달라질 수 있음 → config.toml 의 extra_holidays 로 추가).
VARIABLE_HOLIDAYS: dict[int, frozenset[date]] = {
    2026: frozenset(
        {
            date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),   # 설 연휴
            date(2026, 3, 2),                                           # 삼일절 대체공휴일
            date(2026, 5, 25),                                          # 부처님오신날 대체공휴일
            date(2026, 6, 3),                                           # 전국동시지방선거
            date(2026, 8, 17),                                          # 광복절 대체공휴일
            date(2026, 9, 24), date(2026, 9, 25),                       # 추석 연휴
            date(2026, 10, 5),                                          # 개천절 대체공휴일
        }
    ),
    2027: frozenset(
        {
            date(2027, 2, 8), date(2027, 2, 9),                         # 설 연휴 + 대체공휴일
            date(2027, 5, 3),                                           # 노동절 대체공휴일
            date(2027, 5, 13),                                          # 부처님오신날
            date(2027, 7, 19),                                          # 제헌절 대체공휴일
            date(2027, 8, 16),                                          # 광복절 대체공휴일
            date(2027, 9, 14), date(2027, 9, 15), date(2027, 9, 16),    # 추석 연휴
            date(2027, 10, 4),                                          # 개천절 대체공휴일
            date(2027, 10, 11),                                         # 한글날 대체공휴일
            date(2027, 12, 27),                                         # 성탄절 대체공휴일
        }
    ),
}

# 개장/폐장 시각이 평소와 다른 날. 날짜 → (개장, 폐장)
# 2027년 두 날짜는 관례에 따른 '예상'입니다 (거래소 공지 전). 틀리더라도 실전 루프는
# 실제 거래가 시작된 것을 확인한 뒤에만 주문하므로 엉뚱한 시각에 주문이 나가지는 않습니다.
SPECIAL_SESSIONS: dict[date, tuple[time, time]] = {
    date(2026, 1, 2): (time(10, 0), time(15, 30)),      # 증시 개장식 (연초 첫 거래일)
    date(2026, 11, 19): (time(10, 0), time(16, 30)),    # 대학수학능력시험일
    date(2027, 1, 4): (time(10, 0), time(15, 30)),      # 연초 첫 거래일 (예상)
    date(2027, 11, 18): (time(10, 0), time(16, 30)),    # 대학수학능력시험일 (예상)
}


@dataclass(frozen=True)
class Session:
    """하루의 정규장 시간 (KST)."""

    day: date
    open: datetime
    close: datetime


class MarketCalendar:
    def __init__(
        self,
        *,
        extra_holidays: Iterable[date] = (),
        variable_holidays: Mapping[int, Iterable[date]] | None = None,
        special_sessions: Mapping[date, tuple[time, time]] | None = None,
    ) -> None:
        table = VARIABLE_HOLIDAYS if variable_holidays is None else variable_holidays
        self._variable: dict[int, frozenset[date]] = {y: frozenset(ds) for y, ds in table.items()}
        self._extra: frozenset[date] = frozenset(extra_holidays)
        self._special: dict[date, tuple[time, time]] = dict(
            SPECIAL_SESSIONS if special_sessions is None else special_sessions
        )

    def is_covered(self, day: date) -> bool:
        """이 날짜가 속한 연도의 변동 휴장일 표를 갖고 있는지."""
        return day.year in self._variable

    def is_trading_day(self, day: date) -> bool:
        if day.weekday() >= 5:
            return False
        if (day.month, day.day) in FIXED_HOLIDAYS:
            return False
        if day in self._extra:
            return False
        return day not in self._variable.get(day.year, frozenset())

    def session(self, day: date) -> Session | None:
        """그날의 정규장 시간. 휴장일이면 None."""
        if not self.is_trading_day(day):
            return None
        return self.session_assuming_open(day)

    def session_assuming_open(self, day: date) -> Session:
        """휴장일 여부와 무관하게 '그날 장이 열린다면'의 정규장 시간."""
        open_t, close_t = self._special.get(day, (REGULAR_OPEN, REGULAR_CLOSE))
        return Session(
            day=day,
            open=datetime.combine(day, open_t, tzinfo=KST),
            close=datetime.combine(day, close_t, tzinfo=KST),
        )

    def next_trading_day(self, after: date) -> date:
        """after 다음의 첫 개장일 (after 자신은 제외)."""
        d = after + timedelta(days=1)
        for _ in range(60):
            if self.is_trading_day(d):
                return d
            d += timedelta(days=1)
        raise RuntimeError("60일 안에 개장일을 찾지 못했습니다 (휴장일 설정을 확인하세요)")

    def previous_trading_day(self, before: date) -> date:
        """before 이전의 마지막 개장일 (before 자신은 제외)."""
        d = before - timedelta(days=1)
        for _ in range(60):
            if self.is_trading_day(d):
                return d
            d -= timedelta(days=1)
        raise RuntimeError("60일 안에 개장일을 찾지 못했습니다 (휴장일 설정을 확인하세요)")

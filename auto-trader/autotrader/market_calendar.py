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
        (8, 15),    # 광복절
        (10, 3),    # 개천절
        (10, 9),    # 한글날
        (12, 25),   # 성탄절
        (12, 31),   # 연말 휴장일
    }
)

# 해마다 달라지는 휴장일 (음력 명절, 대체공휴일, 선거일 등). 연도 → 날짜들.
VARIABLE_HOLIDAYS: dict[int, frozenset[date]] = {}

# 개장/폐장 시각이 평소와 다른 날. 날짜 → (개장, 폐장)
SPECIAL_SESSIONS: dict[date, tuple[time, time]] = {}


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

"""비공식 무료 시세 출처 (네이버 금융, 야후 파이낸스).

(구현 예정 — 이 파일은 데이터 담당이 채웁니다.)
"""

from __future__ import annotations

from datetime import date

from ..models import Bar


def fetch_naver_daily(symbol: str, start: date, end: date) -> list[Bar]:
    raise NotImplementedError


def fetch_yahoo_daily(symbol: str, start: date, end: date) -> list[Bar]:
    raise NotImplementedError

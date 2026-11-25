"""전략 인터페이스.

핵심 아이디어 — "하루 계획(DayPlan)"
=====================================
전략은 **장이 열리기 전에**, **전일까지 완성된 일봉만** 보고 오늘의 계획을
한 번 세웁니다. 장중에는 코어(TradingCore)가 그 계획을 기계적으로 실행합니다.

    plan = strategy.plan(history, position)

* ``history``  : 오늘 이전의 일봉 (오래된 것 → 최신 순). 오늘 봉은 절대 포함되지 않습니다.
* ``position`` : 장 시작 전 기준, 이 종목의 봇 보유 포지션 (없으면 None).

이 구조 덕분에 백테스트와 실전이 **완전히 같은 판단 코드**를 사용하고,
미래 데이터를 훔쳐보는 실수(look-ahead)가 구조적으로 불가능합니다.

DayPlan 이 표현할 수 있는 것
----------------------------
진입(EntryRule) — 해당 종목을 보유하고 있지 않을 때만 적용
  * OPEN     : 오늘 시가에 매수
  * BREAKOUT : 장중 가격이 (오늘 시가 + offset) 이상이 되면 매수 (변동성 돌파)

청산(ExitRule)
  * OPEN  : 장 시작 시점에 보유 중이면 시가에 매도
  * CLOSE : 장 마감 직전에 보유 중이면 매도 (오늘 진입한 포지션 포함 — 당일 청산)

손절/익절/추적손절은 전략이 아니라 리스크 설정([risk])으로 코어가 처리합니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Sequence

from ..models import Bar, Position


class EntryKind(str, Enum):
    OPEN = "open"
    BREAKOUT = "breakout"


class ExitKind(str, Enum):
    OPEN = "open"
    CLOSE = "close"


@dataclass(frozen=True)
class EntryRule:
    kind: EntryKind
    offset: float = 0.0   # BREAKOUT 전용: 목표가 = 당일 시가 + offset (원). 반드시 > 0
    score: float = 0.0    # 같은 날 여러 종목이 경쟁할 때 우선순위 (클수록 먼저)
    note: str = ""        # 로그/알림에 남길 설명

    def __post_init__(self) -> None:
        if self.kind == EntryKind.BREAKOUT and not self.offset > 0:
            raise ValueError("BREAKOUT 진입은 offset > 0 이어야 합니다")


@dataclass(frozen=True)
class ExitRule:
    kind: ExitKind
    note: str = ""


@dataclass(frozen=True)
class DayPlan:
    entry: EntryRule | None = None
    exit: ExitRule | None = None


HOLD = DayPlan()  # 아무것도 하지 않음


class Strategy(ABC):
    """모든 전략의 부모 클래스.

    하위 클래스 작성 규칙
    * ``name`` 클래스 변수: 설정 파일에서 쓰는 전략 이름
    * ``DEFAULTS`` 클래스 변수: 파라미터 기본값 dict (여기에 없는 파라미터는 오류)
    * ``warmup`` : 계획을 세우는 데 필요한 최소 일봉 수
    * ``plan()`` : 순수 함수여야 합니다 (같은 입력 → 같은 출력, 외부 상태/시계/난수 사용 금지)
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    DEFAULTS: ClassVar[dict[str, Any]] = {}

    def __init__(self, **params: Any) -> None:
        unknown = set(params) - set(self.DEFAULTS)
        if unknown:
            raise ValueError(
                f"전략 '{self.name}' 에 없는 파라미터: {sorted(unknown)} "
                f"(사용 가능: {sorted(self.DEFAULTS)})"
            )
        self.params: dict[str, Any] = {**self.DEFAULTS, **params}
        self.validate()

    def validate(self) -> None:
        """파라미터 검증. 잘못되면 ValueError."""

    @property
    @abstractmethod
    def warmup(self) -> int:
        """plan() 에 필요한 최소 일봉 개수. history 가 이보다 짧으면 코어가 plan() 을 부르지 않습니다."""

    @abstractmethod
    def plan(self, history: Sequence[Bar], position: Position | None) -> DayPlan:
        """오늘의 계획을 반환합니다. ``len(history) >= self.warmup`` 이 보장됩니다."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.params})"

"""전략 목록(레지스트리).

설정 파일의 ``[strategy] name = "..."`` 에 쓸 수 있는 이름과 전략 클래스를 연결합니다.
새 전략을 추가하려면 전략 파일을 만들고 아래 ``_DISPLAY_ORDER`` 에 한 줄만 추가하면 됩니다.
"""

from __future__ import annotations

from typing import Any, Mapping

from .base import Strategy
from .bollinger_reversion import BollingerReversion
from .donchian_breakout import DonchianBreakout
from .momentum import Momentum
from .rsi_reversion import RsiReversion
from .sma_cross import SmaCross
from .volatility_breakout import VolatilityBreakout

# 도움말에 보여 줄 순서: 기본 전략 → 추세추종 계열 → 역추세(눌림목 매수) 계열
_DISPLAY_ORDER: tuple[type[Strategy], ...] = (
    VolatilityBreakout,
    SmaCross,
    DonchianBreakout,
    Momentum,
    RsiReversion,
    BollingerReversion,
)

STRATEGIES: dict[str, type[Strategy]] = {cls.name: cls for cls in _DISPLAY_ORDER}


def create_strategy(name: str, params: Mapping[str, Any] | None = None) -> Strategy:
    """이름과 파라미터로 전략 객체를 만듭니다.

    모르는 이름이면 사용 가능한 이름을 알려 주는 ValueError 를 내고,
    파라미터가 잘못되면 해당 전략이 내는 ValueError 가 그대로 전달됩니다.
    """
    cls = STRATEGIES.get(name) if isinstance(name, str) else None
    if cls is None:
        raise ValueError(f"알 수 없는 전략 이름: {name!r} (사용 가능: {', '.join(STRATEGIES)})")
    if params is None:
        return cls()
    if not isinstance(params, Mapping) or not all(isinstance(key, str) for key in params):
        raise ValueError(f"전략 '{name}' 의 파라미터는 '이름 = 값' 형태의 표여야 합니다 (입력값: {params!r})")
    return cls(**params)


def available_strategies() -> list[tuple[str, str, dict[str, Any]]]:
    """도움말 출력용: (이름, 한 줄 설명, 기본 파라미터) 목록."""
    return [(name, cls.description, dict(cls.DEFAULTS)) for name, cls in STRATEGIES.items()]


__all__ = ["STRATEGIES", "Strategy", "available_strategies", "create_strategy"]

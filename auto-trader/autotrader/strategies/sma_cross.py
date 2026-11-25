"""이동평균 골든크로스 추세추종 전략.

짧은 기간 평균(단기선)이 긴 기간 평균(장기선)보다 위에 있으면 "오르는 추세"로 보고
보유하고, 아래로 내려가면 추세가 꺾였다고 보고 파는 가장 고전적인 추세추종 방법입니다.

파라미터
--------
* ``fast``       : 단기 이동평균 기간(일). 기본 5
* ``slow``       : 장기 이동평균 기간(일). 기본 20. fast 보다 커야 합니다
* ``cross_only`` : true 면 단기선이 장기선을 **막 넘어선 날**(골든크로스)에만 삽니다.
                   false(기본)면 단기선이 위에 있는 동안은 언제든 삽니다
                   (손절 후 재진입 금지 기간이 끝나면 다시 살 수 있음).

매매 규칙 (전일 종가까지의 일봉으로 판단, 주문은 오늘 시가)
* 미보유: 단기선 > 장기선 이면 매수
* 보유  : 단기선 < 장기선 이면 매도
"""

from __future__ import annotations

from typing import Sequence

from ..indicators import close_prices, recent_bars, require_int, sma
from ..models import Bar, Position
from .base import HOLD, DayPlan, EntryKind, EntryRule, ExitKind, ExitRule, Strategy


class SmaCross(Strategy):
    name = "sma_cross"
    description = "이동평균 골든크로스 추세추종"
    DEFAULTS = {"fast": 5, "slow": 20, "cross_only": False}

    def validate(self) -> None:
        fast = require_int(self.params["fast"], "sma_cross.fast", minimum=1)
        slow = require_int(self.params["slow"], "sma_cross.slow", minimum=2)
        if fast >= slow:
            raise ValueError(f"sma_cross.fast({fast}) 는 sma_cross.slow({slow}) 보다 작아야 합니다")
        cross_only = self.params["cross_only"]
        if not isinstance(cross_only, bool):
            raise ValueError(f"sma_cross.cross_only 값은 true 또는 false 여야 합니다 (입력값: {cross_only!r})")

    @property
    def warmup(self) -> int:
        # 골든크로스 여부를 보려면 하루 전의 이동평균도 필요하므로 일봉이 하나 더 필요합니다.
        return self.params["slow"] + (1 if self.params["cross_only"] else 0)

    def plan(self, history: Sequence[Bar], position: Position | None) -> DayPlan:
        fast, slow = self.params["fast"], self.params["slow"]
        closes = close_prices(recent_bars(history, self.warmup))
        fast_ma, slow_ma = sma(closes, fast), sma(closes, slow)

        if position is not None:
            if fast_ma < slow_ma:
                note = f"{fast}일선({fast_ma:,.0f}) < {slow}일선({slow_ma:,.0f})"
                return DayPlan(exit=ExitRule(ExitKind.OPEN, note=note))
            return HOLD

        if not fast_ma > slow_ma:
            return HOLD
        note = f"{fast}일선({fast_ma:,.0f}) > {slow}일선({slow_ma:,.0f})"
        if self.params["cross_only"]:
            day_before = closes[:-1]
            if sma(day_before, fast) > sma(day_before, slow):
                return HOLD   # 하루 전에도 이미 위에 있었음 → 오늘 새로 생긴 골든크로스가 아님
            note = f"골든크로스: {note}"
        return DayPlan(entry=EntryRule(EntryKind.OPEN, score=fast_ma / slow_ma - 1.0, note=note))

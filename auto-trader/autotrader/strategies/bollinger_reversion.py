"""볼린저밴드 하단 반등 매수 전략.

볼린저밴드는 이동평균(중심선) 위아래로 "평소 움직임의 폭(표준편차)"만큼 띠를 그린 것입니다.
종가가 띠의 아래쪽(하단) 밖으로 밀려나면 "평소보다 지나치게 떨어졌다"고 보고 사고,
평균 수준으로 되돌아오면 팝니다. 떨어질 때 사는 전략이므로 손절 설정이 특히 중요합니다.

파라미터
--------
* ``period``  : 이동평균·표준편차 계산 기간(일). 기본 20
* ``num_std`` : 띠의 폭 (표준편차의 몇 배). 기본 2.0 (클수록 덜 자주 매수)
* ``exit_at`` : 어디까지 오르면 파는지. "middle"(기본) = 중심선, "upper" = 상단

매매 규칙 (전일 종가까지의 일봉으로 판단, 주문은 오늘 시가)
* 미보유: 어제 종가 < 하단 이면 매수
* 보유  : 어제 종가 > 중심선(또는 상단) 이면 매도
"""

from __future__ import annotations

from typing import Sequence

from ..indicators import bollinger, close_prices, recent_bars, require_int, require_number
from ..models import Bar, Position
from .base import HOLD, DayPlan, EntryKind, EntryRule, ExitKind, ExitRule, Strategy

EXIT_TARGETS = ("middle", "upper")


class BollingerReversion(Strategy):
    name = "bollinger_reversion"
    description = "볼린저밴드 하단 반등 매수"
    DEFAULTS = {"period": 20, "num_std": 2.0, "exit_at": "middle"}

    def validate(self) -> None:
        require_int(self.params["period"], "bollinger_reversion.period", minimum=2)
        num_std = require_number(self.params["num_std"], "bollinger_reversion.num_std")
        if not num_std > 0:
            raise ValueError(f"bollinger_reversion.num_std 값은 0보다 커야 합니다 (입력값: {num_std:g})")
        exit_at = self.params["exit_at"]
        if exit_at not in EXIT_TARGETS:
            raise ValueError(
                f'bollinger_reversion.exit_at 값은 "middle" 또는 "upper" 여야 합니다 (입력값: {exit_at!r})'
            )

    @property
    def warmup(self) -> int:
        return self.params["period"]

    def plan(self, history: Sequence[Bar], position: Position | None) -> DayPlan:
        closes = close_prices(recent_bars(history, self.warmup))
        lower, middle, upper = bollinger(closes, self.params["period"], self.params["num_std"])
        last_close = closes[-1]

        if position is not None:
            target, label = (upper, "상단") if self.params["exit_at"] == "upper" else (middle, "중심선")
            if last_close > target:
                note = f"종가({last_close:,.0f}) > 볼린저 {label}({target:,.0f})"
                return DayPlan(exit=ExitRule(ExitKind.OPEN, note=note))
            return HOLD

        if last_close < lower:
            note = f"종가({last_close:,.0f}) < 볼린저 하단({lower:,.0f})"
            return DayPlan(entry=EntryRule(EntryKind.OPEN, score=(lower - last_close) / last_close, note=note))
        return HOLD

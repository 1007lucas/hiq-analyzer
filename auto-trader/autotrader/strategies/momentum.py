"""절대 모멘텀 전략 (N일 수익률 추세추종).

"최근 N일 동안 오른 종목은 당분간 더 오르는 경향이 있다"는 관찰에 기대는 전략입니다.
N일 전보다 가격이 높으면 사서 보유하고, 낮아지면 팝니다.

파라미터
--------
* ``lookback``      : 매수 판단에 쓰는 수익률 기간(일). 기본 60 (약 3개월)
* ``exit_lookback`` : 매도 판단에 쓰는 수익률 기간(일). 0(기본) = lookback 과 같은 기간 사용.
                      lookback 보다 짧게 주면 추세가 꺾일 때 더 빨리 팝니다.

매매 규칙 (전일 종가까지의 일봉으로 판단, 주문은 오늘 시가)
* 미보유: lookback 일 수익률 > 0 이면 매수 (같은 날 여러 종목이면 수익률이 높은 종목 먼저)
* 보유  : exit_lookback 일 수익률 < 0 이면 매도
"""

from __future__ import annotations

from typing import Sequence

from ..indicators import close_prices, rate_of_change, recent_bars, require_int
from ..models import Bar, Position
from .base import HOLD, DayPlan, EntryKind, EntryRule, ExitKind, ExitRule, Strategy


class Momentum(Strategy):
    name = "momentum"
    description = "절대 모멘텀 (N일 수익률 추세추종)"
    DEFAULTS = {"lookback": 60, "exit_lookback": 0}

    def validate(self) -> None:
        require_int(self.params["lookback"], "momentum.lookback", minimum=1)
        require_int(self.params["exit_lookback"], "momentum.exit_lookback", minimum=0)

    @property
    def warmup(self) -> int:
        # N일 수익률에는 N일 전 종가와 어제 종가, 즉 N + 1 개의 일봉이 필요합니다.
        return max(self.params["lookback"], self.params["exit_lookback"]) + 1

    def plan(self, history: Sequence[Bar], position: Position | None) -> DayPlan:
        lookback = self.params["lookback"]
        closes = close_prices(recent_bars(history, self.warmup))

        if position is not None:
            days = self.params["exit_lookback"] or lookback
            change = rate_of_change(closes, days)
            if change < 0:
                return DayPlan(exit=ExitRule(ExitKind.OPEN, note=f"{days}일 수익률 {change:+.1%} (하락 전환)"))
            return HOLD

        change = rate_of_change(closes, lookback)
        if change > 0:
            note = f"{lookback}일 수익률 {change:+.1%} (상승 추세)"
            return DayPlan(entry=EntryRule(EntryKind.OPEN, score=change, note=note))
        return HOLD

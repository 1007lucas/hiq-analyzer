"""신고가 돌파 추세추종 전략 (터틀 트레이딩 / 돈치안 채널).

"최근 N일 중 가장 높은 가격을 뚫고 올라가면 새로운 상승 추세의 시작"이라고 보고 사고,
"최근 M일 중 가장 낮은 가격 아래로 내려가면 추세가 끝났다"고 보고 파는 전략입니다.

파라미터
--------
* ``entry_days`` : 매수 기준 기간(일). 기본 20 → 직전 20일 최고가를 종가가 넘으면 매수
* ``exit_days``  : 매도 기준 기간(일). 기본 10 → 직전 10일 최저가 아래로 종가가 내려가면 매도

매매 규칙 (전일 종가까지의 일봉으로 판단, 주문은 오늘 시가)
* 미보유: 어제 종가 > 그 전 entry_days 일의 최고가(고가 기준) 이면 매수
* 보유  : 어제 종가 < 그 전 exit_days 일의 최저가(저가 기준) 이면 매도

"그 전 N일"에는 어제 봉 자체를 넣지 않습니다. 어제 고가는 항상 어제 종가 이상이라,
어제를 포함하면 돌파가 영원히 일어나지 않기 때문입니다.
"""

from __future__ import annotations

from typing import Sequence

from ..indicators import close_prices, high_prices, highest, low_prices, lowest, recent_bars, require_int
from ..models import Bar, Position
from .base import HOLD, DayPlan, EntryKind, EntryRule, ExitKind, ExitRule, Strategy


class DonchianBreakout(Strategy):
    name = "donchian_breakout"
    description = "신고가 돌파 추세추종 (터틀)"
    DEFAULTS = {"entry_days": 20, "exit_days": 10}

    def validate(self) -> None:
        require_int(self.params["entry_days"], "donchian_breakout.entry_days", minimum=2)
        require_int(self.params["exit_days"], "donchian_breakout.exit_days", minimum=1)

    @property
    def warmup(self) -> int:
        return max(self.params["entry_days"], self.params["exit_days"]) + 1

    def plan(self, history: Sequence[Bar], position: Position | None) -> DayPlan:
        bars = recent_bars(history, self.warmup)
        last_close = close_prices(bars[-1:])[0]
        earlier = bars[:-1]   # 어제 봉을 뺀 그 이전 봉들

        if position is not None:
            days = self.params["exit_days"]
            floor = lowest(low_prices(earlier[-days:]), days)
            if last_close < floor:
                note = f"종가({last_close:,.0f}) < 직전 {days}일 최저가({floor:,.0f})"
                return DayPlan(exit=ExitRule(ExitKind.OPEN, note=note))
            return HOLD

        days = self.params["entry_days"]
        ceiling = highest(high_prices(earlier[-days:]), days)
        if last_close > ceiling:
            note = f"종가({last_close:,.0f}) > 직전 {days}일 최고가({ceiling:,.0f})"
            return DayPlan(entry=EntryRule(EntryKind.OPEN, score=last_close / ceiling - 1.0, note=note))
        return HOLD

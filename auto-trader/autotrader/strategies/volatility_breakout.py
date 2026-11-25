"""변동성 돌파 전략 (래리 윌리엄스).

"어제 하루 동안 움직인 폭의 일정 비율만큼 오늘 시가보다 오르면, 오늘은 상승하는
날"이라고 보고 그 순간 따라 사는 단기 전략입니다.

    목표가 = 오늘 시가 + k × (어제 고가 − 어제 저가)

장중에 가격이 목표가 이상이 되면 매수하고, 다음 날 시가(또는 당일 종가)에 팝니다.

파라미터
--------
* ``k``        : 돌파 계수. 0 초과 2 이하. 기본 0.5 (클수록 덜 자주, 더 확실할 때만 매수)
* ``hold``     : 언제 파는지.
                 "next_open"(기본) = 다음 거래일 시가에 매도 (그날 다시 돌파하면 재매수 가능)
                 "close"           = 산 날 종가에 매도 (하루 안에 끝냄)
* ``trend_ma`` : 추세 필터. 0 보다 크면 "어제 종가가 이 기간 이동평균보다 위"일 때만 매수. 0 = 사용 안 함(기본)

어제 고가와 저가가 같으면(거래정지, 종일 상한가 등) 목표가를 정할 수 없어 그날은 매수하지 않습니다.
"""

from __future__ import annotations

import math
from typing import Sequence

from ..indicators import close_prices, recent_bars, require_int, require_number, sma
from ..models import Bar, Position
from .base import DayPlan, EntryKind, EntryRule, ExitKind, ExitRule, Strategy

HOLD_MODES = ("next_open", "close")


class VolatilityBreakout(Strategy):
    name = "volatility_breakout"
    description = "변동성 돌파 (래리 윌리엄스)"
    DEFAULTS = {"k": 0.5, "hold": "next_open", "trend_ma": 0}

    def validate(self) -> None:
        k = require_number(self.params["k"], "volatility_breakout.k")
        if not 0 < k <= 2:
            raise ValueError(f"volatility_breakout.k 값은 0 초과 2 이하여야 합니다 (입력값: {k:g})")
        hold = self.params["hold"]
        if hold not in HOLD_MODES:
            raise ValueError(
                f'volatility_breakout.hold 값은 "next_open" 또는 "close" 여야 합니다 (입력값: {hold!r})'
            )
        require_int(self.params["trend_ma"], "volatility_breakout.trend_ma", minimum=0)

    @property
    def warmup(self) -> int:
        return max(1, self.params["trend_ma"])

    def plan(self, history: Sequence[Bar], position: Position | None) -> DayPlan:
        bars = recent_bars(history, self.warmup)
        # 보유 중이어도 진입 규칙을 함께 냅니다: 코어는 미보유일 때만 진입을 적용하므로,
        # 시가에 어제 매수분을 판 뒤 같은 날 다시 돌파하면 새로 살 수 있습니다.
        return DayPlan(entry=self._entry(bars), exit=self._exit(position))

    def _entry(self, bars: Sequence[Bar]) -> EntryRule | None:
        k = self.params["k"]
        last = bars[-1]
        day_range = last.high - last.low
        offset = k * day_range
        if not 0 < offset < math.inf:   # 변동폭이 없거나(0) 시세가 깨진 날(NaN 포함)은 목표가를 만들 수 없음
            return None
        note = f"전일 변동폭 {day_range:,.0f} × k {k:g} = {offset:,.0f}"
        trend_ma = self.params["trend_ma"]
        if trend_ma > 0:
            closes = close_prices(bars)
            trend = sma(closes, trend_ma)
            if not closes[-1] > trend:
                return None
            note += f", 종가({closes[-1]:,.0f}) > {trend_ma}일선({trend:,.0f})"
        return EntryRule(EntryKind.BREAKOUT, offset=offset, note=note)

    def _exit(self, position: Position | None) -> ExitRule | None:
        if self.params["hold"] == "close":
            # 오늘 사는 물량은 아직 포지션이 아니므로, 보유 여부와 관계없이 항상 종가 청산을 걸어 둡니다.
            return ExitRule(ExitKind.CLOSE, note="변동성 돌파 매수분은 당일 종가에 매도")
        if position is not None:
            return ExitRule(ExitKind.OPEN, note="변동성 돌파 매수분은 다음 거래일 시가에 매도")
        return None

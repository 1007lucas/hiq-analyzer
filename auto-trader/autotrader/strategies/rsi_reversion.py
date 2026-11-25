"""RSI 과매도 반등 매수 전략.

RSI 는 최근 상승폭과 하락폭의 비율을 0 ~ 100 으로 나타낸 지표입니다. 값이 아주 낮으면
"단기간에 너무 많이 팔렸다(과매도)"고 보고 반등을 기대해 사고, 어느 정도 회복하면 팝니다.
추세추종과 반대로 **떨어질 때 사는** 전략이므로 손절 설정([risk] stop_loss_pct)이 특히 중요합니다.

파라미터
--------
* ``period``        : RSI 계산 기간(일). 기본 14
* ``buy_below``     : RSI 가 이 값보다 낮으면 매수. 기본 30
* ``sell_above``    : RSI 가 이 값보다 높으면 매도. 기본 55
* ``trend_ma``      : 추세 필터. 0 보다 크면 "종가가 이 기간 이동평균보다 위"일 때만 매수
                      (큰 흐름이 상승일 때의 눌림목만 노림). 0 = 사용 안 함(기본)
* ``max_hold_days`` : 이 거래일 수만큼 보유했는데도 반등이 없으면 포기하고 매도. 0 = 사용 안 함. 기본 10

매매 규칙 (전일 종가까지의 일봉으로 판단, 주문은 오늘 시가)
* 미보유: RSI < buy_below (그리고 추세 필터 통과) 이면 매수
* 보유  : RSI > sell_above 이거나 보유 기간이 max_hold_days 에 도달하면 매도
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

from ..indicators import close_prices, recent_bars, require_int, require_number, rsi, rsi_min_bars, sma
from ..models import Bar, Position
from .base import HOLD, DayPlan, EntryKind, EntryRule, ExitKind, ExitRule, Strategy


def _bars_since(bars: Sequence[Bar], entry_date: date) -> int:
    """진입일(포함) 이후의 일봉 개수 = 진입일부터 어제까지 보유한 거래일 수."""
    return sum(1 for bar in bars if bar.date >= entry_date)


class RsiReversion(Strategy):
    name = "rsi_reversion"
    description = "RSI 과매도 반등 매수"
    DEFAULTS = {"period": 14, "buy_below": 30.0, "sell_above": 55.0, "trend_ma": 0, "max_hold_days": 10}

    def validate(self) -> None:
        require_int(self.params["period"], "rsi_reversion.period", minimum=2)
        buy_below = require_number(self.params["buy_below"], "rsi_reversion.buy_below")
        sell_above = require_number(self.params["sell_above"], "rsi_reversion.sell_above")
        if not 0 < buy_below < sell_above < 100:
            raise ValueError(
                "rsi_reversion: 0 < buy_below < sell_above < 100 이어야 합니다 "
                f"(입력값: buy_below={buy_below:g}, sell_above={sell_above:g})"
            )
        require_int(self.params["trend_ma"], "rsi_reversion.trend_ma", minimum=0)
        require_int(self.params["max_hold_days"], "rsi_reversion.max_hold_days", minimum=0)

    @property
    def warmup(self) -> int:
        return max(
            rsi_min_bars(self.params["period"]),
            self.params["trend_ma"],
            self.params["max_hold_days"] + 1,
        )

    def plan(self, history: Sequence[Bar], position: Position | None) -> DayPlan:
        period = self.params["period"]
        bars = recent_bars(history, self.warmup)
        closes = close_prices(bars)
        value = rsi(closes, period)

        if position is not None:
            sell_above = self.params["sell_above"]
            if value > sell_above:
                return DayPlan(exit=ExitRule(ExitKind.OPEN, note=f"RSI({period}) {value:.1f} > {sell_above:g}"))
            max_hold = self.params["max_hold_days"]
            # 최근 max_hold 개 봉이 모두 진입일 이후라면 보유 기간이 한도에 도달한 것입니다
            # (그보다 오래된 봉은 볼 필요가 없으므로 보지 않습니다).
            if max_hold > 0 and _bars_since(bars[-max_hold:], position.entry_date) >= max_hold:
                return DayPlan(exit=ExitRule(ExitKind.OPEN, note=f"보유 {max_hold}거래일 경과 (반등 없음, 기간 청산)"))
            return HOLD

        buy_below = self.params["buy_below"]
        if not value < buy_below:
            return HOLD
        note = f"RSI({period}) {value:.1f} < {buy_below:g}"
        trend_ma = self.params["trend_ma"]
        if trend_ma > 0:
            trend = sma(closes, trend_ma)
            if not closes[-1] > trend:
                return HOLD
            note += f", 종가({closes[-1]:,.0f}) > {trend_ma}일선({trend:,.0f})"
        return DayPlan(entry=EntryRule(EntryKind.OPEN, score=buy_below - value, note=note))

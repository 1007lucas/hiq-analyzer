"""테스트 공용 도구."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autotrader.brokers.base import Broker  # noqa: E402
from autotrader.models import Bar, OrderRequest, OrderResult, OrderStatus, Position  # noqa: E402
from autotrader.strategies.base import DayPlan, Strategy  # noqa: E402


def make_bars(closes: Sequence[float], start: date = date(2024, 1, 2), spread: float = 0.0) -> list[Bar]:
    """종가 목록으로 평일만 있는 일봉을 만듭니다. open=전일 종가(첫날은 종가), high/low=±spread."""
    bars: list[Bar] = []
    d = start
    prev = closes[0]
    for c in closes:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        o = prev
        hi = max(o, c) * (1 + spread)
        lo = min(o, c) * (1 - spread)
        bars.append(Bar(d, float(o), float(hi), float(lo), float(c), 1000.0))
        prev = c
        d += timedelta(days=1)
    return bars


class ScriptedStrategy(Strategy):
    """테스트용: 날짜(history 길이)에 따라 미리 정해 둔 DayPlan 을 돌려주는 전략."""

    name = "scripted"
    DEFAULTS = {"warmup": 1}

    def __init__(self, plans=None, default: DayPlan = DayPlan(), **params) -> None:
        super().__init__(**params)
        self.plans = plans or {}       # (symbol_first_close, len(history)) 대신 단순히 len(history) → DayPlan
        self.default = default
        self.calls: list[tuple[int, Position | None]] = []

    @property
    def warmup(self) -> int:
        return int(self.params["warmup"])

    def plan(self, history, position):
        self.calls.append((len(history), position))
        p = self.plans.get(len(history), self.default)
        return p(history, position) if callable(p) else p


class ScriptedBroker(Broker):
    """테스트용: 주문마다 미리 정한 결과를 돌려주는 브로커 (기본은 기준가에 전량 체결)."""

    name = "scripted"

    def __init__(self) -> None:
        self.requests: list[OrderRequest] = []
        self.script: list = []          # 각 항목: OrderStatus | callable(req) -> OrderResult | Exception
        self.buy_cap: int | None = None
        self.sell_cap: int | None = None
        self.recovered: OrderResult | None = None

    def submit_order(self, req: OrderRequest) -> OrderResult:
        self.requests.append(req)
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            if callable(item):
                return item(req)
            if item == OrderStatus.FILLED:
                return OrderResult(req, OrderStatus.FILLED, req.qty, req.ref_price, "S1")
            return OrderResult(req, item, 0, 0.0, "S1", "scripted")
        return OrderResult(req, OrderStatus.FILLED, req.qty, req.ref_price, f"S{len(self.requests)}")

    def max_buy_qty(self, symbol: str, price: float) -> int | None:
        return self.buy_cap

    def sellable_qty(self, symbol: str) -> int | None:
        return self.sell_cap

    def recover_order(self, req, since):
        return self.recovered


@pytest.fixture
def bars_factory():
    return make_bars

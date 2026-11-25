"""가상 체결 브로커 (백테스트 / 페이퍼 트레이딩용).

주문을 받으면 요청의 기준가(ref_price)에 슬리피지를 불리하게 적용해 즉시
전량 체결시킵니다. 현금/포지션 장부는 TradingCore 가 관리하므로 이 브로커는
상태가 거의 없습니다. 수수료·세금도 코어의 비용 모델이 계산합니다.
"""

from __future__ import annotations

from ..models import OrderRequest, OrderResult, OrderStatus, Side
from .base import Broker


class PaperBroker(Broker):
    name = "paper"

    def __init__(self, slippage_rate: float = 0.0) -> None:
        if slippage_rate < 0:
            raise ValueError("slippage_rate 는 0 이상이어야 합니다")
        self.slippage_rate = float(slippage_rate)
        self._seq = 0

    def submit_order(self, req: OrderRequest) -> OrderResult:
        if req.qty <= 0 or req.ref_price <= 0:
            return OrderResult(req, OrderStatus.REJECTED, message="수량 또는 가격이 올바르지 않습니다")
        self._seq += 1
        if req.side == Side.BUY:
            price = req.ref_price * (1.0 + self.slippage_rate)
        else:
            price = req.ref_price * (1.0 - self.slippage_rate)
        return OrderResult(
            request=req,
            status=OrderStatus.FILLED,
            filled_qty=req.qty,
            avg_price=price,
            broker_order_id=f"PAPER-{self._seq}",
        )

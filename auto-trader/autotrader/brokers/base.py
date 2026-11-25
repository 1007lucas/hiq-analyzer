"""브로커 / 시세 인터페이스.

* ``Broker``     : 주문 실행 + 계좌 조회
* ``MarketData`` : 시세 조회 (현재가, 일봉, 휴장일)

KIS 클라이언트는 둘 다 구현하고, PaperBroker 는 Broker 만 구현합니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from ..models import AccountSnapshot, Bar, OrderRequest, OrderResult, Quote


class BrokerError(Exception):
    """브로커/시세 API 호출 실패."""


class Broker(ABC):
    name: str = "broker"

    @abstractmethod
    def submit_order(self, req: OrderRequest) -> OrderResult:
        """주문을 내고 **최종 상태가 될 때까지 기다린 뒤** 결과를 반환합니다.

        * 예외를 던지지 말고, 실패는 OrderResult(status=REJECTED/UNKNOWN) 로 표현합니다.
        * 타임아웃 시 미체결 잔량은 반드시 취소하고 PARTIAL/REJECTED 로 반환합니다.
        * 주문이 접수됐는지조차 알 수 없으면 UNKNOWN (코어가 해당 종목을 잠그고 알림).
        """

    def max_buy_qty(self, symbol: str, price: float) -> int | None:
        """이 가격에 지금 살 수 있는 최대 수량. 알 수 없으면 None (제한 없음으로 취급)."""
        return None

    def sellable_qty(self, symbol: str) -> int | None:
        """지금 매도 가능한 수량. 알 수 없으면 None (제한 없음으로 취급)."""
        return None

    def get_account(self) -> AccountSnapshot | None:
        """계좌 요약. 지원하지 않으면 None."""
        return None

    def recover_order(self, req: OrderRequest, since: datetime) -> OrderResult | None:
        """재시작 복구용: ``since`` 이후 접수된 주문 중 req 와 일치하는 것을 찾아 최종 결과를 반환.

        찾지 못하면 None (= 주문이 접수되지 않은 것으로 간주).
        """
        return None


class MarketData(ABC):
    name: str = "market"

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        """현재가. 실패 시 BrokerError."""

    @abstractmethod
    def get_daily_bars(self, symbol: str, start: date, end: date) -> list[Bar]:
        """[start, end] 구간의 수정주가 일봉 (오래된 것 → 최신 순). 실패 시 BrokerError."""

    def is_trading_day(self, day: date) -> bool | None:
        """개장일 여부. 알 수 없으면 None (내장 달력으로 판단)."""
        return None

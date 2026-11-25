"""공용 데이터 모델.

모든 모듈이 공유하는 '계약(contract)' 입니다. 필드를 바꾸면 core / broker /
backtest / live 가 모두 영향을 받으므로 신중하게 변경하세요.

가격 단위는 원(KRW). 한국 주식은 정수 가격이지만 지표 계산과 평균단가 때문에
float 로 다룹니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum

# 한국 표준시. 한국은 서머타임이 없으므로 고정 오프셋으로 충분합니다.
# (zoneinfo 는 Windows 에서 tzdata 패키지가 필요하므로 일부러 쓰지 않습니다.)
KST = timezone(timedelta(hours=9), "KST")


def now_kst() -> datetime:
    return datetime.now(KST)


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    FILLED = "filled"        # 전량 체결
    PARTIAL = "partial"      # 일부만 체결되고 잔량은 취소됨 (filled_qty > 0)
    REJECTED = "rejected"    # 거부 / 미체결 취소 (filled_qty == 0, 주문은 살아있지 않음이 확실)
    UNKNOWN = "unknown"      # 전송/체결 여부를 확인할 수 없음 (네트워크 오류 등) — 수동 확인 필요


@dataclass(frozen=True)
class Bar:
    """일봉 1개."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Quote:
    """현재가 스냅샷."""

    symbol: str
    price: float                 # 현재가
    open: float = 0.0            # 당일 시가 (장 시작 전이면 0)
    high: float = 0.0            # 당일 고가
    low: float = 0.0             # 당일 저가
    prev_close: float = 0.0      # 전일 종가
    volume: float = 0.0          # 누적 거래량
    upper_limit: float = 0.0     # 상한가 (모르면 0)
    lower_limit: float = 0.0     # 하한가 (모르면 0)
    halted: bool = False         # 거래정지 등으로 매매 불가
    time: datetime | None = None


@dataclass(frozen=True)
class OrderRequest:
    """코어가 브로커에 보내는 주문 요청. 코어는 항상 '즉시 체결'을 원합니다.

    실제로 시장가로 낼지, 현재가+n틱 지정가로 낼지는 브로커 구현이 결정합니다.
    """

    symbol: str
    side: Side
    qty: int
    ref_price: float             # 판단 시점의 기준가격 (모의 체결가 계산 / 지정가 산정 / 로그용)
    reason: str = ""
    client_id: str = ""          # 봇 내부 주문 식별자 (로그 추적용)


@dataclass
class OrderResult:
    """브로커가 돌려주는 '최종' 주문 결과.

    submit_order 는 주문이 최종 상태가 될 때까지 (체결 완료, 또는 미체결 잔량
    취소 완료) 기다렸다가 반환해야 합니다. 반환 시점에 살아있는 미체결 주문이
    남아 있으면 안 됩니다 (그럴 수밖에 없으면 UNKNOWN).
    """

    request: OrderRequest
    status: OrderStatus
    filled_qty: int = 0
    avg_price: float = 0.0       # 평균 체결가 (filled_qty > 0 일 때만 의미 있음)
    broker_order_id: str = ""
    message: str = ""
    time: datetime | None = None


@dataclass
class Position:
    """봇이 직접 매수해서 관리 중인 포지션 (계좌의 수동 보유분과 구분)."""

    symbol: str
    qty: int
    avg_price: float
    entry_date: date
    highest_price: float         # 진입 이후 최고가 (추적손절 기준, 장 마감 후 갱신)
    entry_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "qty": self.qty,
            "avg_price": self.avg_price,
            "entry_date": self.entry_date.isoformat(),
            "highest_price": self.highest_price,
            "entry_reason": self.entry_reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Position":
        return cls(
            symbol=str(d["symbol"]),
            qty=int(d["qty"]),
            avg_price=float(d["avg_price"]),
            entry_date=date.fromisoformat(d["entry_date"]),
            highest_price=float(d.get("highest_price", d["avg_price"])),
            entry_reason=str(d.get("entry_reason", "")),
        )


@dataclass(frozen=True)
class BrokerPosition:
    """증권사 계좌에 실제로 있는 보유 종목 (수동 매수분 포함)."""

    symbol: str
    qty: int
    sellable_qty: int
    avg_price: float
    name: str = ""


@dataclass(frozen=True)
class AccountSnapshot:
    """증권사 계좌 요약."""

    cash: float                              # 지금 주문에 쓸 수 있는 현금
    total_equity: float                      # 총 평가금액 (현금 + 주식)
    positions: dict[str, BrokerPosition] = field(default_factory=dict)

"""한국거래소 매매 규칙 중 주문 가격 계산에 필요한 것.

호가 단위(틱): 주문 가격은 정해진 단위의 배수여야 합니다.
  주식(코스피·코스닥 공통, 2023-01-25 시행)
    2,000원 미만 1원 / 5,000원 미만 5원 / 20,000원 미만 10원 / 50,000원 미만 50원
    200,000원 미만 100원 / 500,000원 미만 500원 / 그 이상 1,000원
  ETF·ETN: 2,000원 미만 1원, 그 이상 5원

이 모듈은 항상 **주식용 표**를 씁니다. 2,000원 이상에서 주식의 호가 단위는 모두 5원의 배수라
ETF 에도 유효한 가격이 되기 때문입니다 (ETF 에는 조금 더 성긴 가격이 될 뿐 주문 거부는 없습니다).
"""

from __future__ import annotations

import math

_BANDS: tuple[tuple[float, int], ...] = (
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
)
_TOP_TICK = 1_000


def tick_size(price: float) -> int:
    """이 가격대의 호가 단위(원)."""
    for limit, tick in _BANDS:
        if price < limit:
            return tick
    return _TOP_TICK


def round_to_tick(price: float, *, up: bool) -> int:
    """가격을 호가 단위에 맞춥니다. up=True 면 올림, False 면 내림."""
    if price <= 0:
        return 0
    tick = tick_size(price)
    units = price / tick
    n = math.ceil(units - 1e-9) if up else math.floor(units + 1e-9)
    out = int(n) * tick
    # 올림/내림으로 가격대가 바뀌면 새 가격대의 호가 단위에 다시 맞춥니다.
    new_tick = tick_size(out)
    if new_tick != tick:
        units = out / new_tick
        n = math.ceil(units - 1e-9) if up else math.floor(units + 1e-9)
        out = int(n) * new_tick
    return max(out, 0)


def shift_ticks(price: float, ticks: int) -> int:
    """가격에서 호가 단위로 ticks 칸 이동한 가격 (양수 = 위로, 음수 = 아래로). 가격대 경계를 넘으면 단위가 바뀝니다."""
    p = round_to_tick(price, up=ticks >= 0)
    step = 1 if ticks >= 0 else -1
    for _ in range(abs(int(ticks))):
        if step > 0:
            p += tick_size(p)
        else:
            # 경계값(예: 2,000원)에서 한 칸 아래는 아래 가격대의 단위를 따릅니다.
            p -= tick_size(p - 1e-6)
            if p <= 0:
                return 0
    return int(p)

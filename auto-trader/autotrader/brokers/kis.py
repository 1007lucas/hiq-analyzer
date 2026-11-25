"""한국투자증권(KIS) Open API 클라이언트 — 국내주식 현금 매매 전용.

표준 라이브러리(urllib)만 사용합니다. 실전 서버와 모의투자 서버를 모두 지원합니다.

구현 근거: 한국투자증권 공식 예제 저장소(koreainvestment/open-trading-api, 2026-11 기준)의
엔드포인트·TR ID·필드명을 따릅니다. 공식 문서로 확정하지 못한 동작(오류 응답의 HTTP 상태,
주문 직후 조회 지연, 취소 주문의 표시 방식 등)은 **어느 쪽이어도 안전하도록** 방어적으로
처리하고, 확신할 수 없으면 주문 결과를 UNKNOWN 으로 돌려 사람이 확인하게 합니다.

안전 원칙
* 주문(POST)은 절대 자동 재전송하지 않습니다 (중복 주문 방지).
* 주문이 서버에 닿았는지 모르면 주문 내역을 조회해 확인하고, 그래도 모르면 UNKNOWN.
* submit_order 가 끝났을 때 살아 있는 미체결 주문을 남기지 않습니다 (시간 초과 시 잔량 취소).
* 앱키·시크릿·토큰은 로그나 오류 메시지에 남기지 않습니다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time as _time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

from ..config import KisConfig
from ..market_rules import shift_ticks
from ..models import (
    KST,
    AccountSnapshot,
    Bar,
    BrokerPosition,
    OrderRequest,
    OrderResult,
    OrderStatus,
    Quote,
    Side,
    now_kst,
)
from .base import Broker, BrokerError, MarketData

log = logging.getLogger("autotrader.kis")

REAL_BASE = "https://openapi.koreainvestment.com:9443"
MOCK_BASE = "https://openapivts.koreainvestment.com:29443"

# TR ID (실전용). 모의투자는 첫 글자를 V 로 바꾼 ID 를 씁니다 (시세 조회 TR 은 실전/모의 공통).
TR_BUY = "TTTC0012U"
TR_SELL = "TTTC0011U"
TR_CANCEL = "TTTC0013U"
TR_DAILY_CCLD = "TTTC0081R"
TR_BALANCE = "TTTC8434R"
TR_PSBL_ORDER = "TTTC8908R"
TR_PRICE = "FHKST01010100"
TR_DAILY_CHART = "FHKST03010100"
TR_HOLIDAY = "CTCA0903R"            # 실전 전용 (모의투자 미지원)

DEFAULT_CALLS_PER_SEC = {False: 10.0, True: 1.8}   # 실전 / 모의 (공식 한도보다 여유 있게)
TOKEN_REFRESH_MARGIN = timedelta(minutes=10)
TOKEN_ISSUE_COOLDOWN_SEC = 65.0     # 토큰 발급은 1분에 1회로 제한됨
HTTP_TIMEOUT_SEC = 10.0
GET_ATTEMPTS = 3
MAX_PAGES = 30
FILL_POLL_SEC = 1.0
CANCEL_SETTLE_SEC = 8.0             # 취소 주문 후 최종 상태가 조회될 때까지 기다리는 시간
QUOTE_CACHE_SEC = 30.0

Transport = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, Mapping[str, str], bytes]]


class KisApiError(BrokerError):
    """서버가 요청을 명시적으로 거부함 (rt_cd != "0"). 요청은 처리되지 않았습니다."""

    def __init__(self, code: str, message: str, status: int = 0) -> None:
        super().__init__(f"[{code or status}] {message}".strip())
        self.code = code
        self.message = message
        self.status = status


class KisTransportError(BrokerError):
    """요청이 서버에 닿았는지, 처리되었는지 알 수 없음 (네트워크 오류, 해석 불가 응답)."""


def _urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
) -> tuple[int, Mapping[str, str], bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - 고정된 https 주소
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as e:
        # KIS 는 오류도 JSON 본문으로 알려 주므로 4xx/5xx 의 본문을 읽어 돌려줍니다.
        return e.code, dict(e.headers.items()) if e.headers else {}, e.read()


def _i(value: Any) -> int:
    """'0000123', '71,200', '71200.00', '' → int (해석 불가는 0)."""
    try:
        return int(float(str(value).replace(",", "").strip() or 0))
    except (TypeError, ValueError):
        return 0


def _f(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _upper_keys(d: Any) -> dict[str, Any]:
    return {str(k).upper(): v for k, v in d.items()} if isinstance(d, Mapping) else {}


def _same_order_no(a: Any, b: Any) -> bool:
    """주문번호 비교 (앞자리 0 채움 차이 무시)."""
    sa, sb = str(a or "").strip().lstrip("0"), str(b or "").strip().lstrip("0")
    return bool(sa) and sa == sb


@dataclass
class _OrderState:
    found: bool = False
    ord_qty: int = 0
    filled: int = 0
    remaining: int = 0
    rejected: int = 0
    cancelled: bool = False
    cancel_qty: int = 0
    avg_price: float = 0.0
    org_no: str = ""

    def final(self, *, after_cancel: bool = False) -> bool:
        """더 이상 체결될 수 없는 상태인지 (살아 있는 잔량 없음).

        after_cancel: 우리가 낸 취소 요청이 접수된 뒤라면 '잔량 0' 만으로도 끝난 것으로 봅니다.
        (그 전에는 접수 직후 행이 덜 채워진 상태일 수 있어 잔량 0 만으로는 판단하지 않습니다.)
        """
        if not self.found:
            return False
        if self.ord_qty > 0 and self.filled >= self.ord_qty:
            return True
        if self.rejected > 0 or self.cancelled:
            return True
        if self.ord_qty > 0 and self.filled + self.cancel_qty >= self.ord_qty:
            return True
        return after_cancel and self.remaining <= 0


class KisClient(Broker, MarketData):
    name = "kis"

    def __init__(
        self,
        cfg: KisConfig,
        *,
        token_dir: Path,
        transport: Transport | None = None,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] | None = None,
        monotonic: Callable[[], float] | None = None,
        base_url: str | None = None,
    ) -> None:
        if not cfg.configured:
            where = "KIS_MOCK_APP_KEY / KIS_MOCK_APP_SECRET / KIS_MOCK_ACCOUNT" if cfg.mock else "KIS_APP_KEY / KIS_APP_SECRET / KIS_ACCOUNT"
            raise BrokerError(f"한국투자증권 API 설정이 없습니다. .env 파일에 {where} 를 넣어 주세요.")
        self.cfg = cfg
        self.mock = cfg.mock
        self.base_url = (base_url or (MOCK_BASE if cfg.mock else REAL_BASE)).rstrip("/")
        self.token_dir = Path(token_dir)
        self._transport: Transport = transport or _urllib_transport
        self._now = now or now_kst
        self._sleep = sleep or _time.sleep
        self._monotonic = monotonic or _time.monotonic
        rate = cfg.max_calls_per_sec or DEFAULT_CALLS_PER_SEC[cfg.mock]
        self._min_interval = 1.0 / rate
        self._next_call_at = 0.0
        self._token: str = ""
        self._token_expires: datetime | None = None
        self._last_issue_attempt: float | None = None
        self._quotes: dict[str, tuple[float, Quote]] = {}
        self._holidays: dict[str, bool] = {}
        self._holiday_checked: date | None = None
        key_id = hashlib.sha256(cfg.app_key.encode("utf-8")).hexdigest()[:12]
        env = "mock" if cfg.mock else "real"
        self._token_file = self.token_dir / f"kis-token-{env}-{key_id}.json"
        self._holiday_file = self.token_dir / "kis-holidays.json"

    # ------------------------------------------------------------------ #
    # 공통: TR ID, 속도 제한, 토큰, 요청
    # ------------------------------------------------------------------ #
    def _tr(self, real_id: str) -> str:
        """매매·계좌 TR ID 를 환경에 맞게 변환 (모의투자는 첫 글자 V)."""
        return "V" + real_id[1:] if self.mock else real_id

    def _throttle(self) -> None:
        wait = self._next_call_at - self._monotonic()
        if wait > 0:
            self._sleep(wait)
        self._next_call_at = max(self._monotonic(), self._next_call_at) + self._min_interval

    def _redact(self, text: str) -> str:
        for secret in (self.cfg.app_key, self.cfg.app_secret, self._token):
            if secret:
                text = text.replace(secret, "***")
        return text

    # -- 토큰 ----------------------------------------------------------------
    def _load_token_file(self) -> None:
        try:
            data = json.loads(self._token_file.read_text(encoding="utf-8"))
            token = str(data["access_token"])
            expires = datetime.fromisoformat(str(data["expires_at"]))
        except (OSError, ValueError, KeyError, TypeError):
            return
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=KST)
        if token:
            self._token, self._token_expires = token, expires

    def _save_token_file(self) -> None:
        try:
            self.token_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._token_file.with_name(self._token_file.name + ".tmp")
            fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"access_token": self._token, "expires_at": self._token_expires.isoformat()}, f)
            os.replace(tmp, self._token_file)
        except OSError as e:
            log.warning("토큰 캐시 저장 실패: %s", e)

    def _token_valid(self) -> bool:
        return bool(self._token) and self._token_expires is not None and (
            self._token_expires - self._now() > TOKEN_REFRESH_MARGIN
        )

    def _invalidate_token(self) -> None:
        self._token, self._token_expires = "", None
        try:
            self._token_file.unlink()
        except OSError:
            pass

    def _access_token(self) -> str:
        if self._token_valid():
            return self._token
        if not self._token:
            self._load_token_file()
            if self._token_valid():
                return self._token
        return self._issue_token()

    def _issue_token(self) -> str:
        mono = self._monotonic()
        if self._last_issue_attempt is not None and mono - self._last_issue_attempt < TOKEN_ISSUE_COOLDOWN_SEC:
            raise BrokerError("접근 토큰을 방금 요청했습니다. 토큰 발급은 1분에 1회만 가능하므로 잠시 후 다시 시도합니다.")
        self._last_issue_attempt = mono
        body = json.dumps(
            {"grant_type": "client_credentials", "appkey": self.cfg.app_key, "appsecret": self.cfg.app_secret}
        ).encode("utf-8")
        self._throttle()
        try:
            status, _, raw = self._transport(
                "POST", self.base_url + "/oauth2/tokenP", {"content-type": "application/json; charset=utf-8"}, body, HTTP_TIMEOUT_SEC
            )
        except OSError as e:
            raise BrokerError(f"토큰 발급 요청 실패 (네트워크): {self._redact(str(e))}") from None
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            data = {}
        token = str(data.get("access_token") or "") if isinstance(data, dict) else ""
        if status != 200 or not token:
            code = str(data.get("error_code") or data.get("msg_cd") or status) if isinstance(data, dict) else str(status)
            msg = str(data.get("error_description") or data.get("msg1") or "응답을 해석할 수 없습니다") if isinstance(data, dict) else ""
            hint = " — 앱키/시크릿이 맞는지, 실전·모의 키를 바꿔 넣지 않았는지 확인하세요." if status in (401, 403) else ""
            raise BrokerError(self._redact(f"토큰 발급 실패 [{code}] {msg}{hint}"))
        expires: datetime | None = None
        stamp = str(data.get("access_token_token_expired") or "")
        try:
            expires = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
        except ValueError:
            seconds = _i(data.get("expires_in")) or 86400
            expires = self._now() + timedelta(seconds=seconds)
        self._token, self._token_expires = token, expires
        self._save_token_file()
        log.info("한국투자증권 접근 토큰 발급 완료 (만료 %s)", expires.strftime("%m-%d %H:%M"))
        return token

    # -- 요청 ----------------------------------------------------------------
    def _call(
        self,
        method: str,
        path: str,
        tr_id: str,
        *,
        params: Mapping[str, str] | None = None,
        body: Mapping[str, str] | None = None,
        tr_cont: str = "",
    ) -> tuple[dict[str, Any], str]:
        """API 호출. (응답 본문, 응답 헤더의 tr_cont) 를 반환.

        GET 은 일시적 오류(네트워크, 초당 호출 초과, 토큰 만료)에 한해 자동 재시도합니다.
        POST(주문)는 재시도하지 않습니다.
        """
        idempotent = method == "GET"
        attempts = GET_ATTEMPTS if idempotent else 1
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        last: Exception | None = None
        for attempt in range(attempts):
            token = self._access_token()
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {token}",
                "appkey": self.cfg.app_key,
                "appsecret": self.cfg.app_secret,
                "tr_id": tr_id,
                "custtype": "P",
                "tr_cont": tr_cont,
            }
            self._throttle()
            try:
                status, resp_headers, raw = self._transport(method, url, headers, payload, HTTP_TIMEOUT_SEC)
            except OSError as e:
                last = KisTransportError(f"네트워크 오류: {self._redact(str(e))}")
                if attempt + 1 < attempts:
                    self._sleep(0.5 * (attempt + 1))
                    continue
                raise last from None
            try:
                data = json.loads(raw.decode("utf-8", errors="replace"))
            except ValueError:
                data = None
            if not isinstance(data, dict):
                last = KisTransportError(f"서버 응답을 해석할 수 없습니다 (HTTP {status})")
                if attempt + 1 < attempts:
                    self._sleep(0.5 * (attempt + 1))
                    continue
                raise last
            code = str(data.get("msg_cd") or "")
            if str(data.get("rt_cd")) == "0" and 200 <= status < 300:
                cont = ""
                for k, v in resp_headers.items():
                    if str(k).lower() == "tr_cont":
                        cont = str(v).strip()
                return data, cont
            message = self._redact(str(data.get("msg1") or data.get("error_description") or "").strip())
            if code == "EGW00201" and attempt + 1 < attempts:        # 초당 호출 수 초과
                self._sleep(1.0 + attempt)
                continue
            if code in ("EGW00123", "EGW00121"):                    # 토큰 만료/무효 → 다음 호출부터 새 토큰
                self._invalidate_token()
                if attempt + 1 < attempts:
                    continue
            raise KisApiError(code, message or f"요청이 거부되었습니다 (HTTP {status})", status)
        raise last or KisTransportError("요청 실패")

    def _account_params(self) -> dict[str, str]:
        return {"CANO": self.cfg.account_no, "ACNT_PRDT_CD": self.cfg.account_product}

    # ------------------------------------------------------------------ #
    # 시세
    # ------------------------------------------------------------------ #
    def get_quote(self, symbol: str) -> Quote:
        data, _ = self._call(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            TR_PRICE,
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
        )
        o = data.get("output")
        if not isinstance(o, dict):
            raise BrokerError(f"{symbol}: 현재가 응답 형식이 올바르지 않습니다")
        price = _f(o.get("stck_prpr"))
        if price <= 0:
            raise BrokerError(f"{symbol}: 현재가를 받지 못했습니다 (종목코드를 확인하세요)")
        volume = _f(o.get("acml_vol"))
        traded = volume > 0
        prev_close = _f(o.get("stck_sdpr")) or (price - _f(o.get("prdy_vrss")))
        quote = Quote(
            symbol=symbol,
            price=price,
            # 오늘 체결이 한 건도 없으면 시가/고가/저가는 의미가 없으므로 0 으로 둡니다.
            open=_f(o.get("stck_oprc")) if traded else 0.0,
            high=_f(o.get("stck_hgpr")) if traded else 0.0,
            low=_f(o.get("stck_lwpr")) if traded else 0.0,
            prev_close=prev_close,
            volume=volume,
            upper_limit=_f(o.get("stck_mxpr")),
            lower_limit=_f(o.get("stck_llam")),
            halted=str(o.get("temp_stop_yn", "")).upper() == "Y" or str(o.get("iscd_stat_cls_code", "")) == "58",
            time=self._now(),
        )
        self._quotes[symbol] = (self._monotonic(), quote)
        return quote

    def _recent_quote(self, symbol: str) -> Quote:
        cached = self._quotes.get(symbol)
        if cached is not None and self._monotonic() - cached[0] <= QUOTE_CACHE_SEC:
            return cached[1]
        return self.get_quote(symbol)

    def get_daily_bars(self, symbol: str, start: date, end: date) -> list[Bar]:
        """수정주가 일봉. 한 번에 최대 100개씩, 최근 → 과거 방향으로 이어 받습니다."""
        if end < start:
            return []
        bars: dict[date, Bar] = {}
        cursor = end
        for _ in range(MAX_PAGES):
            data, _ = self._call(
                "GET",
                "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                TR_DAILY_CHART,
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": symbol,
                    "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
                    "FID_INPUT_DATE_2": cursor.strftime("%Y%m%d"),
                    "FID_PERIOD_DIV_CODE": "D",
                    "FID_ORG_ADJ_PRC": "0",        # 0 = 수정주가
                },
            )
            rows = data.get("output2")
            rows = [r for r in rows if isinstance(r, dict) and r.get("stck_bsop_date")] if isinstance(rows, list) else []
            oldest: date | None = None
            for r in rows:
                try:
                    d = datetime.strptime(str(r["stck_bsop_date"]), "%Y%m%d").date()
                except ValueError:
                    continue
                if oldest is None or d < oldest:
                    oldest = d
                o, h, low, c = _f(r.get("stck_oprc")), _f(r.get("stck_hgpr")), _f(r.get("stck_lwpr")), _f(r.get("stck_clpr"))
                if min(o, h, low, c) <= 0 or not (start <= d <= end):
                    continue            # 거래가 없던 날(값 0)과 범위 밖 행은 버림
                bars[d] = Bar(d, o, max(h, o, c), min(low, o, c), c, _f(r.get("acml_vol")))
            if oldest is None or oldest <= start or oldest > cursor:
                break               # 더 받을 것이 없거나(빈 응답), 시작일까지 다 받았거나, 진행이 없음
            cursor = oldest - timedelta(days=1)
            if cursor < start:
                break
        return [bars[d] for d in sorted(bars)]

    def is_trading_day(self, day: date) -> bool | None:
        """개장일 여부 (실전 서버의 휴장일 조회, 하루 1회만 호출). 모의투자 키만 있으면 None."""
        if self.mock:
            return None
        key = day.strftime("%Y%m%d")
        if not self._holidays:
            try:
                saved = json.loads(self._holiday_file.read_text(encoding="utf-8"))
                if saved.get("fetched") == self._now().date().isoformat() and isinstance(saved.get("days"), dict):
                    self._holidays = {str(k): bool(v) for k, v in saved["days"].items()}
                    self._holiday_checked = self._now().date()
            except (OSError, ValueError, AttributeError):
                pass
        if key in self._holidays:
            return self._holidays[key]
        today = self._now().date()
        if self._holiday_checked == today:
            return None             # 오늘 이미 조회함 (증권사 권고: 하루 1회)
        self._holiday_checked = today
        try:
            data, _ = self._call(
                "GET",
                "/uapi/domestic-stock/v1/quotations/chk-holiday",
                TR_HOLIDAY,
                params={"BASS_DT": key, "CTX_AREA_NK": "", "CTX_AREA_FK": ""},
            )
        except BrokerError as e:
            log.warning("휴장일 조회 실패: %s", e)
            return None
        rows = data.get("output")
        if isinstance(rows, dict):
            rows = [rows]
        days: dict[str, bool] = {}
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, dict) and r.get("bass_dt") and str(r.get("opnd_yn", "")).upper() in ("Y", "N"):
                days[str(r["bass_dt"])] = str(r["opnd_yn"]).upper() == "Y"
        self._holidays = days
        try:
            self.token_dir.mkdir(parents=True, exist_ok=True)
            self._holiday_file.write_text(json.dumps({"fetched": today.isoformat(), "days": days}), encoding="utf-8")
        except OSError:
            pass
        return days.get(key)

    # ------------------------------------------------------------------ #
    # 계좌
    # ------------------------------------------------------------------ #
    def _balance(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        holdings: list[dict[str, Any]] = []
        summary: dict[str, Any] = {}
        fk = nk = ""
        cont = ""
        for _ in range(MAX_PAGES):
            data, resp_cont = self._call(
                "GET",
                "/uapi/domestic-stock/v1/trading/inquire-balance",
                self._tr(TR_BALANCE),
                params={
                    **self._account_params(),
                    "AFHR_FLPR_YN": "N",
                    "OFL_YN": "",
                    "INQR_DVSN": "02",
                    "UNPR_DVSN": "01",
                    "FUND_STTL_ICLD_YN": "N",
                    "FNCG_AMT_AUTO_RDPT_YN": "N",
                    "PRCS_DVSN": "00",
                    "CTX_AREA_FK100": fk,
                    "CTX_AREA_NK100": nk,
                },
                tr_cont=cont,
            )
            rows = data.get("output1")
            if isinstance(rows, list):
                holdings.extend(r for r in rows if isinstance(r, dict))
            o2 = data.get("output2")
            if isinstance(o2, list) and o2 and isinstance(o2[0], dict):
                summary = o2[0]
            elif isinstance(o2, dict):
                summary = o2
            fk, nk = str(data.get("ctx_area_fk100") or "").strip(), str(data.get("ctx_area_nk100") or "").strip()
            if resp_cont not in ("M", "F") or not nk:
                break
            cont = "N"
        return holdings, summary

    def get_account(self) -> AccountSnapshot:
        holdings, summary = self._balance()
        positions: dict[str, BrokerPosition] = {}
        for r in holdings:
            qty = _i(r.get("hldg_qty"))
            sym = str(r.get("pdno") or "").strip()
            if qty <= 0 or not sym:
                continue            # 당일 전량 매도한 종목은 수량 0 으로 며칠 남아 있을 수 있음
            positions[sym] = BrokerPosition(
                symbol=sym,
                qty=qty,
                sellable_qty=_i(r.get("ord_psbl_qty")),
                avg_price=_f(r.get("pchs_avg_pric")),
                name=str(r.get("prdt_name") or "").strip(),
            )
        return AccountSnapshot(
            cash=_f(summary.get("prvs_rcdl_excc_amt")),       # D+2 예수금 (오늘 매매까지 반영된 현금)
            total_equity=_f(summary.get("tot_evlu_amt")),
            positions=positions,
        )

    def sellable_qty(self, symbol: str) -> int | None:
        holdings, _ = self._balance()
        for r in holdings:
            if str(r.get("pdno") or "").strip() == symbol:
                return _i(r.get("ord_psbl_qty"))
        return 0

    def max_buy_qty(self, symbol: str, price: float) -> int | None:
        """미수(외상) 없이 지금 살 수 있는 최대 수량."""
        order_price = self._order_price(symbol, Side.BUY, price) if self.cfg.order_style == "limit" else int(price)
        data, _ = self._call(
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-psbl-order",
            self._tr(TR_PSBL_ORDER),
            params={
                **self._account_params(),
                "PDNO": symbol,
                "ORD_UNPR": str(max(order_price, 1)),
                "ORD_DVSN": "01",
                "CMA_EVLU_AMT_ICLD_YN": "N",
                "OVRS_ICLD_YN": "N",
            },
        )
        o = data.get("output")
        if not isinstance(o, dict):
            raise BrokerError(f"{symbol}: 매수가능조회 응답 형식이 올바르지 않습니다")
        amount = _f(o.get("nrcvb_buy_amt"))
        qty = _i(o.get("nrcvb_buy_qty"))
        if self.cfg.order_style == "limit":
            # 지정가 주문은 주문가격만큼만 증거금이 잡힘
            return max(0, int(amount // order_price)) if order_price > 0 else 0
        # 시장가 주문은 상한가 기준으로 증거금이 잡히므로 그만큼만 살 수 있음
        upper = 0.0
        try:
            upper = self._recent_quote(symbol).upper_limit
        except BrokerError:
            pass
        if upper <= 0:
            upper = price * 1.3
        return max(0, min(qty, int(amount // upper)))

    # ------------------------------------------------------------------ #
    # 주문
    # ------------------------------------------------------------------ #
    def _order_price(self, symbol: str, side: Side, ref_price: float) -> int:
        """지정가 주문 가격: 기준가에서 불리한 쪽으로 n틱 (상·하한가 범위 안)."""
        n = self.cfg.limit_ticks
        price = shift_ticks(ref_price, n if side == Side.BUY else -n)
        try:
            q = self._recent_quote(symbol)
        except BrokerError:
            return price
        if side == Side.BUY and q.upper_limit > 0:
            price = min(price, int(q.upper_limit))
        if side == Side.SELL and q.lower_limit > 0:
            price = max(price, int(q.lower_limit))
        return price

    def submit_order(self, req: OrderRequest) -> OrderResult:
        try:
            return self._submit(req)
        except Exception as e:  # noqa: BLE001 - 어떤 오류든 '결과 불확실'로 보고 (코어가 잠그고 알림)
            log.exception("주문 처리 중 예외 (%s)", req.symbol)
            return OrderResult(req, OrderStatus.UNKNOWN, message=self._redact(f"주문 처리 중 오류: {e}"), time=self._now())

    def _submit(self, req: OrderRequest) -> OrderResult:
        if req.qty <= 0:
            return OrderResult(req, OrderStatus.REJECTED, message="주문 수량이 0 이하입니다", time=self._now())
        if self.cfg.order_style == "limit":
            dvsn, unpr = "00", str(self._order_price(req.symbol, req.side, req.ref_price))
        else:
            dvsn, unpr = "01", "0"
        body = {
            **self._account_params(),
            "PDNO": req.symbol,
            "ORD_DVSN": dvsn,
            "ORD_QTY": str(int(req.qty)),
            "ORD_UNPR": unpr,
            "EXCG_ID_DVSN_CD": "KRX",
            "SLL_TYPE": "01" if req.side == Side.SELL else "",
            "CNDT_PRIC": "",
        }
        tr = self._tr(TR_BUY if req.side == Side.BUY else TR_SELL)
        sent_at = self._now()
        try:
            data, _ = self._call("POST", "/uapi/domestic-stock/v1/trading/order-cash", tr, body=body)
        except KisApiError as e:
            # 서버가 명시적으로 거부 → 주문은 접수되지 않았음
            return OrderResult(req, OrderStatus.REJECTED, message=str(e), time=self._now())
        except KisTransportError as e:
            # 접수 여부 불명 → 주문 내역에서 찾아본다
            log.warning("%s 주문 전송 결과 불명, 주문 내역을 확인합니다: %s", req.symbol, e)
            found = self._recover(req, sent_at, wait_sec=6.0)
            if found is not None:
                return found
            return OrderResult(
                req, OrderStatus.UNKNOWN, message=f"주문 전송 결과를 확인하지 못했습니다 ({e})", time=self._now()
            )
        out = _upper_keys(data.get("output"))
        odno = str(out.get("ODNO") or "").strip()
        org = str(out.get("KRX_FWDG_ORD_ORGNO") or "").strip()
        if not odno:
            return OrderResult(req, OrderStatus.UNKNOWN, message="주문은 접수됐지만 주문번호를 받지 못했습니다", time=self._now())
        return self._finalize(req, odno, org, self.cfg.fill_timeout_sec)

    def _order_rows(self, symbol: str, side: Side) -> list[dict[str, Any]]:
        """오늘의 해당 종목·방향 주문 내역 전체."""
        today = self._now().strftime("%Y%m%d")
        rows: list[dict[str, Any]] = []
        fk = nk = ""
        cont = ""
        for _ in range(MAX_PAGES):
            data, resp_cont = self._call(
                "GET",
                "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
                self._tr(TR_DAILY_CCLD),
                params={
                    **self._account_params(),
                    "INQR_STRT_DT": today,
                    "INQR_END_DT": today,
                    "SLL_BUY_DVSN_CD": "01" if side == Side.SELL else "02",
                    "PDNO": symbol,
                    "CCLD_DVSN": "00",
                    "INQR_DVSN": "00",
                    "INQR_DVSN_3": "00",
                    "ORD_GNO_BRNO": "",
                    "ODNO": "",
                    "INQR_DVSN_1": "",
                    "CTX_AREA_FK100": fk,
                    "CTX_AREA_NK100": nk,
                    "EXCG_ID_DVSN_CD": "KRX",
                },
                tr_cont=cont,
            )
            page = data.get("output1")
            if isinstance(page, list):
                rows.extend(r for r in page if isinstance(r, dict))
            fk, nk = str(data.get("ctx_area_fk100") or "").strip(), str(data.get("ctx_area_nk100") or "").strip()
            if resp_cont not in ("M", "F") or not nk:
                break
            cont = "N"
        return rows

    @staticmethod
    def _state_of(rows: list[dict[str, Any]], odno: str) -> _OrderState:
        st = _OrderState()
        for r in rows:
            if _same_order_no(r.get("odno"), odno):
                st.found = True
                st.ord_qty = _i(r.get("ord_qty"))
                st.filled = _i(r.get("tot_ccld_qty"))
                st.remaining = _i(r.get("rmn_qty"))
                st.rejected = _i(r.get("rjct_qty"))
                st.cancelled = st.cancelled or str(r.get("cncl_yn", "")).upper() == "Y"
                st.cancel_qty = _i(r.get("cncl_cfrm_qty") or r.get("cnc_cfrm_qty"))
                st.avg_price = _f(r.get("avg_prvs"))
                if st.avg_price <= 0 and st.filled > 0:
                    st.avg_price = _f(r.get("tot_ccld_amt")) / st.filled
                st.org_no = str(r.get("ord_orgno") or r.get("ord_gno_brno") or "").strip()
            elif _same_order_no(r.get("orgn_odno"), odno):
                st.cancelled = True     # 이 주문을 대상으로 한 취소 주문이 별도 행으로 보이는 경우
        return st

    def _result(self, req: OrderRequest, odno: str, st: _OrderState, note: str = "") -> OrderResult:
        filled = max(0, min(st.filled, req.qty))
        if filled >= req.qty:
            status = OrderStatus.FILLED
        elif filled > 0:
            status = OrderStatus.PARTIAL
        else:
            status = OrderStatus.REJECTED
        if not note and status != OrderStatus.FILLED:
            note = "주문이 거부되었습니다" if st.rejected > 0 else "체결되지 않은 수량은 취소했습니다"
        return OrderResult(req, status, filled, st.avg_price if filled > 0 else 0.0, odno, note, self._now())

    def _finalize(self, req: OrderRequest, odno: str, org: str, timeout_sec: float) -> OrderResult:
        """주문이 최종 상태가 될 때까지 추적. 시간 안에 다 체결되지 않으면 잔량을 취소합니다."""
        deadline = self._monotonic() + max(0.0, timeout_sec)
        st = _OrderState()
        while True:
            try:
                st = self._state_of(self._order_rows(req.symbol, req.side), odno)
            except BrokerError as e:
                log.warning("%s 체결 조회 실패: %s", req.symbol, e)
            if st.final():
                return self._result(req, odno, st)
            if self._monotonic() >= deadline:
                break
            self._sleep(FILL_POLL_SEC)

        # 시간 초과 → 남은 수량 취소
        cancel_error = ""
        try:
            self._call(
                "POST",
                "/uapi/domestic-stock/v1/trading/order-rvsecncl",
                self._tr(TR_CANCEL),
                body={
                    **self._account_params(),
                    "KRX_FWDG_ORD_ORGNO": org or st.org_no,
                    "ORGN_ODNO": odno,
                    "ORD_DVSN": "00",
                    "RVSE_CNCL_DVSN_CD": "02",
                    "ORD_QTY": "0",
                    "ORD_UNPR": "0",
                    "QTY_ALL_ORD_YN": "Y",
                    "EXCG_ID_DVSN_CD": "KRX",
                },
            )
        except BrokerError as e:
            cancel_error = str(e)       # 이미 전량 체결되어 취소할 것이 없을 때도 여기로 옴 → 아래에서 다시 확인

        settle_deadline = self._monotonic() + CANCEL_SETTLE_SEC
        while True:
            try:
                st = self._state_of(self._order_rows(req.symbol, req.side), odno)
            except BrokerError as e:
                log.warning("%s 체결 조회 실패: %s", req.symbol, e)
            if st.final(after_cancel=not cancel_error):
                return self._result(req, odno, st)
            if self._monotonic() >= settle_deadline:
                break
            self._sleep(FILL_POLL_SEC)

        detail = f" (취소 요청 오류: {cancel_error})" if cancel_error else ""
        return OrderResult(
            req,
            OrderStatus.UNKNOWN,
            filled_qty=0,
            broker_order_id=odno,
            message=f"주문번호 {odno} 의 최종 상태를 확인하지 못했습니다{detail}. 미체결 주문이 남아 있을 수 있습니다.",
            time=self._now(),
        )

    def _recover(self, req: OrderRequest, since: datetime, wait_sec: float = 0.0) -> OrderResult | None:
        """since 이후에 접수된, req 와 같은 종목·방향·수량의 주문을 찾아 최종 결과를 반환. 없으면 None."""
        deadline = self._monotonic() + wait_sec
        threshold = since - timedelta(seconds=5)
        while True:
            rows = self._order_rows(req.symbol, req.side)
            best: tuple[datetime, str, str] | None = None
            for r in rows:
                if _i(r.get("ord_qty")) != req.qty or str(r.get("orgn_odno") or "").strip().lstrip("0"):
                    continue
                try:
                    at = datetime.strptime(f"{r.get('ord_dt')}{str(r.get('ord_tmd')).zfill(6)}", "%Y%m%d%H%M%S").replace(tzinfo=KST)
                except ValueError:
                    continue
                if at >= threshold and (best is None or at > best[0]):
                    best = (at, str(r.get("odno") or "").strip(), str(r.get("ord_orgno") or r.get("ord_gno_brno") or "").strip())
            if best is not None and best[1]:
                return self._finalize(req, best[1], best[2], 0.0)
            if self._monotonic() >= deadline:
                return None
            self._sleep(FILL_POLL_SEC * 2)

    def recover_order(self, req: OrderRequest, since: datetime) -> OrderResult | None:
        return self._recover(req, since, wait_sec=0.0)

    # ------------------------------------------------------------------ #
    # 연결 점검 (doctor 명령용)
    # ------------------------------------------------------------------ #
    def check_connection(self, symbol: str = "005930") -> list[tuple[str, bool, str]]:
        """(항목, 성공 여부, 설명) 목록. 예외를 던지지 않습니다."""
        out: list[tuple[str, bool, str]] = []
        try:
            self._access_token()
            out.append(("접근 토큰", True, f"발급/확인 완료 (만료 {self._token_expires:%m-%d %H:%M})"))
        except BrokerError as e:
            out.append(("접근 토큰", False, str(e)))
            return out
        try:
            q = self.get_quote(symbol)
            out.append(("시세 조회", True, f"{symbol} 현재가 {q.price:,.0f}원"))
        except BrokerError as e:
            out.append(("시세 조회", False, str(e)))
        try:
            acct = self.get_account()
            out.append(
                ("계좌 조회", True, f"총평가 {acct.total_equity:,.0f}원, 예수금(D+2) {acct.cash:,.0f}원, 보유 {len(acct.positions)}종목")
            )
        except BrokerError as e:
            hint = " — 계좌번호(KIS_ACCOUNT / KIS_MOCK_ACCOUNT)와 앱키가 같은 계좌의 것인지 확인하세요." if "OPSQ2000" in str(e) else ""
            out.append(("계좌 조회", False, f"{e}{hint}"))
        return out

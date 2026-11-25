"""KIS 클라이언트 테스트 — 가짜 KIS 서버(전송 계층 대체)로 요청/응답 흐름을 검증합니다."""

from __future__ import annotations

import json
import stat
import urllib.parse
from datetime import date, datetime, timedelta

import pytest

from autotrader.brokers.base import BrokerError
from autotrader.brokers.kis import MOCK_BASE, REAL_BASE, KisClient
from autotrader.config import KisConfig
from autotrader.models import KST, OrderRequest, OrderStatus, Side

NOW = datetime(2026, 11, 25, 10, 0, 0, tzinfo=KST)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.slept: list[float] = []

    def now(self) -> datetime:
        return NOW + timedelta(seconds=self.t - 1000.0)

    def monotonic(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += max(s, 0.0)


class FakeKis:
    """KIS 서버 흉내. transport(method, url, headers, body, timeout) 로 호출됩니다."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.calls: list[dict] = []
        self.tokens = 0
        self.token_response: tuple[int, dict] | None = None
        self.scripted: dict[str, list] = {}        # 경로 끝부분 → [응답 또는 예외, ...] (앞에서부터 1회씩 소비)
        self.quote = {
            "stck_prpr": "71200", "stck_oprc": "70800", "stck_hgpr": "71500", "stck_lwpr": "70500",
            "stck_sdpr": "70000", "prdy_vrss": "1200", "acml_vol": "1234567", "stck_mxpr": "91000",
            "stck_llam": "49000", "temp_stop_yn": "N", "iscd_stat_cls_code": "55",
        }
        self.bars: list[dict] = []
        self.holdings: list[dict] = []
        self.summary = {"dnca_tot_amt": "5000000", "prvs_rcdl_excc_amt": "4800000", "tot_evlu_amt": "9000000"}
        self.psbl = {"nrcvb_buy_amt": "1000000", "nrcvb_buy_qty": "10", "ord_psbl_cash": "1000000", "max_buy_qty": "25"}
        self.orders: list[dict] = []
        self.next_odno = 2101
        self.fill = "full"                 # full | none | partial | reject
        self.visible_after = 0             # 주문이 이 횟수만큼 조회된 뒤에야 내역에 보임
        self.cancel_ok = True
        self.cancel_as_row = False         # 취소가 원주문 행의 플래그가 아니라 별도 행으로 보이는 방식
        self.holiday_rows = [{"bass_dt": "20261125", "opnd_yn": "Y"}, {"bass_dt": "20261126", "opnd_yn": "N"}]

    # -- 도우미 ---------------------------------------------------------------
    def paths(self, suffix: str) -> list[dict]:
        return [c for c in self.calls if c["path"].endswith(suffix)]

    @staticmethod
    def ok(**payload) -> tuple[int, dict, bytes]:
        headers = payload.pop("_headers", {})
        return 200, headers, json.dumps({"rt_cd": "0", "msg_cd": "OK", "msg1": "정상", **payload}).encode()

    @staticmethod
    def err(code: str, msg: str, status: int = 500) -> tuple[int, dict, bytes]:
        return status, {}, json.dumps({"rt_cd": "1", "msg_cd": code, "msg1": msg}).encode()

    # -- 전송 계층 -------------------------------------------------------------
    def __call__(self, method, url, headers, body, timeout):
        u = urllib.parse.urlsplit(url)
        params = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
        payload = json.loads(body) if body else None
        call = {"method": method, "base": f"{u.scheme}://{u.netloc}", "path": u.path, "params": params,
                "body": payload, "headers": dict(headers)}
        self.calls.append(call)
        for suffix, queue in self.scripted.items():
            if u.path.endswith(suffix) and queue:
                item = queue.pop(0)
                if isinstance(item, Exception):
                    raise item
                if item is not None:
                    return item
        if u.path == "/oauth2/tokenP":
            if self.token_response is not None:
                status, data = self.token_response
                return status, {}, json.dumps(data).encode()
            self.tokens += 1
            exp = (self.clock.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            return 200, {}, json.dumps({"access_token": f"TOKEN{self.tokens}", "token_type": "Bearer",
                                         "expires_in": 86400, "access_token_token_expired": exp}).encode()
        if u.path.endswith("/inquire-price"):
            return self.ok(output=dict(self.quote))
        if u.path.endswith("/inquire-daily-itemchartprice"):
            lo, hi = params["FID_INPUT_DATE_1"], params["FID_INPUT_DATE_2"]
            rows = sorted((b for b in self.bars if b and lo <= b["stck_bsop_date"] <= hi),
                          key=lambda b: b["stck_bsop_date"], reverse=True)[:100]
            if rows and any(not b for b in self.bars):
                rows = rows + [{}]                  # 빈 행이 섞여 오는 경우
            return self.ok(output1={}, output2=rows)
        if u.path.endswith("/chk-holiday"):
            return self.ok(output=self.holiday_rows)
        if u.path.endswith("/inquire-balance"):
            start = int(params.get("CTX_AREA_NK100") or 0)
            page = self.holdings[start:start + 2]
            more = start + 2 < len(self.holdings)
            return self.ok(output1=page, output2=[self.summary], ctx_area_fk100="FK", ctx_area_nk100=str(start + 2) if more else "",
                           _headers={"tr_cont": "M" if more else "D"})
        if u.path.endswith("/inquire-psbl-order"):
            return self.ok(output=dict(self.psbl))
        if u.path.endswith("/order-cash"):
            return self._order(call)
        if u.path.endswith("/order-rvsecncl"):
            return self._cancel(payload)
        if u.path.endswith("/inquire-daily-ccld"):
            side = params["SLL_BUY_DVSN_CD"]
            rows = []
            for o in self.orders:
                if o["pdno"] != params["PDNO"] or o["sll_buy_dvsn_cd"] != side:
                    continue
                if o["_hidden"] > 0:
                    o["_hidden"] -= 1
                    continue
                rows.append({k: v for k, v in o.items() if not k.startswith("_")})
            return self.ok(output1=rows, output2={}, _headers={"tr_cont": "D"})
        return 404, {}, b"not found"

    def _order(self, call):
        b = call["body"]
        qty = int(b["ORD_QTY"])
        side = "01" if call["headers"]["tr_id"].endswith("0011U") else "02"
        price = int(b["ORD_UNPR"]) or int(self.quote["stck_prpr"])
        filled = {"full": qty, "none": 0, "partial": qty // 2, "reject": 0}[self.fill]
        odno = f"{self.next_odno:010d}"
        self.next_odno += 1
        now = self.clock.now()
        self.orders.append({
            "ord_dt": now.strftime("%Y%m%d"), "ord_tmd": now.strftime("%H%M%S"), "odno": odno, "orgn_odno": "",
            "ord_orgno": "06010", "pdno": b["PDNO"], "sll_buy_dvsn_cd": side, "ord_qty": str(qty),
            "tot_ccld_qty": str(filled), "rmn_qty": "0" if self.fill == "reject" else str(qty - filled),
            "rjct_qty": str(qty) if self.fill == "reject" else "0", "cncl_yn": "N", "cnc_cfrm_qty": "0",
            "avg_prvs": str(price) if filled else "0", "tot_ccld_amt": str(price * filled),
            "_hidden": self.visible_after,
        })
        return self.ok(output={"KRX_FWDG_ORD_ORGNO": "06010", "ODNO": odno, "ORD_TMD": now.strftime("%H%M%S")})

    def _cancel(self, b):
        if not self.cancel_ok:
            return self.err("APBK0344", "주문 취소 가능 수량이 없습니다", 200)
        for o in self.orders:
            if int(o["odno"]) == int(b["ORGN_ODNO"]):
                rest = int(o["rmn_qty"])
                o["rmn_qty"] = "0"
                if self.cancel_as_row:
                    self.orders.append({**o, "odno": f"{self.next_odno:010d}", "orgn_odno": o["odno"],
                                        "tot_ccld_qty": "0", "ord_qty": str(rest)})
                    self.next_odno += 1
                else:
                    o["cncl_yn"] = "Y"
                    o["cnc_cfrm_qty"] = str(rest)
        return self.ok(output={"krx_fwdg_ord_orgno": "06010", "odno": "0000009999", "ord_tmd": "100001"})


def make(tmp_path, *, mock=True, style="market", **cfg_kw):
    clock = Clock()
    server = FakeKis(clock)
    cfg = KisConfig(app_key="APPKEY-SECRET-1", app_secret="APPSECRET-2", account_no="50012345", account_product="01",
                    mock=mock, order_style=style, limit_ticks=3, fill_timeout_sec=5.0, **cfg_kw)
    client = KisClient(cfg, token_dir=tmp_path, transport=server, now=clock.now, sleep=clock.sleep, monotonic=clock.monotonic)
    return client, server, clock


def buy(qty=10, ref=71_200.0, symbol="005930") -> OrderRequest:
    return OrderRequest(symbol, Side.BUY, qty, ref, "test", "c1")


def sell(qty=10, ref=71_200.0, symbol="005930") -> OrderRequest:
    return OrderRequest(symbol, Side.SELL, qty, ref, "test", "c2")


# --------------------------------------------------------------------------- #
# 토큰 / 공통 헤더
# --------------------------------------------------------------------------- #
def test_missing_credentials_are_reported(tmp_path):
    with pytest.raises(BrokerError, match="KIS_MOCK_APP_KEY"):
        KisClient(KisConfig(mock=True), token_dir=tmp_path)
    with pytest.raises(BrokerError, match="KIS_APP_KEY"):
        KisClient(KisConfig(mock=False), token_dir=tmp_path)


def test_token_is_issued_once_cached_on_disk_and_reused(tmp_path):
    client, server, clock = make(tmp_path)
    client.get_quote("005930")
    client.get_quote("005930")
    assert server.tokens == 1
    tok = server.paths("/oauth2/tokenP")[0]
    assert tok["method"] == "POST" and tok["base"] == MOCK_BASE
    assert tok["body"] == {"grant_type": "client_credentials", "appkey": "APPKEY-SECRET-1", "appsecret": "APPSECRET-2"}
    files = list(tmp_path.glob("kis-token-mock-*.json"))
    assert len(files) == 1 and "APPKEY" not in files[0].name
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600

    # 새 프로세스(새 객체)는 파일의 토큰을 재사용
    clock2 = Clock()
    server2 = FakeKis(clock2)
    client2 = KisClient(client.cfg, token_dir=tmp_path, transport=server2, now=clock2.now, sleep=clock2.sleep,
                        monotonic=clock2.monotonic)
    client2.get_quote("005930")
    assert server2.tokens == 0
    assert server2.paths("/inquire-price")[0]["headers"]["authorization"] == "Bearer TOKEN1"


def test_token_is_refreshed_before_expiry_and_real_mock_caches_are_separate(tmp_path):
    client, server, clock = make(tmp_path)
    client.get_quote("005930")
    clock.t += 23 * 3600 + 55 * 60          # 만료 5분 전 → 여유(10분) 안쪽이므로 새로 발급
    client.get_quote("005930")
    assert server.tokens == 2
    real, rserver, _ = make(tmp_path, mock=False)
    real.get_quote("005930")
    assert rserver.tokens == 1              # 모의 토큰 파일을 실전에서 쓰지 않음
    assert rserver.paths("/oauth2/tokenP")[0]["base"] == REAL_BASE


def test_token_failure_is_explained_without_leaking_secrets_and_rate_limited(tmp_path):
    client, server, clock = make(tmp_path)
    server.token_response = (403, {"error_code": "EGW00103", "error_description": "유효하지 않은 AppKey APPKEY-SECRET-1"})
    with pytest.raises(BrokerError) as ei:
        client.get_quote("005930")
    msg = str(ei.value)
    assert "EGW00103" in msg and "APPKEY-SECRET-1" not in msg and "확인하세요" in msg
    with pytest.raises(BrokerError, match="1분에 1회"):
        client.get_quote("005930")          # 바로 다시 발급을 시도하지 않음
    assert len(server.paths("/oauth2/tokenP")) == 1
    clock.t += 70
    server.token_response = None
    assert client.get_quote("005930").price == 71_200


def test_common_headers_and_environment_specific_tr_ids(tmp_path):
    client, server, _ = make(tmp_path, mock=True)
    client.get_quote("005930")
    client.get_account()
    h = server.paths("/inquire-price")[0]["headers"]
    assert h["tr_id"] == "FHKST01010100" and h["custtype"] == "P" and h["appkey"] == "APPKEY-SECRET-1"
    assert h["appsecret"] == "APPSECRET-2" and h["authorization"].startswith("Bearer ") and h["tr_cont"] == ""
    assert server.paths("/inquire-balance")[0]["headers"]["tr_id"] == "VTTC8434R"
    real, rserver, _ = make(tmp_path / "r", mock=False)
    real.get_account()
    real.submit_order(buy())
    real.submit_order(sell())
    assert rserver.paths("/inquire-balance")[0]["headers"]["tr_id"] == "TTTC8434R"
    assert [c["headers"]["tr_id"] for c in rserver.paths("/order-cash")] == ["TTTC0012U", "TTTC0011U"]
    assert rserver.paths("/inquire-daily-ccld")[0]["headers"]["tr_id"] == "TTTC0081R"
    assert all(c["base"] == REAL_BASE for c in rserver.calls)


def test_calls_are_throttled(tmp_path):
    client, server, clock = make(tmp_path)
    for _ in range(5):
        client.get_quote("005930")
    assert sum(clock.slept) >= 4 * (1 / 1.8) - 1e-6     # 모의투자 기본 속도 제한
    fast, _, fclock = make(tmp_path / "f", mock=False, max_calls_per_sec=100.0)
    for _ in range(5):
        fast.get_quote("005930")
    assert sum(fclock.slept) < 0.1


# --------------------------------------------------------------------------- #
# 시세
# --------------------------------------------------------------------------- #
def test_quote_parsing_and_no_trade_and_halt(tmp_path):
    client, server, _ = make(tmp_path)
    q = client.get_quote("005930")
    assert (q.price, q.open, q.high, q.low, q.prev_close) == (71_200, 70_800, 71_500, 70_500, 70_000)
    assert q.volume == 1_234_567 and q.upper_limit == 91_000 and q.lower_limit == 49_000 and not q.halted
    assert server.paths("/inquire-price")[0]["params"] == {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"}
    server.quote.update(acml_vol="0", stck_oprc="0", stck_hgpr="0", stck_lwpr="0")
    q = client.get_quote("005930")
    assert q.price == 71_200 and q.open == 0 and q.volume == 0      # 장 시작 전: 현재가는 있지만 시가 없음
    server.quote.update(acml_vol="5", stck_oprc="70800", temp_stop_yn="Y")
    assert client.get_quote("005930").halted
    server.quote.update(stck_prpr="0")
    with pytest.raises(BrokerError, match="현재가"):
        client.get_quote("005930")


def weekday_bars(n: int, end: date) -> list[dict]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            p = 50_000 + len(out) * 10
            out.append({"stck_bsop_date": d.strftime("%Y%m%d"), "stck_oprc": str(p), "stck_hgpr": str(p + 500),
                        "stck_lwpr": str(p - 500), "stck_clpr": str(p + 100), "acml_vol": "1000"})
        d -= timedelta(days=1)
    return out


def test_daily_bars_are_paged_backwards_sorted_and_adjusted(tmp_path):
    client, server, _ = make(tmp_path)
    server.bars = weekday_bars(250, date(2026, 11, 24))
    server.bars.append({"stck_bsop_date": "20260105", "stck_oprc": "0", "stck_hgpr": "0", "stck_lwpr": "0",
                        "stck_clpr": "50000", "acml_vol": "0"})          # 거래 없던 날(값 0)은 버림
    server.bars.append({})                                              # 빈 행도 섞여 올 수 있음
    bars = client.get_daily_bars("005930", date(2025, 1, 1), date(2026, 11, 24))
    assert len(bars) == 250
    assert [b.date for b in bars] == sorted(b.date for b in bars) and bars[-1].date == date(2026, 11, 24)
    assert all(b.low <= min(b.open, b.close) and b.high >= max(b.open, b.close) for b in bars)
    calls = server.paths("/inquire-daily-itemchartprice")
    assert len(calls) >= 3
    assert all(c["params"]["FID_ORG_ADJ_PRC"] == "0" and c["params"]["FID_PERIOD_DIV_CODE"] == "D" for c in calls)
    assert calls[0]["params"]["FID_INPUT_DATE_2"] == "20261124" and calls[1]["params"]["FID_INPUT_DATE_2"] < "20261124"
    assert client.get_daily_bars("005930", date(2026, 11, 20), date(2026, 11, 24)) == bars[-3:]
    assert client.get_daily_bars("005930", date(2026, 11, 24), date(2026, 11, 20)) == []


def test_holiday_check_real_only_once_per_day_and_cached(tmp_path):
    mock_client, mserver, _ = make(tmp_path / "m")
    assert mock_client.is_trading_day(date(2026, 11, 25)) is None and mserver.calls == []
    client, server, _ = make(tmp_path, mock=False)
    assert client.is_trading_day(date(2026, 11, 25)) is True
    assert client.is_trading_day(date(2026, 11, 26)) is False
    assert client.is_trading_day(date(2026, 12, 1)) is None            # 응답에 없는 날짜 → 모름 (재호출 안 함)
    assert len(server.paths("/chk-holiday")) == 1
    assert server.paths("/chk-holiday")[0]["headers"]["tr_id"] == "CTCA0903R"
    again, server2, _ = make(tmp_path, mock=False)                      # 재시작해도 같은 날에는 파일 캐시 사용
    assert again.is_trading_day(date(2026, 11, 26)) is False and server2.paths("/chk-holiday") == []
    broken, bserver, _ = make(tmp_path / "b", mock=False)
    bserver.scripted["/chk-holiday"] = [FakeKis.err("EGW00002", "서버 오류")] * 3
    assert broken.is_trading_day(date(2026, 11, 25)) is None            # 실패해도 예외 없이 '모름'


# --------------------------------------------------------------------------- #
# 계좌
# --------------------------------------------------------------------------- #
def holding(sym, qty, sellable=None, avg="70000", name="종목"):
    return {"pdno": sym, "prdt_name": name, "hldg_qty": str(qty), "ord_psbl_qty": str(qty if sellable is None else sellable),
            "pchs_avg_pric": avg}


def test_account_pagination_zero_holdings_and_sellable(tmp_path):
    client, server, _ = make(tmp_path)
    server.holdings = [holding("005930", 10, 7, "70123.45", "삼성전자"), holding("000660", 0), holding("035420", 3),
                       holding("069500", 5), holding("0152E0", 1)]
    acct = client.get_account()
    assert set(acct.positions) == {"005930", "035420", "069500", "0152E0"}      # 수량 0 은 제외
    p = acct.positions["005930"]
    assert (p.qty, p.sellable_qty, p.avg_price, p.name) == (10, 7, 70123.45, "삼성전자")
    assert acct.cash == 4_800_000 and acct.total_equity == 9_000_000
    pages = server.paths("/inquire-balance")
    assert len(pages) == 3 and pages[0]["headers"]["tr_cont"] == "" and pages[1]["headers"]["tr_cont"] == "N"
    assert pages[1]["params"]["CTX_AREA_NK100"] == "2" and pages[0]["params"]["INQR_DVSN"] == "02"
    assert client.sellable_qty("005930") == 7 and client.sellable_qty("999999") == 0


def test_max_buy_qty_market_uses_upper_limit_and_limit_uses_order_price(tmp_path):
    client, server, _ = make(tmp_path)
    assert client.max_buy_qty("005930", 71_200) == 10                 # min(10, 1,000,000 // 91,000 = 10)
    server.psbl.update(nrcvb_buy_qty="50")
    assert client.max_buy_qty("005930", 71_200) == 10                 # 상한가 기준으로 제한
    q = server.paths("/inquire-psbl-order")[0]
    assert q["headers"]["tr_id"] == "VTTC8908R"
    assert q["params"]["ORD_DVSN"] == "01" and q["params"]["ORD_UNPR"] == "71200" and q["params"]["CMA_EVLU_AMT_ICLD_YN"] == "N"
    lim, lserver, _ = make(tmp_path / "l", style="limit")
    assert lim.max_buy_qty("005930", 71_200) == 1_000_000 // 71_500   # 71,200 + 3틱(100원)
    assert lserver.paths("/inquire-psbl-order")[0]["params"]["ORD_UNPR"] == "71500"


# --------------------------------------------------------------------------- #
# 주문
# --------------------------------------------------------------------------- #
def test_market_buy_fills_and_request_body_is_exact(tmp_path):
    client, server, _ = make(tmp_path)
    res = client.submit_order(buy(10))
    assert res.status == OrderStatus.FILLED and res.filled_qty == 10 and res.avg_price == 71_200
    assert res.broker_order_id == "0000002101"
    (order,) = server.paths("/order-cash")
    assert order["method"] == "POST" and order["headers"]["tr_id"] == "VTTC0012U"
    assert order["body"] == {"CANO": "50012345", "ACNT_PRDT_CD": "01", "PDNO": "005930", "ORD_DVSN": "01",
                             "ORD_QTY": "10", "ORD_UNPR": "0", "EXCG_ID_DVSN_CD": "KRX", "SLL_TYPE": "", "CNDT_PRIC": ""}
    ccld = server.paths("/inquire-daily-ccld")[0]
    assert ccld["headers"]["tr_id"] == "VTTC0081R" and ccld["params"]["SLL_BUY_DVSN_CD"] == "02"
    assert ccld["params"]["INQR_STRT_DT"] == ccld["params"]["INQR_END_DT"] == "20261125"
    assert server.paths("/order-rvsecncl") == []


def test_limit_style_prices_and_sell_fields(tmp_path):
    client, server, _ = make(tmp_path, style="limit")
    assert client.submit_order(buy(4, ref=71_200)).avg_price == 71_500
    res = client.submit_order(sell(4, ref=71_200))
    assert res.status == OrderStatus.FILLED and res.avg_price == 70_900
    b, s = server.paths("/order-cash")
    assert (b["body"]["ORD_DVSN"], b["body"]["ORD_UNPR"]) == ("00", "71500")
    assert (s["body"]["ORD_DVSN"], s["body"]["ORD_UNPR"], s["body"]["SLL_TYPE"]) == ("00", "70900", "01")
    assert s["headers"]["tr_id"] == "VTTC0011U"
    assert server.paths("/inquire-daily-ccld")[-1]["params"]["SLL_BUY_DVSN_CD"] == "01"
    server.quote.update(stck_mxpr="71300", stck_llam="71100")           # 상·하한가를 넘지 않게
    client._quotes.clear()
    client.submit_order(buy(1, ref=71_200))
    client.submit_order(sell(1, ref=71_200))
    assert [c["body"]["ORD_UNPR"] for c in server.paths("/order-cash")[-2:]] == ["71300", "71100"]


@pytest.mark.parametrize("as_row", [False, True])
def test_partial_fill_is_cancelled_after_timeout(tmp_path, as_row):
    client, server, clock = make(tmp_path)
    server.fill = "partial"
    server.cancel_as_row = as_row
    res = client.submit_order(buy(10))
    assert res.status == OrderStatus.PARTIAL and res.filled_qty == 5 and res.avg_price == 71_200
    (cancel,) = server.paths("/order-rvsecncl")
    assert cancel["headers"]["tr_id"] == "VTTC0013U"
    assert cancel["body"] == {"CANO": "50012345", "ACNT_PRDT_CD": "01", "KRX_FWDG_ORD_ORGNO": "06010",
                              "ORGN_ODNO": "0000002101", "ORD_DVSN": "00", "RVSE_CNCL_DVSN_CD": "02", "ORD_QTY": "0",
                              "ORD_UNPR": "0", "QTY_ALL_ORD_YN": "Y", "EXCG_ID_DVSN_CD": "KRX"}
    assert sum(clock.slept) >= 5.0                                      # fill_timeout_sec 만큼은 기다림


def test_unfilled_order_is_cancelled_and_reported_as_rejected(tmp_path):
    client, server, _ = make(tmp_path)
    server.fill = "none"
    res = client.submit_order(sell(10))
    assert res.status == OrderStatus.REJECTED and res.filled_qty == 0 and "취소" in res.message
    assert len(server.paths("/order-rvsecncl")) == 1


def test_exchange_side_rejection_row(tmp_path):
    client, server, _ = make(tmp_path)
    server.fill = "reject"
    res = client.submit_order(buy(10))
    assert res.status == OrderStatus.REJECTED and "거부" in res.message and server.paths("/order-rvsecncl") == []


def test_server_refusal_is_rejected_and_post_is_never_retried(tmp_path):
    client, server, _ = make(tmp_path)
    server.scripted["/order-cash"] = [FakeKis.err("APBK0919", "주문가능금액을 초과했습니다", 200)]
    res = client.submit_order(buy(10))
    assert res.status == OrderStatus.REJECTED and "APBK0919" in res.message and "주문가능금액" in res.message
    assert len(server.paths("/order-cash")) == 1 and server.orders == []
    server.scripted["/order-cash"] = [FakeKis.err("EGW00201", "초당 거래건수를 초과하였습니다.")]
    res = client.submit_order(buy(10))
    assert res.status == OrderStatus.REJECTED and len(server.paths("/order-cash")) == 2     # 재전송 없음


def test_network_error_on_order_is_resolved_from_order_list(tmp_path):
    client, server, _ = make(tmp_path)

    class LostReply:
        """주문은 서버에 접수됐는데 응답만 유실된 상황."""

        def __init__(self, srv):
            self.srv, self.done = srv, False

    orig = server._order
    state = {"first": True}

    def order_then_drop(call):
        out = orig(call)
        if state["first"]:
            state["first"] = False
            raise OSError("connection reset")
        return out

    server._order = order_then_drop
    res = client.submit_order(buy(10))
    assert res.status == OrderStatus.FILLED and res.filled_qty == 10 and res.broker_order_id == "0000002101"
    assert len(server.paths("/order-cash")) == 1                        # 다시 보내지 않고 내역에서 찾음


def test_network_error_with_no_trace_is_unknown(tmp_path):
    client, server, _ = make(tmp_path)
    server.scripted["/order-cash"] = [OSError("timed out")]
    res = client.submit_order(buy(10))
    assert res.status == OrderStatus.UNKNOWN and res.filled_qty == 0 and "확인하지 못했습니다" in res.message
    assert len(server.paths("/order-cash")) == 1
    server.scripted["/order-cash"] = [(502, {}, b"<html>Bad Gateway</html>")]
    assert client.submit_order(buy(10)).status == OrderStatus.UNKNOWN


def test_order_row_appearing_late_is_still_tracked(tmp_path):
    client, server, _ = make(tmp_path)
    server.visible_after = 3
    res = client.submit_order(buy(10))
    assert res.status == OrderStatus.FILLED and res.filled_qty == 10
    assert server.paths("/order-rvsecncl") == []


def test_unresolvable_order_state_is_unknown_with_order_number(tmp_path):
    client, server, _ = make(tmp_path)
    server.fill = "none"
    server.cancel_ok = False                    # 취소도 안 되고 잔량도 그대로
    res = client.submit_order(buy(10))
    assert res.status == OrderStatus.UNKNOWN and res.broker_order_id == "0000002101"
    assert "미체결 주문이 남아 있을 수" in res.message


def test_fill_that_completes_while_cancelling_is_reported_as_filled(tmp_path):
    client, server, _ = make(tmp_path)
    server.fill = "none"
    server.cancel_ok = False

    orig = server._cancel

    def cancel(b):
        for o in server.orders:
            o.update(tot_ccld_qty=o["ord_qty"], rmn_qty="0", avg_prvs="71300")     # 취소 직전에 전량 체결됨
        return orig(b)

    server._cancel = cancel
    res = client.submit_order(buy(10))
    assert res.status == OrderStatus.FILLED and res.avg_price == 71_300


def test_get_requests_retry_transient_failures(tmp_path):
    client, server, clock = make(tmp_path)
    server.scripted["/inquire-price"] = [OSError("reset"), FakeKis.err("EGW00201", "초당 거래건수를 초과하였습니다.")]
    assert client.get_quote("005930").price == 71_200
    assert len(server.paths("/inquire-price")) == 3
    server.scripted["/inquire-price"] = [FakeKis.err("EGW00201", "초과")] * 3
    with pytest.raises(BrokerError, match="EGW00201"):
        client.get_quote("005930")
    server.scripted["/inquire-price"] = [FakeKis.err("MCA05918", "종목코드 오류입니다.", 200)]
    with pytest.raises(BrokerError, match="종목코드 오류"):
        client.get_quote("999999")
    assert len(server.paths("/inquire-price")) == 7                     # 업무 오류는 재시도하지 않음


def test_expired_token_from_cache_is_replaced_and_request_retried(tmp_path):
    first, _, _ = make(tmp_path)
    first.get_quote("005930")                   # 토큰 파일 생성
    clock = Clock()
    server = FakeKis(clock)
    server.tokens = 1
    client = KisClient(first.cfg, token_dir=tmp_path, transport=server, now=clock.now, sleep=clock.sleep,
                       monotonic=clock.monotonic)
    server.scripted["/inquire-price"] = [FakeKis.err("EGW00123", "기간이 만료된 token 입니다.")]
    assert client.get_quote("005930").price == 71_200
    auths = [c["headers"]["authorization"] for c in server.paths("/inquire-price")]
    assert auths == ["Bearer TOKEN1", "Bearer TOKEN2"]


def test_recover_order_finds_matching_recent_order_only(tmp_path):
    client, server, clock = make(tmp_path)
    since = clock.now()
    assert client.recover_order(buy(10), since) is None
    client.submit_order(buy(10))
    res = client.recover_order(buy(10), since)
    assert res is not None and res.status == OrderStatus.FILLED and res.filled_qty == 10
    assert client.recover_order(buy(7), since) is None                  # 수량이 다르면 다른 주문
    assert client.recover_order(sell(10), since) is None                # 방향이 다르면 다른 주문
    assert client.recover_order(buy(10), since + timedelta(hours=1)) is None    # 그 이후에 낸 주문만


def test_check_connection_reports_each_step(tmp_path):
    client, server, _ = make(tmp_path)
    assert [(n, ok) for n, ok, _ in client.check_connection()] == [("접근 토큰", True), ("시세 조회", True), ("계좌 조회", True)]
    server.scripted["/inquire-balance"] = [FakeKis.err("OPSQ2000", "INPUT INVALID_CHECK_ACNO", 200)]
    rows = client.check_connection()
    assert rows[2][1] is False and "계좌번호" in rows[2][2]
    bad, bserver, _ = make(tmp_path / "x")
    bserver.token_response = (403, {"error_code": "EGW00103", "error_description": "bad key"})
    assert [(n, ok) for n, ok, _ in bad.check_connection()] == [("접근 토큰", False)]

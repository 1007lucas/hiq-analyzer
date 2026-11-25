"""데이터 계층 테스트 — CSV, 합성 데이터, 로더, 무료 시세 파서."""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta

import pytest

from autotrader.brokers.base import BrokerError, MarketData
from autotrader.data import DataError, generate_bars, load_bars, read_csv, write_csv
from autotrader.data import loader as loader_mod
from autotrader.data import providers
from autotrader.data.store import CsvFormatError, clean_bars, is_valid_bar, parse_day
from autotrader.models import KST, Bar, Quote

D = date(2024, 1, 2)


def bars3() -> list[Bar]:
    return [Bar(D, 100, 110, 95, 105, 1000), Bar(D + timedelta(days=1), 105, 108.5, 101, 102, 2000),
            Bar(D + timedelta(days=2), 102, 103, 99, 100, 0)]


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def test_csv_round_trip(tmp_path):
    p = write_csv(tmp_path / "sub" / "A.csv", bars3())
    assert read_csv(p) == bars3()
    assert p.read_text(encoding="utf-8").splitlines()[:2] == ["date,open,high,low,close,volume", "2024-01-02,100,110,95,105,1000"]
    assert not list((tmp_path / "sub").glob("*.tmp"))


def test_csv_accepts_korean_headers_cp949_commas_and_other_date_formats(tmp_path):
    text = '날짜,종가,시가,고가,저가,거래량\n2024.01.03,"71,200","70,800","71,500","70,500","1,234,567"\n20240102,70000,69000,70500,68900,100\n'
    p = tmp_path / "k.csv"
    p.write_bytes(text.encode("cp949"))
    got = read_csv(p)
    assert got == [Bar(date(2024, 1, 2), 69000, 70500, 68900, 70000, 100), Bar(date(2024, 1, 3), 70800, 71500, 70500, 71200, 1234567)]
    p.write_bytes(("﻿" + "Date,Open,High,Low,Close\n2024/1/2,1,2,1,2\n").encode("utf-8"))
    assert read_csv(p) == [Bar(date(2024, 1, 2), 1, 2, 1, 2, 0)]
    assert parse_day("2024-01-02 00:00:00") == date(2024, 1, 2)


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("", "비어"),
        ("a,b,c\n1,2,3\n", "필요한 열"),
        ("date,open,high,low,close\n2024-01-02,10,9,8,10\n", "가격이 이상"),          # 고가 < 시가
        ("date,open,high,low,close\n2024-01-02,10,x,8,10\n", "2번째 줄"),
        ("date,open,high,low,close\n어제,10,11,8,10\n", "2번째 줄"),
        ("date,open,high,low,close\n2024-01-02,10,11,8,10\n2024-01-02,10,11,8,10\n", "같은 날짜"),
    ],
)
def test_csv_errors_name_the_problem(tmp_path, text, fragment):
    p = tmp_path / "bad.csv"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(CsvFormatError) as ei:
        read_csv(p)
    assert fragment in str(ei.value)


def test_clean_bars_drops_invalid_sorts_and_dedupes():
    good = Bar(D, 10, 12, 9, 11, 5)
    later = Bar(D + timedelta(days=1), 11, 12, 10, 12, 5)
    dup = Bar(D, 10, 13, 9, 12, 7)
    bad = [Bar(D + timedelta(days=2), 0, 1, 0, 1, 1), Bar(D + timedelta(days=3), 10, 9, 8, 9, 1), Bar(D + timedelta(days=4), 5, 6, 5.5, 6, 1)]
    assert clean_bars([later, good, *bad, dup]) == [dup, later]
    assert is_valid_bar(good) and not any(is_valid_bar(b) for b in bad)


# --------------------------------------------------------------------------- #
# 합성 데이터
# --------------------------------------------------------------------------- #
def test_synthetic_is_deterministic_valid_and_skips_non_trading_days():
    a = generate_bars("005930", date(2026, 1, 1), date(2026, 12, 31))
    assert a == generate_bars("005930", date(2026, 1, 1), date(2026, 12, 31))
    assert a != generate_bars("000660", date(2026, 1, 1), date(2026, 12, 31))
    assert a != generate_bars("005930", date(2026, 1, 1), date(2026, 12, 31), seed=1)
    assert len(a) == 244 and all(is_valid_bar(b) for b in a)                    # 2026년 거래일 수
    assert all(b.date.weekday() < 5 for b in a) and date(2026, 2, 17) not in {b.date for b in a}
    assert all(abs(y.close / x.close - 1) < 0.31 for x, y in zip(a, a[1:]))     # 가격제한폭 안의 움직임
    assert generate_bars("005930", date(2026, 1, 5), date(2026, 1, 4)) == []


# --------------------------------------------------------------------------- #
# 로더
# --------------------------------------------------------------------------- #
class FakeKisData(MarketData):
    def __init__(self, bars=None, fail=False):
        self.bars, self.fail, self.calls = bars or bars3(), fail, 0

    def get_quote(self, symbol):
        raise BrokerError("n/a")

    def get_daily_bars(self, symbol, start, end):
        self.calls += 1
        if self.fail:
            raise BrokerError("KIS 장애")
        return [b for b in self.bars if start <= b.date <= end]


def test_load_synthetic_and_csv_and_validation(tmp_path):
    data, used = load_bars(["A", "B"], date(2024, 1, 1), date(2024, 3, 1), source="synthetic")
    assert set(data) == {"A", "B"} and used == {"A": "synthetic", "B": "synthetic"}
    assert all(date(2024, 1, 1) <= b.date <= date(2024, 3, 1) for b in data["A"])
    write_csv(tmp_path / "A.csv", bars3())
    seen = []
    data, used = load_bars(["A"], D + timedelta(days=1), D + timedelta(days=9), source="csv", csv_dir=tmp_path,
                           progress=lambda s, i, n: seen.append((s, i, n)))
    assert data["A"] == bars3()[1:] and used == {"A": "csv"} and seen == [("A", 1, 1)]
    with pytest.raises(DataError, match="CSV 파일이 없습니다"):
        load_bars(["ZZZ"], D, D, source="csv", csv_dir=tmp_path)
    with pytest.raises(DataError, match="알 수 없는 데이터 출처"):
        load_bars(["A"], D, D, source="bloomberg")
    with pytest.raises(DataError, match="기간"):
        load_bars(["A"], D, D - timedelta(days=1), source="synthetic")
    with pytest.raises(DataError, match="구간에 데이터가 없습니다"):
        load_bars(["A"], date(2030, 1, 1), date(2030, 1, 5), source="csv", csv_dir=tmp_path)


def test_kis_source_uses_daily_cache(tmp_path):
    kis = FakeKisData()
    end = D + timedelta(days=5)
    today = date(2024, 2, 1)
    os.environ.pop("TZ", None)
    d1, used = load_bars(["A"], D, end, source="auto", kis=kis, cache_dir=tmp_path, today=datetime.now(KST).date())
    assert used == {"A": "kis"} and kis.calls == 1 and (tmp_path / "kis" / "A.csv").is_file()
    d2, _ = load_bars(["A"], D, end, source="kis", kis=kis, cache_dir=tmp_path, today=datetime.now(KST).date())
    assert d2 == d1 and kis.calls == 1                                   # 같은 날 같은 구간 → 캐시
    load_bars(["A"], D, end, source="kis", kis=kis, cache_dir=tmp_path, today=datetime.now(KST).date(), refresh=True)
    assert kis.calls == 2                                                # refresh → 다시 받음
    load_bars(["A"], D - timedelta(days=30), end, source="kis", kis=kis, cache_dir=tmp_path, today=datetime.now(KST).date())
    assert kis.calls == 3                                                # 더 넓은 구간 → 다시 받음
    old = time.time() - 3 * 86400
    os.utime(tmp_path / "kis" / "A.csv", (old, old))
    load_bars(["A"], D, end, source="kis", kis=kis, cache_dir=tmp_path, today=datetime.now(KST).date())
    assert kis.calls == 4                                                # 어제 이전 캐시 → 다시 받음
    assert today  # (가독성용 변수)
    with pytest.raises(DataError, match="API 키"):
        load_bars(["A"], D, end, source="kis", kis=None)


def test_auto_falls_back_from_naver_to_yahoo_and_explains_total_failure(tmp_path, monkeypatch):
    calls = []

    def naver(symbol, start, end):
        calls.append("naver")
        raise providers.ProviderError("네이버 금융: 접속 실패")

    def yahoo(symbol, start, end):
        calls.append("yahoo")
        return bars3()

    monkeypatch.setattr(providers, "fetch_naver_daily", naver)
    monkeypatch.setattr(providers, "fetch_yahoo_daily", yahoo)
    data, used = load_bars(["A"], D, D + timedelta(days=5), source="auto", cache_dir=tmp_path)
    assert used == {"A": "yahoo"} and calls == ["naver", "yahoo"] and data["A"] == bars3()

    monkeypatch.setattr(providers, "fetch_yahoo_daily", lambda *a: [])
    with pytest.raises(DataError) as ei:
        load_bars(["B"], D, D + timedelta(days=5), source="auto", cache_dir=tmp_path)
    msg = str(ei.value)
    assert "naver: 네이버 금융: 접속 실패" in msg and "yahoo: 받은 데이터가 없습니다" in msg and "--source synthetic" in msg

    with pytest.raises(DataError, match="KIS 장애"):
        load_bars(["A"], D, D + timedelta(days=5), source="auto", kis=FakeKisData(fail=True), cache_dir=tmp_path / "x")
    assert loader_mod.SOURCES == ("auto", "kis", "naver", "yahoo", "csv", "synthetic")


# --------------------------------------------------------------------------- #
# 무료 시세 파서 (기억에 의존해 재구성한 응답 형태 — 실제 서버로 검증하지 못함)
# --------------------------------------------------------------------------- #
NAVER_TEXT = """
 [['날짜', '시가', '고가', '저가', '종가', '거래량', '외국인소진율'],

["20240102", 78200, 79800, 78200, 79600, 17142847, 54.01],
			
["20240103", 78500, 78800, 77000, 77000, 21753644, 54.07],
['20240104', 76100, 77300, 76100, 76600, 15324439, 53.98]

]
"""


def test_naver_daily_parser_and_request():
    assert providers.parse_naver_daily(NAVER_TEXT) == [
        Bar(date(2024, 1, 2), 78200, 79800, 78200, 79600, 17142847),
        Bar(date(2024, 1, 3), 78500, 78800, 77000, 77000, 21753644),
        Bar(date(2024, 1, 4), 76100, 77300, 76100, 76600, 15324439),
    ]
    seen = {}

    def http(url, headers):
        seen["url"], seen["headers"] = url, headers
        return NAVER_TEXT.encode("utf-8")

    got = providers.fetch_naver_daily("005930", date(2024, 1, 3), date(2024, 1, 31), http=http)
    assert [b.date for b in got] == [date(2024, 1, 3), date(2024, 1, 4)]
    assert "symbol=005930" in seen["url"] and "startTime=20240103" in seen["url"] and "endTime=20240131" in seen["url"]
    assert "timeframe=day" in seen["url"] and seen["headers"]["User-Agent"]
    with pytest.raises(providers.ProviderError, match="형식이 바뀌었"):
        providers.fetch_naver_daily("005930", D, D, http=lambda u, h: b"<html>blocked</html>")

    def down(url, headers):
        raise OSError("no route")

    with pytest.raises(providers.ProviderError, match="접속 실패"):
        providers.fetch_naver_daily("005930", D, D, http=down)


def yahoo_payload():
    base = int(datetime(2024, 1, 2, 9, 0, tzinfo=KST).timestamp())
    return {"chart": {"error": None, "result": [{
        "meta": {"gmtoffset": 32400, "symbol": "005930.KS"},
        "timestamp": [base, base + 86400, base + 2 * 86400],
        "indicators": {"quote": [{"open": [78200.0, None, 76100.0], "high": [79800.0, None, 77300.0],
                                  "low": [78200.0, None, 76100.0], "close": [79600.0, None, 76600.0],
                                  "volume": [17142847, None, 15324439]}]},
    }]}}


def test_yahoo_parser_skips_null_rows_and_tries_both_suffixes():
    assert providers.parse_yahoo_chart(yahoo_payload()) == [
        Bar(date(2024, 1, 2), 78200, 79800, 78200, 79600, 17142847),
        Bar(date(2024, 1, 4), 76100, 77300, 76100, 76600, 15324439),
    ]
    urls = []

    def http(url, headers):
        urls.append(url)
        if ".KS" in url:
            return json.dumps({"chart": {"result": None, "error": {"code": "Not Found", "description": "No data found"}}}).encode()
        return json.dumps(yahoo_payload()).encode()

    got = providers.fetch_yahoo_daily("035720", date(2024, 1, 1), date(2024, 1, 31), http=http)
    assert len(got) == 2 and "035720.KS" in urls[0] and "035720.KQ" in urls[1] and "interval=1d" in urls[0]
    with pytest.raises(providers.ProviderError, match="No data found"):
        providers.fetch_yahoo_daily("000000", D, D, http=lambda u, h: json.dumps(
            {"chart": {"result": None, "error": {"description": "No data found"}}}).encode())
    with pytest.raises(providers.ProviderError, match="형식"):
        providers.parse_yahoo_chart({"unexpected": 1})


def naver_quote_payload(**over):
    item = {"itemCode": "005930", "stockName": "삼성전자", "closePrice": "71,200", "openPrice": "70,800",
            "highPrice": "71,500", "lowPrice": "70,500", "accumulatedTradingVolume": "12,345,678",
            "compareToPreviousClosePrice": "1,200", "compareToPreviousPrice": {"code": "2", "name": "RISING"},
            "marketStatus": "OPEN", "tradeStopType": {"code": "1", "name": "TRADING"}}
    item.update(over)
    return {"pollingInterval": 7000, "datas": [item]}


def test_naver_quote_parser_and_market_data_wrapper():
    q = providers.parse_naver_quote("005930", naver_quote_payload())
    assert isinstance(q, Quote) and (q.price, q.open, q.high, q.low, q.prev_close, q.volume) == (71200, 70800, 71500, 70500, 70000, 12345678)
    assert not q.halted
    down = providers.parse_naver_quote("005930", naver_quote_payload(compareToPreviousClosePrice="-1,200",
                                                                     compareToPreviousPrice={"name": "FALLING"}))
    assert down.prev_close == 72400
    pre = providers.parse_naver_quote("005930", naver_quote_payload(accumulatedTradingVolume="0"))
    assert pre.open == 0 and pre.price == 71200
    assert providers.parse_naver_quote("005930", naver_quote_payload(tradeStopType={"name": "HALT"})).halted

    md = providers.NaverMarketData(http=lambda u, h: json.dumps(naver_quote_payload()).encode())
    assert md.get_quote("005930").price == 71200 and md.is_trading_day(D) is None
    for bad in (b"not json", json.dumps({"datas": []}).encode(), json.dumps(naver_quote_payload(closePrice="")).encode()):
        with pytest.raises(BrokerError):
            providers.NaverMarketData(http=lambda u, h, bad=bad: bad).get_quote("005930")
    assert providers.NaverMarketData(http=lambda u, h: NAVER_TEXT.encode()).get_daily_bars("005930", D, D)[0].close == 79600

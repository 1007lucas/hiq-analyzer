"""명령줄(CLI), 부품 조립(app), 대시보드 테스트."""

from __future__ import annotations

import http.client
import json
import threading
import tomllib
from datetime import date
from pathlib import Path

import pytest

from autotrader import app as app_mod
from autotrader import cli
from autotrader.brokers.kis import KisClient
from autotrader.brokers.paper import PaperBroker
from autotrader.config import build_config, load_config, parse_dotenv
from autotrader.control import BotLock, commands_dir, pop_commands
from autotrader.core import TradingCore
from autotrader.dashboard import build_payload, make_server
from autotrader.dashboard.server import PAGE_PATH
from autotrader.data.providers import NaverMarketData
from autotrader.models import Bar
from autotrader.state import SqliteStore
from autotrader.strategies import create_strategy
from autotrader.templates import CONFIG_TOML, DOTENV

from test_live import MON, FakeClock, FakeMarket, at, flat_history

ROOT = Path(__file__).resolve().parent.parent
MOCK_ENV = "KIS_MOCK_APP_KEY=mk\nKIS_MOCK_APP_SECRET=ms\nKIS_MOCK_ACCOUNT=50012345-01\n"
REAL_ENV = "KIS_APP_KEY=rk\nKIS_APP_SECRET=rs\nKIS_ACCOUNT=12345678-01\n"


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """init 을 마친 작업 폴더."""
    monkeypatch.chdir(tmp_path)
    for name in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT", "KIS_MOCK_APP_KEY", "KIS_MOCK_APP_SECRET",
                 "KIS_MOCK_ACCOUNT", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "NOTIFY_WEBHOOK_URL"):
        monkeypatch.delenv(name, raising=False)
    assert cli.main(["init"]) == 0
    return tmp_path


def run(capsys, *argv) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def seed_state(proj: Path, mode: str = "paper") -> None:
    """봇이 하루 돌아 종목을 보유한 상태의 DB 를 만듭니다."""
    cfg = load_config(proj / "config.toml")
    store = SqliteStore(cfg.state_path(mode))
    core = TradingCore(strategy=create_strategy("sma_cross"), universe=cfg.symbols, risk=cfg.risk, costs=cfg.costs,
                       broker=PaperBroker(), store=store, name_of=cfg.display_name)
    up = [Bar(date(2024, 1, 2 + i), 10_000 + 50 * i, 10_100 + 50 * i, 9_950 + 50 * i, 10_050 + 50 * i, 1.0) for i in range(25)]
    core.start_day(date(2024, 1, 29), {"005930": up})
    core.on_open({"005930": 11_300})
    core.on_close({"005930": 11_400})
    core.end_day({"005930": 11_400})
    assert "005930" in core.positions
    store.close()


# --------------------------------------------------------------------------- #
# 템플릿 / init / strategies
# --------------------------------------------------------------------------- #
def test_example_files_match_templates_and_are_valid():
    assert (ROOT / "config.example.toml").read_text(encoding="utf-8") == CONFIG_TOML
    assert (ROOT / ".env.example").read_text(encoding="utf-8") == DOTENV
    env = parse_dotenv(DOTENV)
    assert set(env) >= {"KIS_APP_KEY", "KIS_MOCK_ACCOUNT", "TELEGRAM_BOT_TOKEN"} and not any(env.values())
    cfg = build_config(tomllib.loads(CONFIG_TOML), env=env)
    assert cfg.mode == "paper" and cfg.live_enabled is False and cfg.risk.stop_loss_pct > 0
    create_strategy(cfg.strategy.name, cfg.strategy.params)


def test_init_creates_files_once_and_never_overwrites(proj, capsys):
    assert (proj / "config.toml").read_text(encoding="utf-8") == CONFIG_TOML
    (proj / ".env").write_text("KIS_APP_KEY=mine\n", encoding="utf-8")
    code, out, _ = run(capsys, "init")
    assert code == 0 and "이미 있어" in out
    assert (proj / ".env").read_text(encoding="utf-8") == "KIS_APP_KEY=mine\n"


def test_help_and_strategies(proj, capsys):
    code, out, _ = run(capsys)
    assert code == 0 and "backtest" in out and "자동매매" in out
    code, out, _ = run(capsys, "strategies")
    assert code == 0 and all(n in out for n in ("sma_cross", "volatility_breakout", "rsi_reversion", "momentum"))


def test_missing_config_gives_friendly_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, _, err = run(capsys, "status")
    assert code == 2 and "설정 파일을 찾을 수 없습니다" in err and "init" in err and "Traceback" not in err


# --------------------------------------------------------------------------- #
# backtest
# --------------------------------------------------------------------------- #
def test_backtest_synthetic_prints_metrics_and_writes_report(proj, capsys):
    code, out, _ = run(capsys, "backtest", "--source", "synthetic", "--start", "2023-01-01", "--end", "2024-03-31",
                       "--report", "out/r.html")
    assert code == 0
    for text in ("연습용 가짜 데이터", "총수익률", "최대낙폭(MDD)", "단순보유 총수익률", "과거 성과는 미래 수익을 보장하지 않습니다"):
        assert text in out
    assert "🟢 매수" not in out                                   # 매매 한 건 한 건을 화면에 쏟아내지 않음
    html_text = (proj / "out" / "r.html").read_text(encoding="utf-8")
    assert "백테스트 리포트" in html_text and "삼성전자(005930)" in html_text
    assert (proj / "out" / "r.csv").read_bytes().startswith(b"\xef\xbb\xbf")


def test_backtest_options_compare_and_errors(proj, capsys):
    code, out, _ = run(capsys, "backtest", "--source", "synthetic", "--start", "2023-06-01", "--end", "2024-03-31",
                       "--strategy", "volatility_breakout", "--param", "k=0.7", "--param", "hold=close",
                       "--symbols", "005930,000660", "--capital", "5000000", "--no-report")
    assert code == 0 and "volatility_breakout (k=0.7, hold=close" in out and "5,000,000원" in out
    assert not (proj / "reports").exists()
    code, out, _ = run(capsys, "backtest", "--source", "synthetic", "--start", "2023-06-01", "--end", "2024-03-31", "--compare")
    assert code == 0 and "전략 비교" in out and "(단순보유)" in out
    assert all(n in out for n in ("sma_cross", "donchian_breakout", "bollinger_reversion"))
    for argv, fragment in (
        (["--strategy", "nope"], "알 수 없는 전략"),
        (["--param", "fast=50"], "전략 설정 오류"),
        (["--param", "oops"], "--param 형식"),
        (["--start", "2024-05-01", "--end", "2024-01-01"], "기간이 올바르지"),
        (["--source", "csv"], "CSV 파일이 없습니다"),
    ):
        code, _, err = run(capsys, "backtest", "--source", "synthetic", "--no-report", *argv)
        assert code == 2 and fragment in err, (argv, err)


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def test_doctor_offline_ok_and_reports_missing_keys_for_mode(proj, capsys):
    code, out, _ = run(capsys, "doctor", "--offline")
    assert code == 0 and "문제 없음" in out and "✅ 설정 파일" in out
    code, out, _ = run(capsys, "doctor", "--offline", "--mode", "kis-mock")
    assert code == 1 and "현재 모드에 필요합니다" in out
    (proj / ".env").write_text(MOCK_ENV, encoding="utf-8")
    code, out, _ = run(capsys, "doctor", "--offline", "--mode", "kis-mock")
    assert code == 0 and "설정됨" in out
    (proj / "config.toml").write_text(CONFIG_TOML.replace("stop_loss_pct = 0.07", "stop_loss_pct = 0.0"), encoding="utf-8")
    code, out, _ = run(capsys, "doctor", "--offline")
    assert code == 0 and "손절이 꺼져 있습니다" in out
    (proj / "config.toml").write_text(CONFIG_TOML.replace('name = "sma_cross"', 'name = "nope"'), encoding="utf-8")
    code, out, _ = run(capsys, "doctor", "--offline")
    assert code == 1 and "알 수 없는 전략" in out


# --------------------------------------------------------------------------- #
# app: 모드별 조립
# --------------------------------------------------------------------------- #
def test_build_services_per_mode(proj):
    cfg = load_config(proj / "config.toml")
    s = app_mod.build_services(cfg, "paper")
    assert isinstance(s.broker, PaperBroker) and isinstance(s.market, NaverMarketData) and "비공식" in s.market_label
    with pytest.raises(app_mod.SetupError, match="KIS_MOCK_APP_KEY"):
        app_mod.build_services(cfg, "kis-mock")
    with pytest.raises(app_mod.SetupError, match="enabled = true"):
        app_mod.build_services(cfg, "kis-live")

    (proj / ".env").write_text(MOCK_ENV, encoding="utf-8")
    cfg = load_config(proj / "config.toml")
    s = app_mod.build_services(cfg, "paper")
    assert isinstance(s.broker, PaperBroker) and isinstance(s.market, KisClient) and s.market.mock
    s = app_mod.build_services(cfg, "kis-mock")
    assert s.broker is s.market and s.broker.mock

    (proj / ".env").write_text(MOCK_ENV + REAL_ENV, encoding="utf-8")
    cfg = load_config(proj / "config.toml")
    s = app_mod.build_services(cfg, "kis-mock")
    assert s.broker.mock and not s.market.mock                    # 주문은 모의 계좌, 시세는 실전 서버
    with pytest.raises(app_mod.SetupError, match="허용되어 있지 않습니다"):
        app_mod.build_services(cfg, "kis-live")                    # 키가 있어도 스위치가 꺼져 있으면 거부
    (proj / "config.toml").write_text(CONFIG_TOML.replace("enabled = false", "enabled = true"), encoding="utf-8")
    s = app_mod.build_services(load_config(proj / "config.toml"), "kis-live")
    assert s.broker is s.market and not s.broker.mock


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def fake_run_env(monkeypatch, proj):
    """실제 시계·네트워크 대신 가짜 시계·시세로 run 명령을 돌릴 수 있게 바꿔 끼웁니다."""
    cfg = load_config(proj / "config.toml")
    clock = FakeClock(at(MON, 8, 0))
    paths = {MON: {s: [("09:00", 10_000), ("12:00", 10_100), ("15:30", 10_150)] for s in cfg.symbols}}
    history = {s: flat_history(n=30) for s in cfg.symbols}
    # 5일선이 20일선 위에 있도록 최근 5일을 살짝 올려 둠 → sma_cross 가 시가 매수
    for s in cfg.symbols:
        history[s] = [Bar(b.date, b.open, b.high, b.low, b.close if i < 25 else 10_050, b.volume) for i, b in enumerate(history[s])]
        history[s] = [Bar(b.date, min(b.open, b.close), max(b.high, b.close), b.low, b.close, b.volume) for b in history[s]]
    market = FakeMarket(clock, history, paths)
    real_build_trader = cli.build_trader
    monkeypatch.setattr(cli, "build_services", lambda c, mode: app_mod.Services(PaperBroker(), market, "가짜 주문", "가짜 시세"))
    monkeypatch.setattr(cli, "build_trader", lambda c, mode, **kw: real_build_trader(c, mode, **{**kw, "clock": clock}))
    monkeypatch.setattr(cli, "build_core", lambda c, **kw: app_mod.build_core(c, **{**kw, "clock": clock}))
    return cfg, clock


def test_run_paper_one_day_end_to_end(proj, capsys, monkeypatch):
    cfg, clock = fake_run_env(monkeypatch, proj)
    code, out, _ = run(capsys, "run", "--days", "1")
    assert code == 0 and "페이퍼(가상 매매)" in out and "Ctrl+C" in out
    assert not (proj / "data" / "bot-paper.lock").exists()            # 종료 시 잠금 해제
    store = SqliteStore(cfg.state_path("paper"), read_only=True)
    orders = store.orders()
    assert len(orders) == 3 and all(o["side"] == "buy" and o["status"] == "filled" for o in orders)   # 최대 3종목
    assert store.equity_history()[-1][0] == MON
    store.close()
    assert (proj / "data" / "logs" / "autotrader.log").is_file()

    code, out, _ = run(capsys, "status")
    assert code == 0 and "봇: 꺼져 있음" in out and "보유 종목" in out and "삼성전자(005930)" in out and "최근 주문" in out


def test_run_refuses_second_instance_and_bad_modes(proj, capsys, monkeypatch):
    fake_run_env(monkeypatch, proj)
    with BotLock(proj / "data", "paper"):
        code, _, err = run(capsys, "run", "--days", "1")
        assert code == 2 and "이미 실행 중" in err
    monkeypatch.undo()
    monkeypatch.chdir(proj)
    code, _, err = run(capsys, "run", "--mode", "kis-mock")
    assert code == 2 and "KIS_MOCK_APP_KEY" in err
    code, _, err = run(capsys, "run", "--mode", "kis-live")
    assert code == 2 and "실전 매매가 허용되어 있지 않습니다" in err


def test_live_mode_requires_typed_confirmation(proj, capsys, monkeypatch):
    (proj / "config.toml").write_text(
        CONFIG_TOML.replace('mode = "paper"', 'mode = "kis-live"').replace("enabled = false", "enabled = true"), encoding="utf-8")
    fake_run_env(monkeypatch, proj)
    args = cli.build_parser().parse_args(["run", "--days", "1"])
    with pytest.raises(cli.CliError, match="시작하지 않았습니다"):
        cli.cmd_run(args, input_fn=lambda prompt: "yes")
    out = capsys.readouterr().out
    assert "실제 돈으로 주문이 나갑니다" in out
    assert not (proj / "data" / "state-kis-live.db").exists()          # 확인 전에는 아무것도 시작하지 않음
    assert cli.cmd_run(args, input_fn=lambda prompt: "실전매매") == 0
    assert (proj / "data" / "state-kis-live.db").exists()
    args = cli.build_parser().parse_args(["run", "--days", "1", "--i-understand"])
    assert cli.cmd_run(args, input_fn=lambda prompt: pytest.fail("묻지 않아야 함")) == 0


# --------------------------------------------------------------------------- #
# status / stop / resume / forget / liquidate
# --------------------------------------------------------------------------- #
def test_status_without_history(proj, capsys):
    code, out, _ = run(capsys, "status")
    assert code == 0 and "실행한 기록이 없습니다" in out


def test_stop_and_resume_offline(proj, capsys):
    seed_state(proj)
    code, out, _ = run(capsys, "stop")
    assert code == 0 and (proj / "data" / "STOP").exists() and "resume" in out
    code, out, _ = run(capsys, "status")
    assert "긴급 정지(STOP) 상태" in out
    # 최대 낙폭 중단 상태로 만들어 둔 뒤 resume
    cfg = load_config(proj / "config.toml")
    store = SqliteStore(cfg.state_path("paper"))
    st = store.load_state()
    st["halted"] = True
    store.save_state(st)
    store.close()
    code, out, _ = run(capsys, "resume")
    assert code == 0 and not (proj / "data" / "STOP").exists() and "신규 매수 중단도 해제" in out
    store = SqliteStore(cfg.state_path("paper"), read_only=True)
    assert store.load_state()["halted"] is False
    store.close()


def test_forget_offline_and_commands_when_bot_is_running(proj, capsys):
    seed_state(proj)
    code, _, err = run(capsys, "forget", "000660")
    assert code == 2 and "포지션이 없거나" in err
    code, _, err = run(capsys, "forget", "005930", "--qty", "0")
    assert code == 2 and "--qty" in err
    code, out, _ = run(capsys, "forget", "005930", "--price", "12000")
    assert code == 0 and "실제 주문은 나가지 않았습니다" in out
    cfg = load_config(proj / "config.toml")
    store = SqliteStore(cfg.state_path("paper"), read_only=True)
    assert store.load_state()["positions"] == {} and store.orders()[-1]["price"] == 12_000
    store.close()

    code, _, err = run(capsys, "liquidate", "--yes")
    assert code == 2 and "봇이 실행 중이 아닙니다" in err
    with BotLock(proj / "data", "paper"):                              # 봇이 실행 중인 상황
        code, out, _ = run(capsys, "liquidate", "--yes")
        assert code == 0 and "요청했습니다" in out
        run(capsys, "forget", "005930", "--qty", "3")
        run(capsys, "resume")
        assert pop_commands(proj / "data", "paper") == [
            {"cmd": "liquidate", "args": {}},
            {"cmd": "forget", "args": {"symbol": "005930", "qty": 3, "price": None}},
            {"cmd": "resume", "args": {}},
        ]
        args = cli.build_parser().parse_args(["liquidate"])
        assert cli.cmd_liquidate(args, input_fn=lambda p: "n") == 1     # 확인에서 거절하면 아무것도 하지 않음
        assert not list(commands_dir(proj / "data", "paper").glob("*.json"))


# --------------------------------------------------------------------------- #
# 대시보드
# --------------------------------------------------------------------------- #
def test_payload_without_db_with_db_and_with_corrupt_db(proj):
    cfg = load_config(proj / "config.toml")
    p = build_payload(cfg)
    assert p["db_exists"] is False and p["snapshot"] is None and p["error"] == "" and p["mode_label"] == "페이퍼(가상 매매)"
    seed_state(proj)
    (proj / "data" / "STOP").write_text("x", encoding="utf-8")
    p = json.loads(json.dumps(build_payload(cfg)))                      # JSON 으로 왕복 가능
    assert p["db_exists"] and p["stop_active"] and not p["bot_running"]
    assert p["snapshot"]["positions"][0]["name"] == "삼성전자(005930)"
    assert p["orders"][0]["name"] == "삼성전자(005930)" and p["equity"][-1]["day"] == "2024-01-29"
    assert p["state_saved_at"]
    with BotLock(proj / "data", "paper"):
        assert build_payload(cfg)["bot_running"] is True
    cfg.state_path("kis-mock").write_bytes(b"this is not a sqlite file at all")
    bad = build_payload(cfg, "kis-mock")
    assert bad["error"].startswith("상태 파일을 읽지 못했습니다") and bad["snapshot"] is None


@pytest.fixture
def server(proj):
    seed_state(proj)
    srv = make_server(load_config(proj / "config.toml"), port=0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def request(port: int, method: str, path: str, host: str | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Host": host} if host else {}
    conn.request(method, path, headers=headers)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp, body


def test_dashboard_http_behaviour(server):
    resp, body = request(server, "GET", "/")
    assert resp.status == 200 and resp.getheader("Content-Type").startswith("text/html")
    csp = resp.getheader("Content-Security-Policy")
    assert "default-src 'none'" in csp and "connect-src 'self'" in csp
    assert resp.getheader("Cache-Control") == "no-store" and resp.getheader("X-Content-Type-Options") == "nosniff"
    assert resp.getheader("X-Frame-Options") == "DENY" and resp.getheader("Access-Control-Allow-Origin") is None
    assert "자동매매 대시보드" in body.decode("utf-8")

    resp, body = request(server, "GET", "/api/state?x=1")
    data = json.loads(body)
    assert resp.status == 200 and resp.getheader("Content-Type").startswith("application/json")
    assert data["snapshot"]["positions"] and set(data) >= {"orders", "equity", "events", "bot_running", "stop_active"}

    resp, body = request(server, "HEAD", "/")
    assert resp.status == 200 and body == b""
    assert request(server, "GET", "/healthz")[1] == b"ok"
    assert request(server, "GET", "/nope")[0].status == 404
    assert request(server, "GET", "/../config.toml")[0].status == 404
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        assert request(server, method, "/api/state")[0].status == 405
    assert request(server, "GET", "/", host="evil.example")[0].status == 403           # DNS 리바인딩 차단
    assert request(server, "GET", "/api/state", host=f"evil.example:{server}")[0].status == 403
    for good in (f"localhost:{server}", f"127.0.0.1:{server}", "localhost", f"[::1]:{server}"):
        assert request(server, "GET", "/healthz", host=good)[0].status == 200


def test_dashboard_page_is_self_contained_and_never_injects_html():
    page = PAGE_PATH.read_text(encoding="utf-8")
    assert "http://www.w3.org/2000/svg" in page                         # SVG 네임스페이스 문자열만 허용
    stripped = page.replace("http://www.w3.org/2000/svg", "")
    assert "http://" not in stripped and "https://" not in stripped and "//cdn" not in stripped
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert banned not in page, banned
    assert "조회 전용" in page and 'name="viewport"' in page and "prefers-color-scheme:dark" in page


def test_port_in_use_is_explained(proj):
    cfg = load_config(proj / "config.toml")
    first = make_server(cfg, port=0)
    try:
        with pytest.raises(RuntimeError, match="--port"):
            make_server(cfg, port=first.server_address[1])
    finally:
        first.server_close()

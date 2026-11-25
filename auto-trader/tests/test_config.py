"""설정 로딩/검증 테스트."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from autotrader.config import ConfigError, build_config, load_config, parse_dotenv, parse_hhmm

BASE = {"universe": {"symbols": ["005930", "069500"]}}


def test_defaults_are_safe():
    cfg = build_config(BASE)
    assert cfg.mode == "paper"                 # 기본은 가상 매매
    assert cfg.live_enabled is False           # 실전은 명시적으로 켜야 함
    assert cfg.risk.stop_loss_pct > 0          # 손절은 기본으로 켜져 있음
    assert cfg.risk.max_positions * cfg.risk.position_pct <= 1.0
    assert cfg.kis_real.mock is False and cfg.kis_mock.mock is True
    assert not cfg.kis_real.configured and not cfg.kis_mock.configured
    assert cfg.kis_for_market_data() is None
    assert not cfg.notify.enabled


def test_sections_and_types_are_parsed():
    cfg = build_config(
        {
            "general": {"mode": "kis-mock", "data_dir": "mydata", "log_level": "debug"},
            "universe": {"symbols": ["005930", "0152e0"], "names": {"005930": "삼성전자"}},
            "strategy": {"name": "sma_cross", "params": {"fast": 5, "slow": 20}},
            "risk": {"capital": 3_000_000, "max_positions": 2, "position_pct": 0.5, "stop_loss_pct": 0.07},
            "costs": {"commission_rate": 0.0002},
            "schedule": {"poll_interval_sec": 5, "close_exit_time": "15:10", "extra_holidays": ["2027-03-03"]},
            "backtest": {"start": "2022-01-03", "data_source": "synthetic"},
            "kis": {"order_style": "limit", "limit_ticks": 3},
            "live": {"enabled": True},
        },
        base_dir=Path("/base"),
    )
    assert cfg.mode == "kis-mock" and cfg.log_level == "DEBUG"
    assert cfg.data_dir == Path("/base/mydata")
    assert cfg.symbols == ("005930", "0152E0")             # 대문자로 정규화, 영문 포함 코드 허용
    assert cfg.display_name("005930") == "삼성전자(005930)" and cfg.display_name("0152E0") == "0152E0"
    assert cfg.strategy.name == "sma_cross" and cfg.strategy.params == {"fast": 5, "slow": 20}
    assert cfg.risk.capital == 3_000_000.0 and isinstance(cfg.risk.capital, float)
    assert cfg.risk.max_positions == 2 and cfg.costs.commission_rate == 0.0002
    assert cfg.schedule.poll_interval_sec == 5.0 and cfg.schedule.extra_holiday_dates == (date(2027, 3, 3),)
    assert cfg.kis_mock.order_style == "limit" and cfg.kis_real.limit_ticks == 3
    assert cfg.live_enabled is True
    assert cfg.state_path() == Path("/base/mydata/state-kis-mock.db")
    assert cfg.state_path("paper") == Path("/base/mydata/state-paper.db")
    assert cfg.stop_file == Path("/base/mydata/STOP")


def test_secrets_come_from_env_only():
    env = {
        "KIS_APP_KEY": " realkey ",
        "KIS_APP_SECRET": "realsecret",
        "KIS_ACCOUNT": "12345678-01",
        "KIS_MOCK_APP_KEY": "mockkey",
        "KIS_MOCK_APP_SECRET": "mocksecret",
        "KIS_MOCK_ACCOUNT": "5001234501",
        "TELEGRAM_BOT_TOKEN": "t",
        "TELEGRAM_CHAT_ID": "42",
    }
    cfg = build_config(BASE, env=env)
    assert cfg.kis_real.app_key == "realkey" and cfg.kis_real.account_no == "12345678" and cfg.kis_real.account_product == "01"
    assert cfg.kis_mock.account_no == "50012345" and cfg.kis_mock.account_product == "01"
    assert cfg.kis_real.configured and cfg.kis_mock.configured and cfg.notify.enabled
    assert cfg.kis_for_mode("kis-live") is cfg.kis_real and cfg.kis_for_mode("kis-mock") is cfg.kis_mock
    assert cfg.kis_for_market_data() is cfg.kis_real

    with pytest.raises(ConfigError):                      # 키를 TOML 에 적으면 거부
        build_config({**BASE, "kis": {"app_key": "x"}})
    with pytest.raises(ConfigError):
        build_config({**BASE, "notify": {"telegram_token": "x"}})
    with pytest.raises(ConfigError, match="KIS_ACCOUNT"):
        build_config(BASE, env={"KIS_ACCOUNT": "1234"})


@pytest.mark.parametrize(
    "patch, fragment",
    [
        ({"general": {"mode": "real"}}, "general.mode"),
        ({"universe": {"symbols": []}}, "종목코드를 1개 이상"),
        ({"universe": {"symbols": ["005930", "005930"]}}, "중복"),
        ({"universe": {"symbols": ["5930"]}}, "종목코드 형식"),
        ({"universe": {"symbols": "005930"}}, "목록"),
        ({"risk": {"stop_loss_pct": 5}}, "risk.stop_loss_pct"),
        ({"risk": {"position_pct": 0}}, "risk.position_pct"),
        ({"risk": {"capital": -1}}, "risk.capital"),
        ({"risk": {"max_positions": 1.5}}, "정수"),
        ({"risk": {"max_positions": True}}, "정수"),
        ({"risk": {"capital": "많이"}}, "숫자"),
        ({"risk": {"daily_loss_action": "panic"}}, "daily_loss_action"),
        ({"risk": {"no_such_option": 1}}, "알 수 없는 항목"),
        ({"costs": {"sell_tax_rate": 0.2}}, "costs.sell_tax_rate"),
        ({"schedule": {"close_exit_time": "25:00"}}, "범위"),
        ({"schedule": {"close_exit_time": "08:00"}}, "close_exit_time"),
        ({"schedule": {"poll_interval_sec": 0}}, "poll_interval_sec"),
        ({"schedule": {"extra_holidays": ["내일"]}}, "extra_holidays"),
        ({"backtest": {"start": "2024/01/01"}}, "backtest.start"),
        ({"backtest": {"data_source": "bloomberg"}}, "data_source"),
        ({"kis": {"order_style": "fok"}}, "order_style"),
        ({"live": {"enabled": True, "x": 1}}, "알 수 없는 항목"),
        ({"typo_section": {}}, "알 수 없는 설정 섹션"),
    ],
)
def test_invalid_values_are_rejected_with_korean_messages(patch, fragment):
    raw = {**BASE, **patch}
    with pytest.raises(ConfigError) as ei:
        build_config(raw)
    assert fragment in str(ei.value)


def test_overrides_use_dotted_paths():
    cfg = build_config(BASE, overrides={"mode": "kis-mock", "strategy.name": "momentum", "risk.capital": 5e6, "log_level": None})
    assert cfg.mode == "kis-mock" and cfg.strategy.name == "momentum" and cfg.risk.capital == 5_000_000.0


def test_load_config_reads_toml_and_dotenv(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        '[general]\nmode = "paper"\ndata_dir = "d"\n[universe]\nsymbols = ["005930"]\n', encoding="utf-8"
    )
    (tmp_path / ".env").write_text(
        "# 주석\nKIS_MOCK_APP_KEY='filekey'\nexport KIS_MOCK_APP_SECRET=filesecret # 뒤 주석\nKIS_MOCK_ACCOUNT=50012345-01\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("KIS_MOCK_APP_KEY", raising=False)
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "from-environment")       # 실제 환경변수가 .env 보다 우선
    cfg = load_config(tmp_path / "config.toml")
    assert cfg.kis_mock.app_key == "filekey" and cfg.kis_mock.app_secret == "from-environment"
    assert cfg.data_dir == tmp_path / "d"

    with pytest.raises(ConfigError, match="init"):
        load_config(tmp_path / "missing.toml")
    (tmp_path / "bad.toml").write_text("[general\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="문법"):
        load_config(tmp_path / "bad.toml")


def test_parse_helpers():
    assert parse_dotenv('A=1\nB="x y"\n\n#C=3\nexport D=4\nE=a=b\nF=v # c') == {"A": "1", "B": "x y", "D": "4", "E": "a=b", "F": "v"}
    assert parse_hhmm("9:05") == time(9, 5) and parse_hhmm("15:15:30") == time(15, 15, 30)
    with pytest.raises(ConfigError):
        parse_hhmm("1515")

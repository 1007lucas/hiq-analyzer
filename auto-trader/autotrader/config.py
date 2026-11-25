"""설정 로딩과 검증.

* 일반 설정: ``config.toml`` (TOML)
* 비밀 값(API 키, 계좌번호, 알림 토큰): 환경변수 또는 ``.env`` 파일 — 절대 TOML 에 넣지 않습니다.

모든 설정 클래스는 불변(frozen) dataclass 입니다.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field, fields
from datetime import date, time
from pathlib import Path
from typing import Any, Mapping

MODES = ("paper", "kis-mock", "kis-live")
SYMBOL_RE = re.compile(r"^[0-9A-Z]{6}$")  # 국내 종목 단축코드 6자리 (신형 코드는 영문 포함 가능)


class ConfigError(ValueError):
    """설정이 잘못되었을 때."""


# --------------------------------------------------------------------------- #
# 섹션별 설정
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StrategyConfig:
    name: str = "volatility_breakout"
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskConfig:
    capital: float = 10_000_000.0       # 봇 운용자금(원). 봇은 이 한도 안에서만 매매합니다.
    max_positions: int = 3              # 동시에 보유할 최대 종목 수
    position_pct: float = 0.30          # 1종목당 투입 비중 (봇 평가금 대비)
    max_order_amount: float = 0.0       # 1회 매수 최대 금액(원). 0 = 제한 없음
    cash_reserve_pct: float = 0.01      # 항상 남겨둘 현금 비율 (수수료/슬리피지 대비)
    stop_loss_pct: float = 0.05         # 손절: 평균단가 대비 하락률. 0 = 사용 안 함
    take_profit_pct: float = 0.0        # 익절: 평균단가 대비 상승률. 0 = 사용 안 함
    trailing_stop_pct: float = 0.0      # 추적손절: 진입 후 최고가 대비 하락률. 0 = 사용 안 함
    cooldown_days: int = 3              # 손절/익절로 청산된 종목의 재진입 금지 거래일 수
    breakout_max_chase_pct: float = 0.01  # 돌파 목표가보다 이만큼 넘게 오른 가격은 추격매수하지 않음
    daily_loss_limit_pct: float = 0.03  # 하루 손실 한도(시작 평가금 대비). 0 = 사용 안 함
    daily_loss_action: str = "halt"     # "halt": 신규 진입만 중단 / "liquidate": 전량 청산 후 중단
    max_drawdown_pct: float = 0.20      # 최고 평가금 대비 낙폭 한도. 넘으면 수동 해제 전까지 신규 진입 중단. 0 = 사용 안 함
    max_orders_per_day: int = 30        # 하루 최대 신규 매수 주문 수 (폭주 방지)

    def validate(self) -> None:
        _require(self.capital > 0, "risk.capital 은 0보다 커야 합니다")
        _require(self.max_positions >= 1, "risk.max_positions 는 1 이상이어야 합니다")
        _require(0 < self.position_pct <= 1, "risk.position_pct 는 0 초과 1 이하여야 합니다")
        _require(self.max_order_amount >= 0, "risk.max_order_amount 는 0 이상이어야 합니다")
        _require(0 <= self.cash_reserve_pct < 1, "risk.cash_reserve_pct 는 0 이상 1 미만이어야 합니다")
        for name in ("stop_loss_pct", "trailing_stop_pct", "daily_loss_limit_pct", "max_drawdown_pct"):
            v = getattr(self, name)
            _require(0 <= v < 1, f"risk.{name} 는 0 이상 1 미만이어야 합니다 (예: 5% → 0.05)")
        _require(self.take_profit_pct >= 0, "risk.take_profit_pct 는 0 이상이어야 합니다")
        _require(self.cooldown_days >= 0, "risk.cooldown_days 는 0 이상이어야 합니다")
        _require(self.breakout_max_chase_pct >= 0, "risk.breakout_max_chase_pct 는 0 이상이어야 합니다")
        _require(
            self.daily_loss_action in ("halt", "liquidate"),
            'risk.daily_loss_action 은 "halt" 또는 "liquidate" 여야 합니다',
        )
        _require(self.max_orders_per_day >= 1, "risk.max_orders_per_day 는 1 이상이어야 합니다")


@dataclass(frozen=True)
class CostConfig:
    commission_rate: float = 0.00015    # 매매 수수료율 (매수·매도 각각). 0.015%
    sell_tax_rate: float = 0.0020       # 매도 시 거래세율(증권거래세+농특세). 증권사/연도별로 확인 필요
    slippage_rate: float = 0.0005       # 슬리피지 가정 (백테스트/페이퍼 체결가에 불리하게 반영)

    def validate(self) -> None:
        for name in ("commission_rate", "sell_tax_rate", "slippage_rate"):
            v = getattr(self, name)
            _require(0 <= v < 0.1, f"costs.{name} 는 0 이상 0.1 미만이어야 합니다 (예: 0.015% → 0.00015)")


@dataclass(frozen=True)
class ScheduleConfig:
    entry_delay_sec: int = 30           # 장 시작 후 이만큼 기다렸다가 시가 주문 실행
    open_entry_deadline: str = "09:30"  # 이 시각 이후에 봇을 켜면 '시가 매수'는 건너뜀 (시가 매도는 실행)
    close_exit_time: str = "15:15"      # 종가 청산 주문 시각 (동시호가 15:20 이전 권장)
    poll_interval_sec: float = 10.0     # 장중 시세 확인 주기(초)
    extra_holidays: tuple[str, ...] = ()  # 내장 달력에 없는 휴장일 추가 (예: ["2027-03-03"])

    def validate(self) -> None:
        _require(0 <= self.entry_delay_sec <= 3600, "schedule.entry_delay_sec 는 0~3600 이어야 합니다")
        _require(self.poll_interval_sec >= 1, "schedule.poll_interval_sec 는 1 이상이어야 합니다")
        deadline = parse_hhmm(self.open_entry_deadline, "schedule.open_entry_deadline")
        close_exit = parse_hhmm(self.close_exit_time, "schedule.close_exit_time")
        _require(time(9, 0) <= deadline <= time(15, 30), "schedule.open_entry_deadline 은 09:00~15:30 사이여야 합니다")
        _require(time(9, 0) < close_exit <= time(15, 30), "schedule.close_exit_time 은 09:00~15:30 사이여야 합니다")
        _require(
            isinstance(self.extra_holidays, (list, tuple)),
            'schedule.extra_holidays 는 날짜 목록이어야 합니다. 예: ["2027-03-03"]',
        )
        for h in self.extra_holidays:
            parse_date(h, "schedule.extra_holidays")

    @property
    def extra_holiday_dates(self) -> tuple[date, ...]:
        return tuple(parse_date(h, "schedule.extra_holidays") for h in self.extra_holidays)


@dataclass(frozen=True)
class BacktestConfig:
    start: str = "2021-01-01"           # YYYY-MM-DD
    end: str = ""                       # 비우면 오늘까지
    data_source: str = "auto"           # auto | kis | naver | yahoo | csv | synthetic

    def validate(self) -> None:
        parse_date(self.start, "backtest.start")
        if self.end:
            parse_date(self.end, "backtest.end")
        _require(
            self.data_source in ("auto", "kis", "naver", "yahoo", "csv", "synthetic"),
            "backtest.data_source 는 auto/kis/naver/yahoo/csv/synthetic 중 하나여야 합니다",
        )


@dataclass(frozen=True)
class KisConfig:
    """한국투자증권 Open API 접속 정보 (실전 또는 모의 중 한쪽)."""

    app_key: str = ""
    app_secret: str = ""
    account_no: str = ""                # 계좌번호 앞 8자리 (CANO)
    account_product: str = "01"         # 계좌번호 뒤 2자리 (ACNT_PRDT_CD)
    mock: bool = True                   # True = 모의투자 서버
    max_calls_per_sec: float = 0.0      # 0 = 환경별 기본값 사용
    order_style: str = "market"         # "market": 시장가 / "limit": 현재가±n틱 지정가(체결 안 되면 취소)
    limit_ticks: int = 5                # order_style="limit" 일 때 유리하지 않은 방향으로 더할 틱 수
    fill_timeout_sec: float = 20.0      # 체결 대기 시간. 넘으면 잔량 취소

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret and self.account_no)

    def validate(self) -> None:
        _require(self.order_style in ("market", "limit"), 'kis.order_style 은 "market" 또는 "limit" 여야 합니다')
        _require(0 <= self.limit_ticks <= 50, "kis.limit_ticks 는 0~50 이어야 합니다")
        _require(self.fill_timeout_sec >= 1, "kis.fill_timeout_sec 는 1 이상이어야 합니다")
        _require(self.max_calls_per_sec >= 0, "kis.max_calls_per_sec 는 0 이상이어야 합니다")
        if self.account_no:
            _require(
                bool(re.fullmatch(r"\d{8}", self.account_no)) and bool(re.fullmatch(r"\d{2}", self.account_product)),
                "계좌번호 형식이 올바르지 않습니다. 예: 12345678-01",
            )


@dataclass(frozen=True)
class NotifyConfig:
    telegram_token: str = ""
    telegram_chat_id: str = ""
    webhook_url: str = ""               # 디스코드/슬랙 호환 웹훅 URL

    @property
    def enabled(self) -> bool:
        return bool((self.telegram_token and self.telegram_chat_id) or self.webhook_url)


@dataclass(frozen=True)
class Config:
    mode: str = "paper"                 # paper | kis-mock | kis-live
    data_dir: Path = Path("data")
    log_level: str = "INFO"
    symbols: tuple[str, ...] = ()
    names: Mapping[str, str] = field(default_factory=dict)   # 종목코드 → 표시용 이름 (선택)
    live_enabled: bool = False          # [live] enabled — 실전 매매 허용 스위치
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    costs: CostConfig = field(default_factory=CostConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    kis_real: KisConfig = field(default_factory=lambda: KisConfig(mock=False))
    kis_mock: KisConfig = field(default_factory=lambda: KisConfig(mock=True))
    notify: NotifyConfig = field(default_factory=NotifyConfig)

    # -- 편의 메서드 ---------------------------------------------------------
    def validate(self) -> None:
        _require(self.mode in MODES, f"general.mode 는 {', '.join(MODES)} 중 하나여야 합니다")
        _require(len(self.symbols) > 0, "universe.symbols 에 종목코드를 1개 이상 넣어 주세요")
        _require(len(set(self.symbols)) == len(self.symbols), "universe.symbols 에 중복된 종목코드가 있습니다")
        for s in self.symbols:
            _require(bool(SYMBOL_RE.fullmatch(s)), f"종목코드 형식이 올바르지 않습니다: {s!r} (예: 005930)")
        _require(bool(self.strategy.name), "strategy.name 이 비어 있습니다")
        self.risk.validate()
        self.costs.validate()
        self.schedule.validate()
        self.backtest.validate()
        self.kis_real.validate()
        self.kis_mock.validate()

    def kis_for_mode(self, mode: str | None = None) -> KisConfig:
        """매매 모드에 해당하는 KIS 접속 설정."""
        m = mode or self.mode
        if m == "kis-live":
            return self.kis_real
        return self.kis_mock

    def kis_for_market_data(self) -> KisConfig | None:
        """시세 조회에 쓸 수 있는 KIS 설정 (실전 키 우선). 없으면 None."""
        if self.kis_real.configured:
            return self.kis_real
        if self.kis_mock.configured:
            return self.kis_mock
        return None

    def state_path(self, mode: str | None = None) -> Path:
        """모드별 상태 DB 경로 (모드끼리 장부가 섞이지 않도록 분리)."""
        return self.data_dir / f"state-{mode or self.mode}.db"

    @property
    def stop_file(self) -> Path:
        """이 파일이 존재하면 봇은 어떤 주문도 내지 않습니다 (긴급 정지)."""
        return self.data_dir / "STOP"

    def display_name(self, symbol: str) -> str:
        name = self.names.get(symbol)
        return f"{name}({symbol})" if name else symbol


# --------------------------------------------------------------------------- #
# 로딩
# --------------------------------------------------------------------------- #
def load_config(
    path: str | os.PathLike[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    env_file: str | os.PathLike[str] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> Config:
    """TOML + 환경변수(.env)에서 설정을 읽어 검증된 Config 를 반환합니다.

    path       : config.toml 경로. None 이면 현재 폴더의 config.toml (없으면 ConfigError).
    env        : 환경변수 매핑 (테스트용). None 이면 os.environ + .env 파일.
    env_file   : .env 경로. None 이면 config.toml 과 같은 폴더의 .env (없으면 무시).
    overrides  : {"mode": "kis-mock", "strategy.name": "sma_cross", "risk.capital": 5e6, ...}
                 처럼 점(.) 경로로 TOML 값을 덮어씁니다 (CLI 옵션용).
                 최상위 키 "mode"/"data_dir"/"log_level" 은 general.* 의 줄임입니다.
    """
    cfg_path = Path(path) if path is not None else Path("config.toml")
    if not cfg_path.is_file():
        raise ConfigError(
            f"설정 파일을 찾을 수 없습니다: {cfg_path}\n"
            "  → 'python -m autotrader init' 으로 기본 설정 파일을 만들 수 있습니다."
        )
    try:
        with cfg_path.open("rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"설정 파일 문법 오류 ({cfg_path}): {e}") from e

    if env is None:
        merged_env: dict[str, str] = {}
        dotenv_path = Path(env_file) if env_file is not None else cfg_path.parent / ".env"
        if dotenv_path.is_file():
            merged_env.update(parse_dotenv(dotenv_path.read_text(encoding="utf-8")))
        merged_env.update(os.environ)  # 실제 환경변수가 .env 보다 우선
        env = merged_env

    return build_config(raw, env=env, base_dir=cfg_path.parent, overrides=overrides)


def build_config(
    raw: Mapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
    base_dir: Path | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> Config:
    """파싱된 TOML dict 로부터 Config 를 만듭니다 (테스트에서 직접 호출 가능)."""
    env = env or {}
    data = _deep_copy(raw)
    for key, value in (overrides or {}).items():
        if value is None:
            continue
        dotted = key if "." in key else f"general.{key}"
        _set_dotted(data, dotted, value)

    known_sections = {
        "general", "universe", "strategy", "risk", "costs", "schedule", "backtest", "kis", "live", "notify",
    }
    unknown = set(data) - known_sections
    if unknown:
        raise ConfigError(f"알 수 없는 설정 섹션: {sorted(unknown)} (사용 가능: {sorted(known_sections)})")

    general = _section(data, "general")
    universe = _section(data, "universe")
    strategy = _section(data, "strategy")
    kis = _section(data, "kis")
    live = _section(data, "live")

    _check_keys("general", general, {"mode", "data_dir", "log_level"})
    _check_keys("universe", universe, {"symbols", "names"})
    _check_keys("strategy", strategy, {"name", "params"})
    _check_keys("live", live, {"enabled"})
    kis_keys = {"max_calls_per_sec", "order_style", "limit_ticks", "fill_timeout_sec"}
    _check_keys("kis", kis, kis_keys)
    _check_keys("notify", _section(data, "notify"), set())  # 알림 설정은 전부 환경변수(.env)

    data_dir = Path(str(general.get("data_dir", "data")))
    if not data_dir.is_absolute() and base_dir is not None:
        data_dir = base_dir / data_dir

    symbols = universe.get("symbols", [])
    if not isinstance(symbols, (list, tuple)):
        raise ConfigError("universe.symbols 는 목록이어야 합니다. 예: symbols = [\"005930\", \"000660\"]")
    names = universe.get("names", {})
    if not isinstance(names, Mapping):
        raise ConfigError("universe.names 는 표(table)여야 합니다")

    params = strategy.get("params", {})
    if not isinstance(params, Mapping):
        raise ConfigError("strategy.params 는 표(table)여야 합니다")

    kis_common = {k: kis[k] for k in kis_keys if k in kis}
    real_no, real_prod = _split_account(env.get("KIS_ACCOUNT", ""), "KIS_ACCOUNT")
    mock_no, mock_prod = _split_account(env.get("KIS_MOCK_ACCOUNT", ""), "KIS_MOCK_ACCOUNT")

    try:
        cfg = Config(
            mode=str(general.get("mode", "paper")),
            data_dir=data_dir,
            log_level=str(general.get("log_level", "INFO")).upper(),
            symbols=tuple(str(s).strip().upper() for s in symbols),
            names={str(k).strip().upper(): str(v) for k, v in names.items()},
            live_enabled=bool(live.get("enabled", False)),
            strategy=StrategyConfig(name=str(strategy.get("name", StrategyConfig.name)), params=dict(params)),
            risk=_make(RiskConfig, _section(data, "risk"), "risk"),
            costs=_make(CostConfig, _section(data, "costs"), "costs"),
            schedule=_make(ScheduleConfig, _section(data, "schedule"), "schedule"),
            backtest=_make(BacktestConfig, _section(data, "backtest"), "backtest"),
            kis_real=_make(
                KisConfig,
                {
                    **kis_common,
                    "app_key": env.get("KIS_APP_KEY", "").strip(),
                    "app_secret": env.get("KIS_APP_SECRET", "").strip(),
                    "account_no": real_no,
                    "account_product": real_prod,
                    "mock": False,
                },
                "kis",
            ),
            kis_mock=_make(
                KisConfig,
                {
                    **kis_common,
                    "app_key": env.get("KIS_MOCK_APP_KEY", "").strip(),
                    "app_secret": env.get("KIS_MOCK_APP_SECRET", "").strip(),
                    "account_no": mock_no,
                    "account_product": mock_prod,
                    "mock": True,
                },
                "kis",
            ),
            notify=NotifyConfig(
                telegram_token=env.get("TELEGRAM_BOT_TOKEN", "").strip(),
                telegram_chat_id=env.get("TELEGRAM_CHAT_ID", "").strip(),
                webhook_url=env.get("NOTIFY_WEBHOOK_URL", "").strip(),
            ),
        )
    except (TypeError, ValueError) as e:
        if isinstance(e, ConfigError):
            raise
        raise ConfigError(f"설정 값 형식 오류: {e}") from e

    cfg.validate()
    return cfg


# --------------------------------------------------------------------------- #
# 도우미
# --------------------------------------------------------------------------- #
def parse_dotenv(text: str) -> dict[str, str]:
    """아주 단순한 .env 파서: KEY=VALUE, # 주석, 따옴표 제거."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key:
            out[key] = value
    return out


def parse_date(s: str, what: str = "날짜") -> date:
    try:
        return date.fromisoformat(str(s).strip())
    except ValueError as e:
        raise ConfigError(f"{what} 형식이 올바르지 않습니다: {s!r} (예: 2024-01-31)") from e


def parse_hhmm(s: str, what: str = "시각") -> time:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", str(s).strip())
    if not m:
        raise ConfigError(f"{what} 형식이 올바르지 않습니다: {s!r} (예: 15:15)")
    hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        raise ConfigError(f"{what} 값이 범위를 벗어났습니다: {s!r}")
    return time(hh, mm, ss)


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ConfigError(message)


def _section(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    sec = data.get(name, {})
    if not isinstance(sec, Mapping):
        raise ConfigError(f"[{name}] 는 섹션(table)이어야 합니다")
    return sec


def _check_keys(section: str, values: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = set(values) - allowed
    if unknown:
        hint = f" (사용 가능: {sorted(allowed)})" if allowed else " (이 섹션의 값은 .env 파일에 설정합니다)"
        raise ConfigError(f"[{section}] 에 알 수 없는 항목: {sorted(unknown)}{hint}")


def _make(cls: type, values: Mapping[str, Any], section: str) -> Any:
    """dict → dataclass. 모르는 키는 오류, 숫자 타입은 기본값의 타입에 맞춰 변환."""
    allowed = {f.name: f for f in fields(cls)}
    _check_keys(section, values, set(allowed))
    kwargs: dict[str, Any] = {}
    for key, value in values.items():
        default = allowed[key].default
        try:
            if isinstance(default, bool):
                if not isinstance(value, bool):
                    raise TypeError("true/false 여야 합니다")
                kwargs[key] = value
            elif isinstance(default, int):
                if isinstance(value, bool) or (isinstance(value, float) and value != int(value)):
                    raise TypeError("정수여야 합니다")
                kwargs[key] = int(value)
            elif isinstance(default, float):
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError("숫자여야 합니다")
                kwargs[key] = float(value)
            elif isinstance(default, str):
                kwargs[key] = str(value)
            else:
                kwargs[key] = value
        except (TypeError, ValueError) as e:
            raise ConfigError(f"{section}.{key} 값이 올바르지 않습니다 ({value!r}): {e}") from e
    return cls(**kwargs)


def _split_account(value: str, what: str) -> tuple[str, str]:
    """'12345678-01' 또는 '1234567801' → ('12345678', '01')."""
    v = value.strip().replace(" ", "")
    if not v:
        return "", "01"
    m = re.fullmatch(r"(\d{8})-?(\d{2})", v)
    if not m:
        raise ConfigError(f"{what} 형식이 올바르지 않습니다. 계좌번호 10자리를 12345678-01 형식으로 넣어 주세요.")
    return m.group(1), m.group(2)


def _deep_copy(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return {k: _deep_copy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_copy(v) for v in obj]
    return obj


def _set_dotted(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = data
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value

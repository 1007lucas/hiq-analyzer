"""부품 조립: 설정(Config)으로부터 전략·브로커·시세·코어·매매 루프를 만듭니다."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .brokers.base import Broker, BrokerError, MarketData
from .brokers.kis import KisClient
from .brokers.paper import PaperBroker
from .config import Config
from .core import TradingCore
from .data.providers import NaverMarketData
from .live.trader import MODE_LABELS, Clock, LiveTrader
from .market_calendar import MarketCalendar
from .models import KST
from .notify import Notifier
from .state import SqliteStore, StateStore
from .strategies import create_strategy
from .strategies.base import Strategy


class SetupError(Exception):
    """실행 준비 실패. 메시지는 사용자에게 그대로 보여 줄 한국어 문장입니다."""


@dataclass
class Services:
    broker: Broker
    market: MarketData
    broker_label: str
    market_label: str


def _kst_formatter(fmt: str, datefmt: str) -> logging.Formatter:
    """PC 의 시간대 설정과 무관하게 한국 시각으로 찍는 로그 형식."""
    f = logging.Formatter(fmt, datefmt)
    f.converter = lambda seconds: datetime.fromtimestamp(seconds, KST).timetuple()  # type: ignore[assignment]
    return f


def setup_logging(cfg: Config, *, to_file: bool = True) -> None:
    """콘솔(+파일) 로그 설정. 여러 번 불러도 핸들러가 중복되지 않습니다."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")      # 한글 Windows 콘솔에서 이모지 때문에 죽지 않게
        except (AttributeError, ValueError):
            pass
    root = logging.getLogger("autotrader")
    root.setLevel(getattr(logging, cfg.log_level, logging.INFO))
    root.propagate = False
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_kst_formatter("%(asctime)s  %(message)s", "%m-%d %H:%M:%S"))
    root.addHandler(console)
    if to_file:
        try:
            log_dir = cfg.data_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(
                log_dir / "autotrader.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
            )
            fh.setFormatter(_kst_formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
            root.addHandler(fh)
        except OSError as e:
            root.warning("로그 파일을 만들 수 없어 화면에만 기록합니다: %s", e)


def build_strategy(cfg: Config) -> Strategy:
    try:
        return create_strategy(cfg.strategy.name, cfg.strategy.params)
    except ValueError as e:
        raise SetupError(f"전략 설정 오류: {e}") from None


def build_calendar(cfg: Config) -> MarketCalendar:
    return MarketCalendar(extra_holidays=cfg.schedule.extra_holiday_dates)


def _kis(cfg: Config, *, mock: bool) -> KisClient:
    try:
        return KisClient(cfg.kis_mock if mock else cfg.kis_real, token_dir=cfg.data_dir)
    except BrokerError as e:
        raise SetupError(str(e)) from None


def market_data_for(cfg: Config) -> MarketData | None:
    """시세·일봉 조회에 쓸 KIS 클라이언트 (실전 키 우선). 키가 없으면 None."""
    k = cfg.kis_for_market_data()
    if k is None:
        return None
    return _kis(cfg, mock=k.mock)


def build_services(cfg: Config, mode: str) -> Services:
    """모드에 맞는 주문 브로커와 시세 출처를 만듭니다."""
    if mode == "paper":
        broker: Broker = PaperBroker(cfg.costs.slippage_rate)
        market = market_data_for(cfg)
        if market is not None:
            which = "모의투자" if getattr(market, "mock", False) else "실전"
            return Services(broker, market, "가상 체결 (실제 주문 없음)", f"한국투자증권 시세 ({which} 키)")
        return Services(broker, NaverMarketData(), "가상 체결 (실제 주문 없음)", "네이버 금융 시세 (비공식)")
    if mode == "kis-mock":
        mock_client = _kis(cfg, mock=True)
        if cfg.kis_real.configured:
            # 시세·휴장일은 실전 서버가 더 빠르고 정확 (주문은 모의 계좌로만 나감)
            return Services(mock_client, _kis(cfg, mock=False), "한국투자증권 모의투자 계좌", "한국투자증권 시세 (실전 키)")
        return Services(mock_client, mock_client, "한국투자증권 모의투자 계좌", "한국투자증권 시세 (모의투자 키)")
    if mode == "kis-live":
        if not cfg.live_enabled:
            raise SetupError(
                "실전 매매가 허용되어 있지 않습니다.\n"
                "  실전 계좌로 매매하려면 config.toml 의 [live] 섹션에서 enabled = true 로 바꿔야 합니다.\n"
                "  그 전에 백테스트 → 페이퍼(paper) → 모의투자(kis-mock) 순서로 충분히 확인하세요."
            )
        client = _kis(cfg, mock=False)
        return Services(client, client, "한국투자증권 실전 계좌", "한국투자증권 시세 (실전 키)")
    raise SetupError(f"알 수 없는 모드: {mode}")


def build_core(
    cfg: Config,
    *,
    strategy: Strategy,
    broker: Broker,
    store: StateStore,
    notifier: Notifier | None = None,
    clock: Clock | None = None,
) -> TradingCore:
    return TradingCore(
        strategy=strategy,
        universe=cfg.symbols,
        risk=cfg.risk,
        costs=cfg.costs,
        broker=broker,
        store=store,
        clock=clock.now if clock is not None else None,
        notify=notifier.send if notifier is not None else None,
        kill_switch=cfg.stop_file.exists,
        name_of=cfg.display_name,
    )


def open_store(cfg: Config, mode: str) -> SqliteStore:
    path: Path = cfg.state_path(mode)
    try:
        return SqliteStore(path)
    except OSError as e:
        raise SetupError(f"상태 파일을 열 수 없습니다 ({path}): {e}") from None


def build_trader(
    cfg: Config,
    mode: str,
    *,
    services: Services,
    core: TradingCore,
    notifier: Notifier | None = None,
    clock: Clock | None = None,
    lock=None,
) -> LiveTrader:
    return LiveTrader(
        core=core,
        market=services.market,
        broker=services.broker,
        calendar=build_calendar(cfg),
        schedule=cfg.schedule,
        mode=mode,
        data_dir=cfg.data_dir,
        clock=clock,
        notify=notifier.send if notifier is not None else None,
        kill_switch=cfg.stop_file.exists,
        lock=lock,
    )


def mode_label(mode: str) -> str:
    return MODE_LABELS.get(mode, mode)

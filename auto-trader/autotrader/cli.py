"""명령줄 인터페이스.

    python -m autotrader <명령> [옵션]

명령: init, strategies, doctor, backtest, run, status, stop, resume, liquidate, forget, dashboard
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

from . import __version__
from .app import (
    SetupError,
    build_calendar,
    build_core,
    build_services,
    build_strategy,
    build_trader,
    market_data_for,
    mode_label,
    open_store,
    setup_logging,
)
from .brokers.kis import KisClient
from .brokers.paper import PaperBroker
from .config import MODES, Config, ConfigError, load_config, parse_date
from .control import AlreadyRunning, BotLock, enqueue_command, is_running, set_stop
from .core import snapshot_from_state
from .models import now_kst
from .notify import Notifier
from .state import SqliteStore
from .strategies import available_strategies, create_strategy
from .templates import CONFIG_TOML, DOTENV

LIVE_CONFIRM_WORD = "실전매매"


class CliError(Exception):
    """사용자에게 보여 줄 오류 (스택 추적 없이 메시지만 출력)."""


def _out(text: str = "") -> None:
    print(text, flush=True)


# --------------------------------------------------------------------------- #
# 공통
# --------------------------------------------------------------------------- #
def _load(args: argparse.Namespace, **overrides: Any) -> Config:
    ov = {k: v for k, v in overrides.items() if v is not None}
    if getattr(args, "mode", None):
        ov["mode"] = args.mode
    try:
        return load_config(args.config, overrides=ov)
    except ConfigError as e:
        raise CliError(f"설정 오류: {e}") from None


def _parse_params(items: Sequence[str] | None) -> dict[str, Any]:
    """--param k=v 목록을 dict 로. 값은 true/false, 정수, 실수, 문자열 순으로 해석합니다."""
    out: dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise CliError(f"--param 형식이 올바르지 않습니다: {item!r} (예: --param fast=5)")
        k, v = item.split("=", 1)
        k, v = k.strip(), v.strip()
        if v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
            continue
        try:
            out[k] = int(v)
        except ValueError:
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
    return out


def _won(x: float) -> str:
    return f"{x:,.0f}원"


def _pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


# --------------------------------------------------------------------------- #
# init / strategies
# --------------------------------------------------------------------------- #
def cmd_init(args: argparse.Namespace) -> int:
    base = Path(args.config).resolve().parent
    cfg_path = Path(args.config)
    env_path = base / ".env"
    base.mkdir(parents=True, exist_ok=True)
    for path, text, what in ((cfg_path, CONFIG_TOML, "설정 파일"), (env_path, DOTENV, "비밀 값 파일")):
        if path.exists():
            _out(f"· {what}이 이미 있어 그대로 둡니다: {path}")
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
            _out(f"· {what}을 만들었습니다: {path}")
    _out()
    _out("다음 순서로 진행하세요.")
    _out("  1) python -m autotrader backtest --source synthetic   ← 연습용 가짜 데이터로 기능 체험")
    _out("  2) python -m autotrader backtest                      ← 실제 과거 시세로 전략 검증")
    _out("  3) python -m autotrader run                           ← 가상 매매(paper)로 며칠 지켜보기")
    _out("  4) .env 에 모의투자 키를 넣고  python -m autotrader run --mode kis-mock")
    _out("자세한 설명은 README.md 를 참고하세요.")
    return 0


def cmd_strategies(args: argparse.Namespace) -> int:
    _out("사용 가능한 전략 (config.toml 의 [strategy] name 에 적는 이름)")
    _out()
    for name, desc, defaults in available_strategies():
        params = ", ".join(f"{k}={v!r}" for k, v in defaults.items()) or "(없음)"
        _out(f"  {name}")
        _out(f"      {desc}")
        _out(f"      기본 파라미터: {params}")
    return 0


# --------------------------------------------------------------------------- #
# backtest
# --------------------------------------------------------------------------- #
def cmd_backtest(args: argparse.Namespace) -> int:
    from .backtest import format_metrics, run_backtest, write_html_report, write_trades_csv
    from .data import DataError, load_bars

    cfg = _load(args)
    setup_logging(cfg, to_file=False)
    logging.getLogger("autotrader.core").setLevel(logging.WARNING)   # 백테스트의 매매 한 건 한 건은 화면에 찍지 않음
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] if args.symbols else list(cfg.symbols)
    source = args.source or cfg.backtest.data_source
    start = parse_date(args.start or cfg.backtest.start, "시작일")
    end = parse_date(args.end, "종료일") if args.end else (parse_date(cfg.backtest.end, "종료일") if cfg.backtest.end else now_kst().date())
    if end < start:
        raise CliError(f"기간이 올바르지 않습니다: {start} ~ {end}")
    risk = cfg.risk
    if args.capital:
        from dataclasses import replace

        risk = replace(risk, capital=float(args.capital))
        risk.validate()

    names_params: list[tuple[str, dict[str, Any]]]
    if args.compare:
        names_params = [(name, {}) for name, _, _ in available_strategies()]
    else:
        name = args.strategy or cfg.strategy.name
        params = dict(cfg.strategy.params) if name == cfg.strategy.name else {}
        params.update(_parse_params(args.param))
        names_params = [(name, params)]
    try:
        strategies = [create_strategy(n, p) for n, p in names_params]
    except ValueError as e:
        raise CliError(f"전략 설정 오류: {e}") from None

    # 전략이 첫날부터 판단할 수 있도록 시작일 이전의 일봉도 함께 받습니다.
    warmup = max(s.warmup for s in strategies)
    fetch_start = start - timedelta(days=int(warmup * 1.6) + 30)
    kis = None
    if source in ("auto", "kis"):
        try:
            kis = market_data_for(cfg)
        except SetupError as e:
            raise CliError(str(e)) from None
    _out(f"데이터 준비 중… (출처: {source}, 종목 {len(symbols)}개, {fetch_start} ~ {end})")
    try:
        data, used = load_bars(
            symbols,
            fetch_start,
            end,
            source=source,
            cache_dir=cfg.data_dir / "cache",
            kis=kis,
            csv_dir=Path(args.csv_dir) if args.csv_dir else cfg.data_dir / "csv",
            refresh=args.refresh,
            progress=lambda sym, i, n: _out(f"  [{i}/{n}] {cfg.display_name(sym)}"),
        )
    except DataError as e:
        raise CliError(str(e)) from None
    sources = sorted(set(used.values()))
    if "synthetic" in sources:
        _out()
        _out("※ 연습용 가짜 데이터(synthetic)입니다. 실제 시세가 아니므로 아래 수익률은 아무 의미가 없습니다.")

    results = []
    for strat in strategies:
        try:
            res = run_backtest(
                data=data, strategy=strat, risk=risk, costs=cfg.costs, start=start, end=end,
                universe=symbols, names={s: cfg.names[s] for s in symbols if s in cfg.names},
            )
        except ValueError as e:
            raise CliError(f"백테스트 실패 ({strat.name}): {e}") from None
        results.append(res)

    _out()
    if args.compare:
        _out(f"전략 비교 ({results[0].start} ~ {results[0].end}, 초기 자금 {_won(risk.capital)}, 각 전략 기본 파라미터)")
        _out()
        _out(f"  {'전략':<22}{'총수익률':>10}{'CAGR':>10}{'MDD':>10}{'샤프':>8}{'거래':>7}{'승률':>9}")
        for res in results:
            m = res.metrics
            _out(
                f"  {res.strategy_name:<24}{_pct(m.total_return):>10}{_pct(m.cagr):>10}{m.max_drawdown * 100:>9.2f}%"
                f"{m.sharpe:>8.2f}{m.num_trades:>7d}{m.win_rate * 100:>8.1f}%"
            )
        b = results[0].metrics
        _out(f"  {'(단순보유)':<21}{_pct(b.benchmark_return):>10}{_pct(b.benchmark_cagr):>10}{b.benchmark_max_drawdown * 100:>9.2f}%")
        _out()
        _out("※ 과거에 가장 좋았던 전략이 앞으로도 좋다는 보장은 없습니다. 수익률보다 최대낙폭(MDD)을 먼저 보세요.")
        return 0

    res = results[0]
    params = ", ".join(f"{k}={v}" for k, v in res.strategy_params.items())
    _out(f"백테스트 결과 — 전략 {res.strategy_name} ({params})")
    _out(f"데이터 출처: {', '.join(sources)}")
    _out()
    _out(format_metrics(res.metrics))
    _out()
    if not args.no_report:
        stamp = now_kst().strftime("%Y%m%d-%H%M%S")
        out = Path(args.report) if args.report else cfg.data_dir.parent / "reports" / f"backtest-{res.strategy_name}-{stamp}.html"
        html_path = write_html_report(res, out)
        csv_path = write_trades_csv(res, out.with_suffix(".csv"))
        _out(f"리포트: {html_path}   (브라우저로 열어 보세요)")
        _out(f"거래 내역: {csv_path}")
    _out()
    _out("※ 과거 성과는 미래 수익을 보장하지 않습니다. 백테스트는 일봉 기준의 근사이며 실제 체결과 다를 수 있습니다.")
    return 0


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def _confirm_live(cfg: Config, args: argparse.Namespace, input_fn: Callable[[str], str]) -> None:
    _out("=" * 62)
    _out("  ⚠️  실전 계좌로 자동매매를 시작합니다. 실제 돈으로 주문이 나갑니다.")
    _out(f"     운용자금 한도: {_won(cfg.risk.capital)}   종목: {', '.join(cfg.symbols)}")
    _out("     손실이 날 수 있으며, 그 책임은 사용자 본인에게 있습니다.")
    _out("=" * 62)
    if args.i_understand:
        _out("(--i-understand 옵션으로 확인 절차를 생략했습니다)")
        return
    try:
        answer = input_fn(f"계속하려면 '{LIVE_CONFIRM_WORD}' 라고 입력하세요: ").strip()
    except EOFError:
        answer = ""
    if answer != LIVE_CONFIRM_WORD:
        raise CliError("실전 매매를 시작하지 않았습니다.")


def cmd_run(args: argparse.Namespace, input_fn: Callable[[str], str] = input) -> int:
    cfg = _load(args)
    mode = cfg.mode
    setup_logging(cfg)
    try:
        strategy = build_strategy(cfg)
        services = build_services(cfg, mode)
    except SetupError as e:
        raise CliError(str(e)) from None
    if mode == "kis-live":
        _confirm_live(cfg, args, input_fn)

    _out(f"모드      : {mode_label(mode)}")
    _out(f"주문      : {services.broker_label}")
    _out(f"시세      : {services.market_label}")
    _out(f"전략      : {strategy.name} {dict(strategy.params)}")
    _out(f"종목      : {', '.join(cfg.display_name(s) for s in cfg.symbols)}")
    r = cfg.risk
    _out(
        f"리스크    : 운용자금 {_won(r.capital)}, 최대 {r.max_positions}종목 × {r.position_pct:.0%}, "
        f"손절 {r.stop_loss_pct:.1%}, 일일 손실 한도 {r.daily_loss_limit_pct:.1%}"
    )
    if cfg.stop_file.exists():
        _out("※ 긴급 정지(STOP) 상태입니다. 'python -m autotrader resume' 전까지 주문을 내지 않습니다.")
    _out("종료하려면 Ctrl+C 를 누르세요. (봇을 끄면 손절 감시도 멈춥니다)")
    _out()

    lock = BotLock(cfg.data_dir, mode)
    try:
        lock.acquire()
    except AlreadyRunning as e:
        raise CliError(str(e)) from None
    notifier = Notifier(cfg.notify, prefix=f"[{mode_label(mode)}] ")
    store = None
    try:
        store = open_store(cfg, mode)
        core = build_core(cfg, strategy=strategy, broker=services.broker, store=store, notifier=notifier)
        trader = build_trader(cfg, mode, services=services, core=core, notifier=notifier, lock=lock)
        trader.run(max_days=args.days)
    except SetupError as e:
        raise CliError(str(e)) from None
    except KeyboardInterrupt:
        _out()
        _out("사용자 요청으로 종료합니다. 보유 종목은 그대로 남아 있으며, 봇이 꺼져 있는 동안에는 손절도 동작하지 않습니다.")
        notifier.send("⏹ 자동매매 봇이 종료되었습니다 (사용자 중지). 봇이 꺼져 있는 동안에는 손절도 동작하지 않습니다.")
    finally:
        notifier.close()
        if store is not None:
            store.close()
        lock.release()
    return 0


# --------------------------------------------------------------------------- #
# status / stop / resume / liquidate / forget
# --------------------------------------------------------------------------- #
def _read_state(cfg: Config, mode: str) -> tuple[dict | None, list[dict]]:
    path = cfg.state_path(mode)
    if not path.is_file():
        return None, []
    store = SqliteStore(path, read_only=True)
    try:
        return store.load_state(), store.orders(limit=8)
    finally:
        store.close()


def cmd_status(args: argparse.Namespace) -> int:
    cfg = _load(args)
    mode = cfg.mode
    running = is_running(cfg.data_dir, mode)
    _out(f"모드: {mode_label(mode)}   봇: {'실행 중' if running else '꺼져 있음'}"
         f"{'   ⏸ 긴급 정지(STOP) 상태' if cfg.stop_file.exists() else ''}")
    try:
        state, orders = _read_state(cfg, mode)
    except Exception as e:  # noqa: BLE001 - 상태 파일이 손상돼도 메시지로 안내
        raise CliError(f"상태 파일을 읽을 수 없습니다: {e}") from None
    if not state:
        _out("아직 이 모드로 봇을 실행한 기록이 없습니다.")
        return 0
    snap = snapshot_from_state(state, risk=cfg.risk, name_of=cfg.display_name)
    _out(f"기록 시각: {state.get('saved_at', '')}   전략: {snap['strategy']} {snap['strategy_params']}")
    _out()
    _out(f"봇 평가금 : {_won(snap['equity'])}  (누적 {_pct(snap['total_return'])}, 오늘 {_pct(snap['day_return'])})")
    _out(f"현금      : {_won(snap['cash'])}   주식 평가액: {_won(snap['positions_value'])}")
    if snap["halted"]:
        _out("⛔ 최대 낙폭 한도 초과로 신규 매수가 중단된 상태입니다 → 'resume' 명령으로 해제")
    if snap["entries_halted_today"]:
        _out("⛔ 오늘 일일 손실 한도에 도달해 신규 매수를 중단했습니다")
    _out()
    if snap["positions"]:
        _out("보유 종목")
        for p in snap["positions"]:
            stop = f"손절가 {p['stop']:,.0f}" if p["stop"] > 0 else "손절 없음"
            _out(f"  {p['name']:<16} {p['qty']:>6,}주  평단 {p['avg_price']:>10,.0f}  현재 {p['price']:>10,.0f}  "
                 f"{_pct(p['pnl_pct'])} ({p['pnl']:+,.0f}원)  {stop}")
    else:
        _out("보유 종목 없음")
    plans = [p for p in snap["plans"] if p["entry"] or p["exit"] or p["note"]]
    if plans:
        _out()
        _out(f"오늘({snap['day']})의 계획")
        labels = {"open": "시가", "breakout": "돌파", "close": "종가", "": "-"}
        for p in plans:
            target = f" 목표가 {p['breakout_target']:,.0f}" if p["breakout_target"] > 0 else ""
            _out(f"  {p['name']:<16} 진입: {labels[p['entry']]}{target}  청산: {labels[p['exit']]}  {p['entry_note'] or p['exit_note'] or p['note']}")
    if orders:
        _out()
        _out("최근 주문")
        for o in orders[::-1]:
            side = "매도" if o["side"] == "sell" else "매수"
            pnl = f"  손익 {o['pnl']:+,.0f}원" if o.get("pnl") is not None else ""
            _out(f"  {str(o['ts'])[:19]}  {cfg.display_name(o['symbol']):<16} {side} {o['filled_qty'] or 0}/{o['qty']}주 "
                 f"@ {o['price'] or 0:,.0f}  [{o['status']}]{pnl}  {o['reason']}")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    cfg = _load(args)
    p = set_stop(cfg.data_dir, True)
    _out(f"⏸ 긴급 정지를 걸었습니다 ({p}).")
    _out("  이 상태에서는 모든 모드의 봇이 어떤 주문도 내지 않습니다 (손절 포함).")
    _out("  보유 종목을 팔려면 증권사 앱을 쓰거나, 봇이 실행 중일 때 'liquidate' 명령을 쓰세요.")
    _out("  다시 매매하려면: python -m autotrader resume")
    return 0


def _offline_core(cfg: Config, mode: str):
    """봇이 꺼져 있을 때 장부만 고치기 위한 코어 (주문은 나가지 않음)."""
    if not cfg.state_path(mode).is_file():
        raise CliError("아직 이 모드로 봇을 실행한 기록이 없습니다.")
    try:
        store = open_store(cfg, mode)
        core = build_core(cfg, strategy=build_strategy(cfg), broker=PaperBroker(), store=store)
    except SetupError as e:
        raise CliError(str(e)) from None
    return core, store


def cmd_resume(args: argparse.Namespace) -> int:
    cfg = _load(args)
    mode = cfg.mode
    set_stop(cfg.data_dir, False)
    _out("▶️ 긴급 정지(STOP)를 해제했습니다.")
    if is_running(cfg.data_dir, mode):
        enqueue_command(cfg.data_dir, mode, "resume")
        _out("  실행 중인 봇에 '신규 매수 중단 해제'를 요청했습니다 (수십 초 안에 반영).")
    elif cfg.state_path(mode).is_file():
        core, store = _offline_core(cfg, mode)
        try:
            if core.halted:
                core.resume()
                _out("  최대 낙폭 한도로 걸린 신규 매수 중단도 해제했습니다.")
        finally:
            store.close()
    return 0


def cmd_liquidate(args: argparse.Namespace, input_fn: Callable[[str], str] = input) -> int:
    cfg = _load(args)
    mode = cfg.mode
    if not is_running(cfg.data_dir, mode):
        raise CliError(
            "봇이 실행 중이 아닙니다. 자동 청산은 봇이 실행 중인 장중에만 할 수 있습니다.\n"
            "  지금 바로 팔아야 한다면 증권사 앱에서 직접 매도한 뒤 'forget' 명령으로 봇 장부를 정리하세요."
        )
    if not args.yes:
        try:
            answer = input_fn(f"[{mode_label(mode)}] 봇이 보유한 종목을 모두 시장가로 팔고 정지합니다. 진행할까요? (y/N) ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes", "예"):
            _out("취소했습니다.")
            return 1
    enqueue_command(cfg.data_dir, mode, "liquidate")
    _out("실행 중인 봇에 전량 청산을 요청했습니다 (수십 초 안에 처리). 결과는 'status' 명령이나 알림으로 확인하세요.")
    return 0


def cmd_forget(args: argparse.Namespace) -> int:
    cfg = _load(args)
    mode = cfg.mode
    symbol = args.symbol.strip().upper()
    if args.qty is not None and args.qty < 1:
        raise CliError("--qty 는 1 이상이어야 합니다")
    if args.price is not None and args.price <= 0:
        raise CliError("--price 는 0보다 커야 합니다")
    if is_running(cfg.data_dir, mode):
        enqueue_command(cfg.data_dir, mode, "forget", symbol=symbol, qty=args.qty, price=args.price)
        _out(f"실행 중인 봇에 {symbol} 장부 정리를 요청했습니다 (수십 초 안에 처리).")
        return 0
    core, store = _offline_core(cfg, mode)
    try:
        ok = core.forget_position(symbol, qty=args.qty, price=args.price, reason="사용자 요청으로 장부 정리")
    finally:
        store.close()
    if not ok:
        raise CliError(f"봇 장부에 {symbol} 포지션이 없거나 정산 가격을 알 수 없습니다 (--price 로 판 가격을 알려 주세요).")
    _out(f"{symbol} 을(를) 봇 장부에서 정리했습니다. (실제 주문은 나가지 않았습니다)")
    return 0


# --------------------------------------------------------------------------- #
# doctor / dashboard
# --------------------------------------------------------------------------- #
def cmd_doctor(args: argparse.Namespace) -> int:
    problems = 0

    def row(ok: bool | None, what: str, detail: str = "") -> None:
        nonlocal problems
        mark = {True: "✅", False: "❌", None: "➖"}[ok]
        if ok is False:
            problems += 1
        _out(f"  {mark} {what}{': ' + detail if detail else ''}")

    _out(f"autotrader {__version__} 점검")
    row(sys.version_info >= (3, 11), "파이썬 버전", sys.version.split()[0] + (" (3.11 이상 필요)" if sys.version_info < (3, 11) else ""))
    try:
        cfg = _load(args)
    except CliError as e:
        row(False, "설정 파일", str(e))
        return 1
    row(True, "설정 파일", f"{args.config} (모드: {mode_label(cfg.mode)})")
    try:
        strategy = build_strategy(cfg)
        row(True, "전략", f"{strategy.name} {dict(strategy.params)} — 필요한 일봉 {strategy.warmup}개")
    except SetupError as e:
        row(False, "전략", str(e))
    try:
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        probe = cfg.data_dir / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        row(True, "데이터 폴더", str(cfg.data_dir))
    except OSError as e:
        row(False, "데이터 폴더", f"{cfg.data_dir} 에 쓸 수 없습니다 ({e})")
    r = cfg.risk
    if r.max_positions * r.position_pct > 1.0 + 1e-9:
        row(None, "자금 배분", f"max_positions × position_pct = {r.max_positions * r.position_pct:.0%} — 현금이 모자라 일부 종목은 매수되지 않을 수 있습니다")
    if r.stop_loss_pct == 0 and r.trailing_stop_pct == 0:
        row(None, "손절", "손절이 꺼져 있습니다 (stop_loss_pct = 0). 큰 손실에 대한 안전장치가 없습니다.")
    today = now_kst().date()
    cal = build_calendar(cfg)
    if not cal.is_covered(today) or not cal.is_covered(today + timedelta(days=60)):
        row(None, "휴장일 달력", "내장 달력에 없는 연도가 다가옵니다. 프로그램을 업데이트하거나 [schedule] extra_holidays 에 휴장일을 추가하세요.")
    else:
        row(True, "휴장일 달력", f"다음 거래일 {cal.next_trading_day(today - timedelta(days=1))}")
    _out(f"  ➖ 현재 시각(KST): {now_kst():%Y-%m-%d %H:%M:%S} — PC 시계가 틀리면 주문 시각이 어긋납니다")
    if cfg.stop_file.exists():
        row(None, "긴급 정지", "STOP 상태입니다 ('resume' 으로 해제)")

    for label, kcfg in (("모의투자", cfg.kis_mock), ("실전", cfg.kis_real)):
        if not kcfg.configured:
            needed = (cfg.mode == "kis-mock" and kcfg.mock) or (cfg.mode == "kis-live" and not kcfg.mock)
            row(False if needed else None, f"한국투자증권 {label} 키", "설정되지 않음 (.env)" + (" — 현재 모드에 필요합니다" if needed else ""))
            continue
        if args.offline:
            row(None, f"한국투자증권 {label} 키", "설정됨 (--offline 이라 접속 점검은 생략)")
            continue
        try:
            client = KisClient(kcfg, token_dir=cfg.data_dir)
            for what, ok, detail in client.check_connection(cfg.symbols[0]):
                row(ok, f"한국투자증권 {label} — {what}", detail)
        except Exception as e:  # noqa: BLE001 - 점검 도구는 어떤 오류든 보고만
            row(False, f"한국투자증권 {label}", str(e))

    if cfg.notify.enabled:
        if args.notify_test and not args.offline:
            errors = Notifier(cfg.notify).send_now("🔔 autotrader 알림 테스트입니다.")
            row(not errors, "알림 전송", "; ".join(errors) if errors else "테스트 메시지를 보냈습니다")
        else:
            row(True, "알림", "설정됨 (--notify-test 로 실제 전송 확인)")
    else:
        row(None, "알림", "설정되지 않음 (선택 사항이지만 실전에서는 강력히 권장)")
    if cfg.mode == "kis-live" and not cfg.live_enabled:
        row(False, "실전 매매 허용", "[live] enabled = false 입니다")
    _out()
    _out("문제 없음 — 준비되었습니다." if problems == 0 else f"해결이 필요한 항목 {problems}개가 있습니다 (❌ 표시).")
    return 0 if problems == 0 else 1


def cmd_dashboard(args: argparse.Namespace) -> int:
    from .dashboard import serve

    cfg = _load(args)
    try:
        serve(cfg, cfg.mode, host=args.host, port=args.port, open_browser=not args.no_browser)
    except RuntimeError as e:
        raise CliError(str(e)) from None
    return 0


# --------------------------------------------------------------------------- #
# 진입점
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m autotrader",
        description="한국 주식 자동매매 (백테스트 / 가상 매매 / 한국투자증권 모의·실전)",
    )
    p.add_argument("--version", action="version", version=f"autotrader {__version__}")
    p.add_argument("-c", "--config", default="config.toml", help="설정 파일 경로 (기본: config.toml)")
    sub = p.add_subparsers(dest="command", metavar="<명령>")

    def add(name: str, help_: str, mode: bool = False) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.add_argument("-c", "--config", default=argparse.SUPPRESS, help="설정 파일 경로")
        if mode:
            sp.add_argument("--mode", choices=MODES, help="매매 모드 (기본: 설정 파일의 general.mode)")
        return sp

    add("init", "기본 설정 파일(config.toml, .env) 만들기")
    add("strategies", "사용 가능한 전략 목록 보기")

    d = add("doctor", "설정과 API 연결 점검", mode=True)
    d.add_argument("--offline", action="store_true", help="인터넷 접속 없이 설정만 점검")
    d.add_argument("--notify-test", action="store_true", help="알림 테스트 메시지 보내기")

    b = add("backtest", "과거 시세로 전략 검증")
    b.add_argument("--strategy", help="전략 이름 (기본: 설정 파일)")
    b.add_argument("--param", action="append", metavar="이름=값", help="전략 파라미터 (여러 번 지정 가능)")
    b.add_argument("--symbols", help="종목코드 목록 (쉼표로 구분, 기본: 설정 파일)")
    b.add_argument("--start", help="시작일 YYYY-MM-DD")
    b.add_argument("--end", help="종료일 YYYY-MM-DD (기본: 오늘)")
    b.add_argument("--source", choices=("auto", "kis", "naver", "yahoo", "csv", "synthetic"), help="데이터 출처")
    b.add_argument("--csv-dir", help="--source csv 일 때 <종목코드>.csv 가 있는 폴더 (기본: data/csv)")
    b.add_argument("--capital", type=float, help="초기 자금(원)")
    b.add_argument("--refresh", action="store_true", help="캐시를 무시하고 시세를 다시 받기")
    b.add_argument("--compare", action="store_true", help="모든 전략을 기본 파라미터로 돌려 비교")
    b.add_argument("--report", help="HTML 리포트 저장 경로")
    b.add_argument("--no-report", action="store_true", help="리포트 파일을 만들지 않음")

    r = add("run", "자동매매 시작", mode=True)
    r.add_argument("--days", type=int, help="이만큼의 거래일만 실행하고 종료 (기본: 계속 실행)")
    r.add_argument("--i-understand", action="store_true", help="실전 매매 확인 입력 생략 (무인 실행용)")

    add("status", "현재 봇 상태 보기", mode=True)
    add("stop", "긴급 정지 — 모든 주문 중단")
    add("resume", "긴급 정지 / 신규 매수 중단 해제", mode=True)
    lq = add("liquidate", "봇 보유 종목 전량 매도 후 정지 (봇 실행 중일 때)", mode=True)
    lq.add_argument("-y", "--yes", action="store_true", help="확인 질문 생략")
    f = add("forget", "봇 장부에서 종목 정리 (직접 매도했을 때)", mode=True)
    f.add_argument("symbol", help="종목코드")
    f.add_argument("--qty", type=int, help="정리할 수량 (기본: 전부)")
    f.add_argument("--price", type=float, help="실제로 판 가격 (기본: 마지막으로 알려진 가격)")

    w = add("dashboard", "웹 대시보드 열기 (조회 전용)", mode=True)
    w.add_argument("--host", default="127.0.0.1", help="접속 허용 주소 (기본: 이 PC 에서만)")
    w.add_argument("--port", type=int, default=8787, help="포트 (기본: 8787)")
    w.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    return p


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "init": cmd_init,
    "strategies": cmd_strategies,
    "doctor": cmd_doctor,
    "backtest": cmd_backtest,
    "run": cmd_run,
    "status": cmd_status,
    "stop": cmd_stop,
    "resume": cmd_resume,
    "liquidate": cmd_liquidate,
    "forget": cmd_forget,
    "dashboard": cmd_dashboard,
}


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    try:
        return COMMANDS[args.command](args)
    except CliError as e:
        print(f"\n[오류] {e}", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        print("\n중단했습니다.", file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

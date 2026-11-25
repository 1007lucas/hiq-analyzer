"""조회 전용 웹 대시보드 (이 PC 안에서만 접속).

* 상태 DB 를 **읽기 전용**으로 열어 보여 주기만 합니다. 주문·정지 같은 조작 기능은 없습니다.
* 기본적으로 127.0.0.1 에만 열립니다. Host 헤더를 검사해 다른 웹페이지가 몰래 접근하는 것
  (DNS 리바인딩)을 막고, 외부 리소스를 전혀 쓰지 않는 한 장짜리 페이지를 제공합니다.
"""

from __future__ import annotations

import ipaddress
import json
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ..config import Config
from ..control import is_running
from ..core import snapshot_from_state
from ..live.trader import MODE_LABELS
from ..models import now_kst
from ..state import SqliteStore

PAGE_PATH = Path(__file__).with_name("page.html")

CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; "
    "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
COMMON_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def build_payload(cfg: Config, mode: str | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    """대시보드에 보여 줄 모든 정보를 JSON 으로 만들 수 있는 dict 로 모읍니다. 예외를 던지지 않습니다."""
    m = mode or cfg.mode
    stamp = now or now_kst()
    path = cfg.state_path(m)
    out: dict[str, Any] = {
        "generated_at": stamp.isoformat(),
        "mode": m,
        "mode_label": MODE_LABELS.get(m, m),
        "db_exists": path.is_file(),
        "bot_running": is_running(cfg.data_dir, m),
        "stop_active": cfg.stop_file.exists(),
        "snapshot": None,
        "state_saved_at": "",
        "orders": [],
        "equity": [],
        "events": [],
        "error": "",
    }
    if not out["db_exists"]:
        return out
    try:
        store = SqliteStore(path, read_only=True)
        try:
            state = store.load_state()
            if state:
                out["snapshot"] = snapshot_from_state(state, risk=cfg.risk, name_of=cfg.display_name)
                out["state_saved_at"] = str(state.get("saved_at", ""))
            out["orders"] = [
                {**o, "name": cfg.display_name(str(o.get("symbol", "")))} for o in store.orders(limit=200)[::-1]
            ]
            out["equity"] = [{"day": d.isoformat(), "equity": e, "cash": c} for d, e, c in store.equity_history()]
            out["events"] = store.events(limit=200)[::-1]
        finally:
            store.close()
    except Exception as e:  # noqa: BLE001 - 손상·잠금 등 어떤 문제든 화면에 알리고 계속 동작
        out["error"] = f"상태 파일을 읽지 못했습니다: {e}"
    return out


def _is_loopback(host: str) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _host_only(header: str) -> str:
    """'127.0.0.1:8787' / '[::1]:8787' / 'localhost' → 포트를 뗀 호스트 이름."""
    h = header.strip().lower()
    if h.startswith("["):
        return h[1 : h.find("]")] if "]" in h else h
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


class _Handler(BaseHTTPRequestHandler):
    server_version = "autotrader-dashboard"
    sys_version = ""
    cfg: Config
    mode: str
    allowed_hosts: frozenset[str]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - 표준 시그니처
        pass                                                   # 요청마다 콘솔에 찍지 않음

    def _send(self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in {**COMMON_HEADERS, **(extra or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _text(self, status: int, text: str) -> None:
        self._send(status, text.encode("utf-8"), "text/plain; charset=utf-8")

    def _handle(self) -> None:
        if _host_only(self.headers.get("Host", "")) not in self.allowed_hosts:
            self._text(403, "허용되지 않은 Host 입니다.")
            return
        path = self.path.split("?", 1)[0]
        if path == "/":
            try:
                body = PAGE_PATH.read_bytes()
            except OSError:
                self._text(500, "대시보드 페이지 파일을 찾을 수 없습니다.")
                return
            self._send(200, body, "text/html; charset=utf-8", {"Content-Security-Policy": CSP})
        elif path == "/api/state":
            payload = build_payload(self.cfg, self.mode)
            self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif path == "/healthz":
            self._text(200, "ok")
        else:
            self._text(404, "없는 주소입니다.")

    def do_GET(self) -> None:  # noqa: N802 - http.server 규칙
        self._handle()

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle()

    def _not_allowed(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        for k, v in COMMON_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _not_allowed  # noqa: N815


def make_server(cfg: Config, mode: str | None = None, host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    allowed = frozenset({"localhost", "127.0.0.1", "::1", host.strip("[]").lower()})
    handler = type("Handler", (_Handler,), {"cfg": cfg, "mode": mode or cfg.mode, "allowed_hosts": allowed})
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as e:
        raise RuntimeError(
            f"대시보드를 열 수 없습니다 ({host}:{port}): {e}\n  → 이미 열려 있거나 다른 프로그램이 쓰는 포트입니다. --port 로 다른 번호를 지정해 보세요."
        ) from None
    server.daemon_threads = True
    return server


def serve(cfg: Config, mode: str | None = None, host: str = "127.0.0.1", port: int = 8787, open_browser: bool = False) -> None:
    """대시보드 서버를 실행합니다 (Ctrl+C 로 종료)."""
    server = make_server(cfg, mode, host, port)
    shown = "localhost" if _is_loopback(host) else host
    url = f"http://{shown}:{server.server_address[1]}/"
    print(f"대시보드 주소: {url}   (조회 전용, 종료하려면 Ctrl+C)", flush=True)
    if not _is_loopback(host):
        print(
            "⚠️  경고: 이 PC 밖에서도 접속할 수 있는 주소로 열었습니다. 같은 네트워크의 누구나 계좌 상태를 볼 수 있습니다.\n"
            "    꼭 필요한 경우가 아니면 --host 옵션 없이 실행하세요.",
            flush=True,
        )
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n대시보드를 종료합니다.", flush=True)
    finally:
        server.server_close()

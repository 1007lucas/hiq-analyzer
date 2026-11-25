"""알림 전송 (텔레그램 / 디스코드·슬랙 호환 웹훅).

매매 루프를 막지 않도록 별도 스레드에서 보냅니다. 알림 실패는 로그만 남기고 무시합니다
(알림이 안 간다고 매매가 멈추면 안 됩니다).
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .config import NotifyConfig

log = logging.getLogger("autotrader.notify")

TELEGRAM_LIMIT = 4000       # 텔레그램 메시지 최대 4096자
WEBHOOK_LIMIT = 1900        # 디스코드 메시지 최대 2000자
QUEUE_MAX = 200             # 밀린 알림이 이보다 많아지면 새 알림을 버림 (네트워크 장애 시 메모리 보호)
TIMEOUT_SEC = 8.0

Sender = Callable[[str, bytes, dict[str, str]], None]   # (url, body, headers) → None, 실패 시 예외


def _http_post(url: str, body: bytes, headers: dict[str, str]) -> None:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:  # noqa: S310 - URL 은 사용자가 설정한 https 주소
        resp.read()


def _redact(text: str, *secrets: str) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


class Notifier:
    """알림 전송기. 설정이 비어 있으면 아무것도 하지 않습니다."""

    def __init__(self, cfg: NotifyConfig, *, prefix: str = "", sender: Sender | None = None) -> None:
        self.cfg = cfg
        self.prefix = prefix
        self._sender: Sender = sender or _http_post
        self._q: queue.Queue[str | None] = queue.Queue(maxsize=QUEUE_MAX)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.cfg.enabled

    def send(self, text: str) -> None:
        """알림을 대기열에 넣습니다 (즉시 반환)."""
        if not self.enabled:
            return
        msg = f"{self.prefix}{text}" if self.prefix else text
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._worker, name="notifier", daemon=True)
                self._thread.start()
        try:
            self._q.put_nowait(msg)
        except queue.Full:
            log.warning("알림 대기열이 가득 차 알림을 버립니다")

    def send_now(self, text: str) -> list[str]:
        """알림을 지금 바로 보내고, 실패한 채널의 오류 메시지 목록을 반환합니다 (연결 테스트용)."""
        msg = f"{self.prefix}{text}" if self.prefix else text
        return self._deliver(msg)

    def close(self, timeout: float = 10.0) -> None:
        """대기 중인 알림을 마저 보내고 스레드를 종료합니다."""
        t = self._thread
        if t is None or not t.is_alive():
            return
        try:
            self._q.put(None, timeout=1.0)
        except queue.Full:
            return
        t.join(timeout)

    # ------------------------------------------------------------------ #
    def _worker(self) -> None:
        while True:
            msg = self._q.get()
            if msg is None:
                return
            for err in self._deliver(msg):
                log.warning("알림 전송 실패: %s", err)

    def _deliver(self, msg: str) -> list[str]:
        errors: list[str] = []
        c = self.cfg
        if c.telegram_token and c.telegram_chat_id:
            url = f"https://api.telegram.org/bot{c.telegram_token}/sendMessage"
            body = json.dumps(
                {"chat_id": c.telegram_chat_id, "text": msg[:TELEGRAM_LIMIT], "disable_web_page_preview": True}
            ).encode("utf-8")
            try:
                self._sender(url, body, {"Content-Type": "application/json"})
            except Exception as e:  # noqa: BLE001 - 어떤 실패든 알림만 포기
                errors.append(_redact(f"텔레그램: {e}", c.telegram_token))
        if c.webhook_url:
            text = msg[:WEBHOOK_LIMIT]
            host = urllib.parse.urlsplit(c.webhook_url).hostname or ""
            if host.endswith("slack.com"):
                payload: dict[str, str] = {"text": text}
            elif host.endswith(("discord.com", "discordapp.com")):
                payload = {"content": text}
            else:
                payload = {"content": text, "text": text}
            try:
                self._sender(
                    c.webhook_url,
                    json.dumps(payload).encode("utf-8"),
                    {"Content-Type": "application/json", "User-Agent": "autotrader"},
                )
            except Exception as e:  # noqa: BLE001
                errors.append(_redact(f"웹훅: {e}", c.webhook_url))
        return errors

"""control(잠금·명령 파일)과 notify(알림) 테스트."""

from __future__ import annotations

import json
import os
import time

import pytest

from autotrader.config import NotifyConfig
from autotrader.control import (
    HEARTBEAT_STALE_SEC,
    AlreadyRunning,
    BotLock,
    commands_dir,
    enqueue_command,
    is_running,
    lock_path,
    pop_commands,
    set_stop,
)
from autotrader.notify import Notifier


# --------------------------------------------------------------------------- #
# 잠금
# --------------------------------------------------------------------------- #
def test_lock_prevents_second_bot_and_is_released(tmp_path):
    a = BotLock(tmp_path, "paper")
    a.acquire()
    assert is_running(tmp_path, "paper")
    assert not is_running(tmp_path, "kis-mock")             # 모드별로 따로
    with pytest.raises(AlreadyRunning):
        BotLock(tmp_path, "paper").acquire()
    BotLock(tmp_path, "kis-mock").acquire()                  # 다른 모드는 동시에 가능
    a.release()
    assert not is_running(tmp_path, "paper")
    with BotLock(tmp_path, "paper"):
        assert is_running(tmp_path, "paper")
    assert not lock_path(tmp_path, "paper").exists()


def test_stale_lock_is_taken_over_and_heartbeat_keeps_it_fresh(tmp_path):
    dead = BotLock(tmp_path, "paper")
    dead.acquire()
    old = time.time() - HEARTBEAT_STALE_SEC - 5
    os.utime(dead.path, (old, old))                          # 죽은 봇이 남긴 오래된 잠금
    assert not is_running(tmp_path, "paper")
    live = BotLock(tmp_path, "paper")
    live.acquire()                                           # 인수 가능
    os.utime(live.path, (old, old))
    live.heartbeat()
    assert is_running(tmp_path, "paper")
    live.path.unlink()                                       # 사용자가 실수로 지워도
    live.heartbeat()                                         # 다음 heartbeat 에서 복구
    assert is_running(tmp_path, "paper")
    live.release()


def test_release_without_acquire_does_not_delete_someone_elses_lock(tmp_path):
    owner = BotLock(tmp_path, "paper")
    owner.acquire()
    BotLock(tmp_path, "paper").release()
    assert is_running(tmp_path, "paper")
    owner.release()


# --------------------------------------------------------------------------- #
# 명령 파일 / STOP
# --------------------------------------------------------------------------- #
def test_commands_round_trip_in_order_and_are_consumed(tmp_path):
    assert pop_commands(tmp_path, "paper") == []
    enqueue_command(tmp_path, "paper", "resume")
    enqueue_command(tmp_path, "paper", "forget", symbol="005930", qty=3, price=71000.0)
    enqueue_command(tmp_path, "kis-mock", "liquidate")
    cmds = pop_commands(tmp_path, "paper")
    assert cmds == [
        {"cmd": "resume", "args": {}},
        {"cmd": "forget", "args": {"symbol": "005930", "qty": 3, "price": 71000.0}},
    ]
    assert pop_commands(tmp_path, "paper") == []             # 한 번만 실행됨
    assert pop_commands(tmp_path, "kis-mock") == [{"cmd": "liquidate", "args": {}}]
    with pytest.raises(ValueError):
        enqueue_command(tmp_path, "paper", "format-disk")


def test_garbage_command_files_are_dropped(tmp_path):
    d = commands_dir(tmp_path, "paper")
    d.mkdir(parents=True)
    (d / "1-bad.json").write_text("{not json", encoding="utf-8")
    (d / "2-unknown.json").write_text(json.dumps({"cmd": "rm -rf", "args": {}}), encoding="utf-8")
    (d / "3-args.json").write_text(json.dumps({"cmd": "forget", "args": "005930"}), encoding="utf-8")
    (d / "4-half.json.tmp").write_text("{}", encoding="utf-8")          # 쓰는 중인 파일은 건드리지 않음
    enqueue_command(tmp_path, "paper", "resume")
    assert pop_commands(tmp_path, "paper") == [{"cmd": "resume", "args": {}}]
    assert sorted(p.name for p in d.iterdir()) == ["4-half.json.tmp"]


def test_stop_switch(tmp_path):
    p = set_stop(tmp_path / "data", True)
    assert p.exists() and p.name == "STOP"
    set_stop(tmp_path / "data", True)
    set_stop(tmp_path / "data", False)
    assert not p.exists()
    set_stop(tmp_path / "data", False)                       # 없어도 오류 없음


# --------------------------------------------------------------------------- #
# 알림
# --------------------------------------------------------------------------- #
class Capture:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict, dict]] = []
        self.fail = fail

    def __call__(self, url: str, body: bytes, headers: dict) -> None:
        self.calls.append((url, json.loads(body), headers))
        if self.fail:
            raise OSError(f"cannot reach {url}")


def test_notifier_disabled_without_config_sends_nothing():
    cap = Capture()
    n = Notifier(NotifyConfig(), sender=cap)
    assert not n.enabled
    n.send("hello")
    n.close()
    assert cap.calls == []


def test_notifier_sends_to_telegram_and_webhook_in_background():
    cap = Capture()
    cfg = NotifyConfig(telegram_token="TOKEN", telegram_chat_id="42", webhook_url="https://discord.com/api/webhooks/1/abc")
    n = Notifier(cfg, prefix="[모의] ", sender=cap)
    n.send("매수 체결")
    n.send("x" * 5000)
    n.close()
    assert len(cap.calls) == 4
    url, body, _ = cap.calls[0]
    assert url == "https://api.telegram.org/botTOKEN/sendMessage"
    assert body["chat_id"] == "42" and body["text"] == "[모의] 매수 체결"
    assert cap.calls[1][1] == {"content": "[모의] 매수 체결"}
    assert len(cap.calls[2][1]["text"]) <= 4096 and len(cap.calls[3][1]["content"]) <= 2000


def test_webhook_payload_shape_depends_on_host():
    cap = Capture()
    Notifier(NotifyConfig(webhook_url="https://hooks.slack.com/services/T/B/x"), sender=cap).send_now("hi")
    Notifier(NotifyConfig(webhook_url="https://example.org/hook"), sender=cap).send_now("hi")
    assert cap.calls[0][1] == {"text": "hi"}
    assert cap.calls[1][1] == {"content": "hi", "text": "hi"}


def test_notifier_failures_are_swallowed_and_secrets_redacted():
    cap = Capture(fail=True)
    cfg = NotifyConfig(telegram_token="SECRET123", telegram_chat_id="42", webhook_url="https://example.org/hook/KEY9")
    n = Notifier(cfg, sender=cap)
    errors = n.send_now("ping")
    assert len(errors) == 2
    assert all("SECRET123" not in e and "KEY9" not in e for e in errors)
    n.send("background")          # 백그라운드 전송 실패도 예외 없이 지나감
    n.close()
    assert len(cap.calls) == 4

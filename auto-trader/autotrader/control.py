"""실행 중인 봇과 명령줄(CLI) 사이의 통신.

봇은 한 번에 하나만 실행되어야 합니다 (둘이 같은 장부로 주문하면 중복 매매가 됩니다).
그래서 봇은 '잠금 파일'을 잡고 주기적으로 갱신(heartbeat)하며,
다른 명령(청산, 재개, 장부 정리)은 '명령 파일'을 남겨 실행 중인 봇이 처리하게 합니다.

파일 배치 (data_dir 아래)
  bot-<mode>.lock            실행 중 표시 (내용: PID, 갱신 시각은 파일 수정시각)
  commands-<mode>/*.json     봇에게 보내는 명령 (처리되면 삭제)
  STOP                       긴급 정지 스위치 (존재하는 동안 어떤 주문도 내지 않음)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

HEARTBEAT_STALE_SEC = 180.0     # 이 시간 동안 갱신이 없으면 죽은 봇의 잠금으로 간주
COMMANDS = ("liquidate", "resume", "forget")


class AlreadyRunning(RuntimeError):
    """같은 모드의 봇이 이미 실행 중."""


def lock_path(data_dir: Path, mode: str) -> Path:
    return Path(data_dir) / f"bot-{mode}.lock"


def commands_dir(data_dir: Path, mode: str) -> Path:
    return Path(data_dir) / f"commands-{mode}"


def is_running(data_dir: Path, mode: str, *, now: float | None = None) -> bool:
    """해당 모드의 봇이 지금 실행 중인지 (잠금 파일이 최근에 갱신되었는지)."""
    p = lock_path(data_dir, mode)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return False
    return ((time.time() if now is None else now) - mtime) < HEARTBEAT_STALE_SEC


class BotLock:
    """봇 단일 실행 보장용 잠금."""

    def __init__(self, data_dir: Path, mode: str) -> None:
        self.path = lock_path(data_dir, mode)
        self._held = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                except OSError:
                    continue            # 방금 사라짐 → 다시 시도
                if age < HEARTBEAT_STALE_SEC:
                    raise AlreadyRunning(
                        f"이미 실행 중인 봇이 있습니다 ({self.path.name}). "
                        "먼저 실행 중인 봇을 종료해 주세요. 봇이 비정상 종료된 직후라면 "
                        f"{int(HEARTBEAT_STALE_SEC // 60)}분 뒤에 다시 시도하면 됩니다."
                    ) from None
                try:
                    self.path.unlink()  # 오래된(죽은) 잠금 제거 후 재시도
                except OSError:
                    pass
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            self._held = True
            return
        raise AlreadyRunning(f"잠금 파일을 만들 수 없습니다: {self.path}")

    def heartbeat(self) -> None:
        if not self._held:
            return
        try:
            os.utime(self.path, None)
        except OSError:
            # 잠금 파일이 지워졌으면 다시 만듭니다 (사용자가 실수로 지운 경우)
            try:
                self.path.write_text(str(os.getpid()), encoding="utf-8")
            except OSError:
                pass

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        try:
            self.path.unlink()
        except OSError:
            pass

    def __enter__(self) -> "BotLock":
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


def enqueue_command(data_dir: Path, mode: str, cmd: str, **args: Any) -> Path:
    """실행 중인 봇에게 명령을 남깁니다. 반환값은 만들어진 명령 파일 경로."""
    if cmd not in COMMANDS:
        raise ValueError(f"알 수 없는 명령: {cmd}")
    d = commands_dir(data_dir, mode)
    d.mkdir(parents=True, exist_ok=True)
    name = f"{time.time_ns()}-{os.getpid()}-{cmd}.json"
    tmp = d / (name + ".tmp")
    tmp.write_text(json.dumps({"cmd": cmd, "args": args}, ensure_ascii=False), encoding="utf-8")
    final = d / name
    os.replace(tmp, final)          # 반쯤 쓰인 파일을 봇이 읽지 않도록 원자적으로 이름 변경
    return final


def pop_commands(data_dir: Path, mode: str) -> list[dict[str, Any]]:
    """쌓인 명령을 오래된 순서로 꺼내고 파일을 지웁니다. 읽을 수 없는 파일은 버립니다."""
    d = commands_dir(data_dir, mode)
    if not d.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        try:
            p.unlink()
        except OSError:
            continue                # 지우지 못한 명령은 실행하지 않음 (반복 실행 방지)
        if isinstance(data, dict) and data.get("cmd") in COMMANDS and isinstance(data.get("args", {}), dict):
            out.append({"cmd": data["cmd"], "args": data.get("args", {})})
    return out


def set_stop(data_dir: Path, on: bool) -> Path:
    """긴급 정지 스위치를 켜거나 끕니다."""
    p = Path(data_dir) / "STOP"
    if on:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("이 파일이 있는 동안 자동매매 봇은 어떤 주문도 내지 않습니다.\n", encoding="utf-8")
    else:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    return p

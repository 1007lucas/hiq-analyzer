"""상태 저장소.

TradingCore 의 상태(현금, 포지션, 당일 진행상황)와 기록(주문, 평가금, 이벤트)을
보관합니다.

* ``MemoryStore`` : 메모리에만 보관 (백테스트용, 빠름)
* ``SqliteStore`` : SQLite 파일에 보관 (실전/페이퍼용, 재시작해도 이어서 동작)

코어 상태는 JSON 문서 1개로 통째로 저장합니다 (원자적 갱신).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

ORDER_FIELDS = (
    "ts",              # ISO 시각 (KST)
    "day",             # 거래일 YYYY-MM-DD
    "symbol",
    "side",            # buy | sell
    "qty",             # 요청 수량
    "filled_qty",      # 체결 수량
    "price",           # 평균 체결가
    "ref_price",       # 판단 시점 기준가
    "amount",          # 체결 금액 (filled_qty * price)
    "fee",             # 수수료 (추정)
    "tax",             # 거래세 (추정, 매도만)
    "pnl",             # 실현손익 (매도만, 매수·매도 비용 차감 후)
    "pnl_pct",         # 실현수익률 (매도만, 비용 차감 후, 0.05 = 5%)
    "entry_price",     # (매도만) 진입 평균단가
    "entry_day",       # (매도만) 진입일
    "reason",          # 주문 사유
    "status",          # filled | partial | rejected | unknown
    "broker_order_id",
    "message",
    "cash_after",      # 주문 반영 후 봇 현금
)


class StateStore(Protocol):
    persistent: bool

    def load_state(self) -> dict[str, Any] | None: ...
    def save_state(self, state: dict[str, Any]) -> None: ...
    def record_order(self, rec: dict[str, Any]) -> None: ...
    def record_equity(self, day: date, equity: float, cash: float) -> None: ...
    def log_event(self, level: str, message: str, ts: datetime | None = None) -> None: ...
    def orders(self, limit: int | None = None) -> list[dict[str, Any]]: ...
    def equity_history(self) -> list[tuple[date, float, float]]: ...
    def events(self, limit: int | None = 200) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...


class MemoryStore:
    """메모리 저장소. 코어 상태는 저장하지 않고 기록만 리스트에 쌓습니다."""

    persistent = False

    def __init__(self) -> None:
        self._state: dict[str, Any] | None = None
        self._orders: list[dict[str, Any]] = []
        self._equity: dict[date, tuple[float, float]] = {}
        self._events: list[dict[str, Any]] = []

    def load_state(self) -> dict[str, Any] | None:
        return self._state

    def save_state(self, state: dict[str, Any]) -> None:
        self._state = state

    def record_order(self, rec: dict[str, Any]) -> None:
        self._orders.append({k: rec.get(k) for k in ORDER_FIELDS})

    def record_equity(self, day: date, equity: float, cash: float) -> None:
        self._equity[day] = (float(equity), float(cash))

    def log_event(self, level: str, message: str, ts: datetime | None = None) -> None:
        self._events.append({"ts": ts.isoformat() if ts else "", "level": level, "message": message})

    def orders(self, limit: int | None = None) -> list[dict[str, Any]]:
        """오래된 것 → 최신 순. limit 이 있으면 최신 limit 개."""
        return list(self._orders if limit is None else self._orders[-limit:])

    def equity_history(self) -> list[tuple[date, float, float]]:
        return [(d, e, c) for d, (e, c) in sorted(self._equity.items())]

    def events(self, limit: int | None = 200) -> list[dict[str, Any]]:
        return list(self._events if limit is None else self._events[-limit:])

    def close(self) -> None:
        pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT,
    day             TEXT,
    symbol          TEXT,
    side            TEXT,
    qty             INTEGER,
    filled_qty      INTEGER,
    price           REAL,
    ref_price       REAL,
    amount          REAL,
    fee             REAL,
    tax             REAL,
    pnl             REAL,
    pnl_pct         REAL,
    entry_price     REAL,
    entry_day       TEXT,
    reason          TEXT,
    status          TEXT,
    broker_order_id TEXT,
    message         TEXT,
    cash_after      REAL
);
CREATE TABLE IF NOT EXISTS equity (
    day    TEXT PRIMARY KEY,
    equity REAL NOT NULL,
    cash   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT,
    level   TEXT,
    message TEXT
);
"""


class SqliteStore:
    """SQLite 저장소. 한 프로세스(봇)가 쓰고, 대시보드 등 다른 프로세스가 읽을 수 있습니다."""

    persistent = True

    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        self.path = Path(path)
        self.read_only = read_only
        self._lock = threading.Lock()
        if read_only:
            if not self.path.is_file():
                raise FileNotFoundError(f"상태 DB 가 없습니다: {self.path}")
            uri = f"file:{self.path.as_posix()}?mode=ro"
            self._db = sqlite3.connect(uri, uri=True, timeout=10, check_same_thread=False)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(self.path), timeout=10, check_same_thread=False)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            with self._db:
                self._db.executescript(_SCHEMA)
        self._db.row_factory = sqlite3.Row

    # -- 코어 상태 -----------------------------------------------------------
    def load_state(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT value FROM kv WHERE key = 'core_state'").fetchone()
        if row is None:
            return None
        return json.loads(row["value"])

    def save_state(self, state: dict[str, Any]) -> None:
        payload = json.dumps(state, ensure_ascii=False)
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO kv(key, value) VALUES('core_state', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (payload,),
            )

    # -- 기록 ----------------------------------------------------------------
    def record_order(self, rec: dict[str, Any]) -> None:
        cols = ", ".join(ORDER_FIELDS)
        marks = ", ".join("?" for _ in ORDER_FIELDS)
        with self._lock, self._db:
            self._db.execute(
                f"INSERT INTO orders({cols}) VALUES({marks})",
                tuple(rec.get(k) for k in ORDER_FIELDS),
            )

    def record_equity(self, day: date, equity: float, cash: float) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO equity(day, equity, cash) VALUES(?, ?, ?) "
                "ON CONFLICT(day) DO UPDATE SET equity = excluded.equity, cash = excluded.cash",
                (day.isoformat(), float(equity), float(cash)),
            )

    def log_event(self, level: str, message: str, ts: datetime | None = None) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO events(ts, level, message) VALUES(?, ?, ?)",
                (ts.isoformat() if ts else "", level, message),
            )
            # 이벤트 로그가 무한히 커지지 않도록 오래된 것은 정리
            self._db.execute("DELETE FROM events WHERE id <= (SELECT MAX(id) FROM events) - 5000")

    # -- 조회 ----------------------------------------------------------------
    def orders(self, limit: int | None = None) -> list[dict[str, Any]]:
        """오래된 것 → 최신 순. limit 이 있으면 최신 limit 개."""
        cols = ", ".join(ORDER_FIELDS)
        with self._lock:
            if limit is None:
                rows = self._db.execute(f"SELECT {cols} FROM orders ORDER BY id").fetchall()
            else:
                rows = self._db.execute(
                    f"SELECT {cols} FROM (SELECT id, {cols} FROM orders ORDER BY id DESC LIMIT ?) ORDER BY id",
                    (int(limit),),
                ).fetchall()
        return [dict(r) for r in rows]

    def equity_history(self) -> list[tuple[date, float, float]]:
        with self._lock:
            rows = self._db.execute("SELECT day, equity, cash FROM equity ORDER BY day").fetchall()
        return [(date.fromisoformat(r["day"]), float(r["equity"]), float(r["cash"])) for r in rows]

    def events(self, limit: int | None = 200) -> list[dict[str, Any]]:
        with self._lock:
            if limit is None:
                rows = self._db.execute("SELECT ts, level, message FROM events ORDER BY id").fetchall()
            else:
                rows = self._db.execute(
                    "SELECT ts, level, message FROM "
                    "(SELECT id, ts, level, message FROM events ORDER BY id DESC LIMIT ?) ORDER BY id",
                    (int(limit),),
                ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()

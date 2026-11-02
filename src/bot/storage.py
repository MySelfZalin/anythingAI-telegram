import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import aiosqlite

from bot.providers.base import ChatMessage, Usage

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    provider TEXT,
    model TEXT,
    session_started_at REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_user ON messages (user_id, id);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost REAL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_user ON usage (user_id, created_at);
"""

TOTALS_COLUMNS = """
    COUNT(*),
    COALESCE(SUM(input_tokens), 0),
    COALESCE(SUM(output_tokens), 0),
    COALESCE(SUM(cost), 0),
    COALESCE(SUM(cost IS NULL), 0)
"""


@dataclass(frozen=True, slots=True)
class UsageTotals:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    unpriced: int = 0


@dataclass(frozen=True, slots=True)
class ModelUsage:
    label: str
    totals: UsageTotals


class Database:
    def __init__(self, connection: aiosqlite.Connection, clock: Callable[[], float]) -> None:
        self._db = connection
        self._clock = clock

    @classmethod
    async def open(cls, path: Path | str, clock: Callable[[], float] = time.time) -> Self:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(path)
        await connection.execute("PRAGMA journal_mode=WAL")
        await connection.executescript(SCHEMA)
        await connection.commit()
        return cls(connection, clock)

    async def close(self) -> None:
        await self._db.close()

    async def get_model(self, user_id: int) -> tuple[str, str] | None:
        async with self._db.execute(
            "SELECT provider, model FROM user_settings WHERE user_id = ? AND model IS NOT NULL",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return (row[0], row[1]) if row else None

    async def set_model(self, user_id: int, provider: str, model: str) -> None:
        await self._db.execute(
            """
            INSERT INTO user_settings (user_id, provider, model) VALUES (?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET provider = excluded.provider, model = excluded.model
            """,
            (user_id, provider, model),
        )
        await self._db.commit()

    async def reset_session(self, user_id: int) -> None:
        await self._db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        await self._db.execute(
            """
            INSERT INTO user_settings (user_id, session_started_at) VALUES (?, ?)
            ON CONFLICT (user_id) DO UPDATE SET session_started_at = excluded.session_started_at
            """,
            (user_id, self._clock()),
        )
        await self._db.commit()

    async def session_started_at(self, user_id: int) -> float:
        async with self._db.execute(
            "SELECT session_started_at FROM user_settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0.0

    async def get_history(self, user_id: int) -> list[ChatMessage]:
        async with self._db.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [ChatMessage(role, content) for role, content in rows]

    async def count_messages(self, user_id: int) -> int:
        async with self._db.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def add_exchange(self, user_id: int, question: str, answer: str) -> None:
        now = self._clock()
        await self._db.executemany(
            "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            [(user_id, "user", question, now), (user_id, "assistant", answer, now)],
        )
        await self._db.commit()

    async def add_usage(
        self, user_id: int, provider: str, model: str, usage: Usage, cost: float | None
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO usage
                (user_id, provider, model, input_tokens, output_tokens, cost, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                provider,
                model,
                usage.input_tokens,
                usage.output_tokens,
                cost,
                self._clock(),
            ),
        )
        await self._db.commit()

    async def last_usage(self, user_id: int, since: float) -> Usage | None:
        async with self._db.execute(
            """
            SELECT input_tokens, output_tokens FROM usage
            WHERE user_id = ? AND created_at >= ? ORDER BY id DESC LIMIT 1
            """,
            (user_id, since),
        ) as cursor:
            row = await cursor.fetchone()
        return Usage(row[0], row[1]) if row else None

    async def totals(self, user_id: int, since: float = 0.0) -> UsageTotals:
        async with self._db.execute(
            f"SELECT {TOTALS_COLUMNS} FROM usage WHERE user_id = ? AND created_at >= ?",  # noqa: S608
            (user_id, since),
        ) as cursor:
            row = await cursor.fetchone()
        return UsageTotals(*row) if row else UsageTotals()

    async def totals_by_model(self, user_id: int) -> list[ModelUsage]:
        async with self._db.execute(
            f"""
            SELECT provider, model, {TOTALS_COLUMNS} FROM usage WHERE user_id = ?
            GROUP BY provider, model ORDER BY SUM(input_tokens + output_tokens) DESC
            """,  # noqa: S608
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [ModelUsage(f"{row[0]}/{row[1]}", UsageTotals(*row[2:])) for row in rows]

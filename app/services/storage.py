from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    content TEXT,
    transcript TEXT,
    status TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, id);
"""

USER_COLUMNS = "u.id, u.username, u.first_name, u.last_name, u.first_seen, u.last_seen"
USER_MESSAGE_COUNT = "(SELECT COUNT(*) FROM messages m WHERE m.user_id = u.id)"
MESSAGE_COLUMNS = "id, user_id, chat_id, message_id, kind, content, transcript, status, created_at"


@dataclass(frozen=True)
class UserRow:
    id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    first_seen: str
    last_seen: str
    message_count: int


@dataclass(frozen=True)
class MessageRow:
    id: int
    user_id: int
    chat_id: int
    message_id: int
    kind: str
    content: str | None
    transcript: str | None
    status: str | None
    created_at: str


def _connect() -> aiosqlite.Connection:
    return aiosqlite.connect(settings.DB_PATH)


async def init_db() -> None:
    Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with _connect() as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def log_message(
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    chat_id: int,
    message_id: int,
    kind: str,
    content: str | None,
) -> int:
    now = datetime.now(UTC).isoformat()
    async with _connect() as db:
        await db.execute(
            """
            INSERT INTO users (id, username, first_name, last_name, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_seen = excluded.last_seen
            """,
            (user_id, username, first_name, last_name, now, now),
        )
        cursor = await db.execute(
            """
            INSERT INTO messages (user_id, chat_id, message_id, kind, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, chat_id, message_id, kind, content, now),
        )
        await db.commit()
        return cursor.lastrowid


async def set_result(log_id: int, status: str, transcript: str | None = None) -> None:
    async with _connect() as db:
        await db.execute(
            "UPDATE messages SET status = ?, transcript = ? WHERE id = ?",
            (status, transcript, log_id),
        )
        await db.commit()


async def _count(query: str, *params: int) -> int:
    async with _connect() as db:
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
    return row[0]


async def count_users() -> int:
    return await _count("SELECT COUNT(*) FROM users")


async def count_all_messages() -> int:
    return await _count("SELECT COUNT(*) FROM messages")


async def count_messages(user_id: int) -> int:
    return await _count("SELECT COUNT(*) FROM messages WHERE user_id = ?", user_id)


async def list_users(limit: int, offset: int) -> list[UserRow]:
    async with _connect() as db:
        async with db.execute(
            f"""
            SELECT {USER_COLUMNS}, {USER_MESSAGE_COUNT}
            FROM users u
            ORDER BY u.last_seen DESC, u.id
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
    return [UserRow(*row) for row in rows]


async def get_user(user_id: int) -> UserRow | None:
    async with _connect() as db:
        async with db.execute(
            f"SELECT {USER_COLUMNS}, {USER_MESSAGE_COUNT} FROM users u WHERE u.id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return UserRow(*row) if row else None


async def list_messages(user_id: int, limit: int, offset: int) -> list[MessageRow]:
    async with _connect() as db:
        async with db.execute(
            f"""
            SELECT {MESSAGE_COLUMNS}
            FROM messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
    return [MessageRow(*row) for row in rows]


async def get_message(log_id: int) -> MessageRow | None:
    async with _connect() as db:
        async with db.execute(
            f"SELECT {MESSAGE_COLUMNS} FROM messages WHERE id = ?",
            (log_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return MessageRow(*row) if row else None

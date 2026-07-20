from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import aiosqlite

from app.core.config import BASE_DIR, get_settings

SCHEMA_PATH = BASE_DIR / "app" / "storage" / "schema.sql"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> aiosqlite.Connection:
    settings = get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return aiosqlite.connect(settings.db_path, timeout=10)


async def _configure(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA busy_timeout=10000")


async def init_db() -> None:
    async with _connect() as db:
        await _configure(db)
        await db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        await db.commit()


async def upsert_telegram_user(user: dict) -> dict:
    now = utc_now()
    telegram_user_id = int(user["id"])
    async with _connect() as db:
        await _configure(db)
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            INSERT INTO users (
                telegram_user_id, username, first_name, last_name, language_code,
                created_at, updated_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                language_code = excluded.language_code,
                updated_at = excluded.updated_at,
                last_seen_at = excluded.last_seen_at
            """,
            (
                telegram_user_id,
                user.get("username"),
                user.get("first_name"),
                user.get("last_name"),
                user.get("language_code"),
                now,
                now,
                now,
            ),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM users WHERE telegram_user_id = ?", (telegram_user_id,))
        row = await cursor.fetchone()
        return dict(row)


async def create_session(user_id: int, test_key: str, project_id: str | None = None) -> dict:
    now = utc_now()
    session_id = str(uuid4())
    async with _connect() as db:
        await _configure(db)
        await db.execute(
            """
            INSERT INTO test_sessions (
                id, user_id, project_id, test_key, test_version, scoring_version,
                phrase_bank_version, status, started_at, updated_at
            ) VALUES (?, ?, ?, ?, '1', '1', '1', 'in_progress', ?, ?)
            """,
            (session_id, user_id, project_id, test_key, now, now),
        )
        await db.commit()
    return {"id": session_id, "test_key": test_key, "status": "in_progress", "started_at": now}


async def list_user_results(user_id: int, limit: int = 50) -> list[dict]:
    async with _connect() as db:
        await _configure(db)
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT s.id AS session_id, s.test_key, s.completed_at,
                   p.code_name, r.primary_narrative_key, r.primary_score,
                   r.confidence, r.result_text
            FROM test_sessions s
            JOIN test_results r ON r.session_id = s.id
            LEFT JOIN projects p ON p.id = s.project_id
            WHERE s.user_id = ?
            ORDER BY s.completed_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def log_event(event_name: str, user_id: int | None, session_id: str | None, payload: dict | None = None) -> None:
    async with _connect() as db:
        await _configure(db)
        await db.execute(
            "INSERT INTO analytics_events (user_id, session_id, event_name, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, session_id, event_name, json.dumps(payload or {}, ensure_ascii=False), utc_now()),
        )
        await db.commit()


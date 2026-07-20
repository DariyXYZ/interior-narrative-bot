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


async def create_project(
    user_id: int,
    code_name: str,
    object_type: str | None,
    area_m2: float | None,
    project_started_on: str | None,
    concept_due_on: str | None,
    presentation_on: str | None,
    implementation_on: str | None,
) -> dict:
    now = utc_now()
    project_id = str(uuid4())
    async with _connect() as db:
        await _configure(db)
        await db.execute(
            """
            INSERT INTO projects (
                id, user_id, code_name, object_type, area_m2,
                project_started_on, concept_due_on, presentation_on, implementation_on,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id, user_id, code_name, object_type, area_m2,
                project_started_on, concept_due_on, presentation_on, implementation_on,
                now, now,
            ),
        )
        await db.commit()
    return {"id": project_id, "code_name": code_name}


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


async def get_session(session_id: str, user_id: int) -> dict | None:
    async with _connect() as db:
        await _configure(db)
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM test_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


def _decode_answer(answer_json: str) -> list[str]:
    data = json.loads(answer_json)
    if "option_ids" in data:
        return data["option_ids"]
    return [data["option_id"]]  # старый формат (до multi-select), совместимость


async def list_session_answers(session_id: str) -> dict[str, list[str]]:
    async with _connect() as db:
        await _configure(db)
        cursor = await db.execute(
            "SELECT question_id, answer_json FROM session_answers WHERE session_id = ?",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return {question_id: _decode_answer(answer_json) for question_id, answer_json in rows}


async def upsert_answer(session_id: str, question_id: str, option_ids: list[str]) -> None:
    now = utc_now()
    async with _connect() as db:
        await _configure(db)
        await db.execute(
            """
            INSERT INTO session_answers (session_id, question_id, answer_json, answered_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, question_id) DO UPDATE SET
                answer_json = excluded.answer_json,
                answered_at = excluded.answered_at
            """,
            (session_id, question_id, json.dumps({"option_ids": option_ids}, ensure_ascii=False), now),
        )
        await db.execute(
            "UPDATE test_sessions SET current_question_id = ?, updated_at = ? WHERE id = ?",
            (question_id, now, session_id),
        )
        await db.commit()


async def complete_session(session_id: str, result: dict) -> dict:
    now = utc_now()
    result_id = str(uuid4())
    async with _connect() as db:
        await _configure(db)
        await db.execute(
            "UPDATE test_sessions SET status = 'completed', completed_at = ?, updated_at = ? WHERE id = ?",
            (now, now, session_id),
        )
        await db.execute(
            """
            INSERT INTO test_results (
                id, session_id, primary_narrative_key, primary_score, alternatives_json,
                confidence, result_text, fragment_ids_json, scoring_trace_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result_id, session_id, result["primary_narrative_key"], result["primary_score"],
                json.dumps(result["alternatives"], ensure_ascii=False),
                result["confidence"], result["result_text"],
                json.dumps(result["fragment_ids"], ensure_ascii=False),
                json.dumps(result["scoring_trace"], ensure_ascii=False),
                now,
            ),
        )
        await db.commit()
    return {"id": result_id, "completed_at": now}


async def get_result(session_id: str, user_id: int) -> dict | None:
    async with _connect() as db:
        await _configure(db)
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT s.id AS session_id, s.test_key, s.status, s.completed_at, s.project_id,
                   r.primary_narrative_key, r.primary_score, r.alternatives_json,
                   r.confidence, r.result_text, r.scoring_trace_json
            FROM test_sessions s
            JOIN test_results r ON r.session_id = s.id
            WHERE s.id = ? AND s.user_id = ?
            """,
            (session_id, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        data = dict(row)
        data["alternatives"] = json.loads(data.pop("alternatives_json"))
        data["scoring_trace"] = json.loads(data.pop("scoring_trace_json"))
        return data


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


"""Хранилище на Postgres (Supabase).

Раньше данные лежали в SQLite-файле рядом с процессом. Это привязывало бота к
одной машине: выключен компьютер — тест не пройти, а единственная копия
результатов лежала на одном диске без бэкапа.

Подключение идёт через transaction-пулер Supabase (порт 6543). Отсюда две
обязательные особенности:

* `statement_cache_size=0` — пулер в этом режиме отдаёт соединение другому
  клиенту между запросами, и prepared statements такого не переживают;
* маленький пул — на serverless инстансов много, и каждый держит свои
  соединения.

Схема задаётся через `search_path`, поэтому в запросах нет префикса: рабочая —
`interior`, тесты гоняются в своей и рабочих данных не касаются.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import asyncpg

from app.core.config import get_settings

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None and not _pool.is_closing():
        return _pool
    async with _pool_lock:
        if _pool is None or _pool.is_closing():
            settings = get_settings()
            _pool = await asyncpg.create_pool(
                settings.require_database_url(),
                statement_cache_size=0,
                min_size=1,
                max_size=4,
                command_timeout=20,
                server_settings={"search_path": f"{settings.db_schema},public"},
            )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _plain(value):
    """Даты наружу уходят строками ISO — такими их ждут фронтенд и история."""
    return value.isoformat() if isinstance(value, datetime) else value


def _row(record: asyncpg.Record | None) -> dict | None:
    return {key: _plain(value) for key, value in record.items()} if record is not None else None


async def init_db() -> None:
    """Проверка связи, а не создание таблиц.

    Схему раскатывает `migrations/001_interior_schema.sql` — отдельным осознанным
    шагом. Молча создавать таблицы на каждом старте в общей базе нельзя.
    """
    pool = await get_pool()
    await pool.fetchval("SELECT 1")


async def upsert_telegram_user(user: dict) -> dict:
    now = utc_now()
    pool = await get_pool()
    record = await pool.fetchrow(
        """
        INSERT INTO users (telegram_user_id, username, first_name, last_name, language_code,
                           created_at, updated_at, last_seen_at)
        VALUES ($1, $2, $3, $4, $5, $6, $6, $6)
        ON CONFLICT (telegram_user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            language_code = excluded.language_code,
            updated_at = excluded.updated_at,
            last_seen_at = excluded.last_seen_at
        RETURNING *
        """,
        int(user["id"]), user.get("username"), user.get("first_name"),
        user.get("last_name"), user.get("language_code"), now,
    )
    return _row(record)


async def get_user_by_telegram_id(telegram_user_id: int) -> dict | None:
    pool = await get_pool()
    return _row(await pool.fetchrow("SELECT * FROM users WHERE telegram_user_id = $1", telegram_user_id))


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
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO projects (id, user_id, code_name, object_type, area_m2,
                              project_started_on, concept_due_on, presentation_on,
                              implementation_on, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10)
        """,
        project_id, user_id, code_name, object_type, area_m2,
        project_started_on, concept_due_on, presentation_on, implementation_on, now,
    )
    return {"id": project_id, "code_name": code_name}


async def create_session(user_id: int, test_key: str, project_id: str | None = None) -> dict:
    now = utc_now()
    session_id = str(uuid4())
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO test_sessions (id, user_id, project_id, test_key, test_version,
                                   scoring_version, phrase_bank_version, status,
                                   started_at, updated_at)
        VALUES ($1, $2, $3, $4, '1', '1', '1', 'in_progress', $5, $5)
        """,
        session_id, user_id, project_id, test_key, now,
    )
    return {"id": session_id, "test_key": test_key, "status": "in_progress", "started_at": now.isoformat()}


async def get_session(session_id: str, user_id: int) -> dict | None:
    pool = await get_pool()
    return _row(
        await pool.fetchrow("SELECT * FROM test_sessions WHERE id = $1 AND user_id = $2", session_id, user_id)
    )


def _decode_answer(answer: str) -> list[str]:
    data = json.loads(answer)
    if "option_ids" in data:
        return data["option_ids"]
    return [data["option_id"]]  # старый формат (до multi-select), совместимость


async def list_session_answers(session_id: str) -> dict[str, list[str]]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT question_id, answer FROM session_answers WHERE session_id = $1", session_id
    )
    return {row["question_id"]: _decode_answer(row["answer"]) for row in rows}


async def upsert_answer(session_id: str, question_id: str, option_ids: list[str]) -> None:
    now = utc_now()
    pool = await get_pool()
    # Ответ и отметка «на каком вопросе человек» — одно событие: запиши их
    # порознь и упади между ними, и возобновление приведёт не туда.
    async with pool.acquire() as db, db.transaction():
        await db.execute(
            """
            INSERT INTO session_answers (session_id, question_id, answer, answered_at)
            VALUES ($1, $2, $3::jsonb, $4)
            ON CONFLICT (session_id, question_id) DO UPDATE SET
                answer = excluded.answer,
                answered_at = excluded.answered_at
            """,
            session_id, question_id, json.dumps({"option_ids": option_ids}, ensure_ascii=False), now,
        )
        await db.execute(
            "UPDATE test_sessions SET current_question_id = $1, updated_at = $2 WHERE id = $3",
            question_id, now, session_id,
        )


async def complete_session(session_id: str, result: dict) -> dict | None:
    """Завершает сессию. None — если её уже завершил кто-то другой.

    Два «завершить» подряд — обычное дело: двойной тап по последнему ответу или
    повтор запроса после таймаута. Гонку снимает сам UPDATE: он меняет статус
    только с 'in_progress', и проигравший запрос не пишет второй результат
    (иначе UNIQUE по session_id роняет запрос пятисоткой).
    """
    now = utc_now()
    result_id = str(uuid4())
    pool = await get_pool()
    async with pool.acquire() as db, db.transaction():
        won = await db.fetchval(
            "UPDATE test_sessions SET status = 'completed', completed_at = $1, updated_at = $1 "
            "WHERE id = $2 AND status = 'in_progress' RETURNING id",
            now, session_id,
        )
        if won is None:
            return None
        await db.execute(
            """
            INSERT INTO test_results (id, session_id, primary_narrative_key, primary_score,
                                      alternatives, confidence, result_text, fragment_ids,
                                      scoring_trace, created_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8::jsonb, $9::jsonb, $10)
            """,
            result_id, session_id, result["primary_narrative_key"], result["primary_score"],
            json.dumps(result["alternatives"], ensure_ascii=False),
            result["confidence"], result["result_text"],
            json.dumps(result["fragment_ids"], ensure_ascii=False),
            json.dumps(result["scoring_trace"], ensure_ascii=False),
            now,
        )
    return {"id": result_id, "completed_at": now.isoformat()}


async def get_result(session_id: str, user_id: int) -> dict | None:
    pool = await get_pool()
    record = await pool.fetchrow(
        """
        SELECT s.id AS session_id, s.test_key, s.status, s.completed_at, s.project_id,
               r.primary_narrative_key, r.primary_score, r.alternatives,
               r.confidence, r.result_text, r.scoring_trace
        FROM test_sessions s
        JOIN test_results r ON r.session_id = s.id
        WHERE s.id = $1 AND s.user_id = $2
        """,
        session_id, user_id,
    )
    data = _row(record)
    if data is None:
        return None
    data["alternatives"] = json.loads(data["alternatives"])
    data["scoring_trace"] = json.loads(data["scoring_trace"])
    return data


async def list_user_results(user_id: int, limit: int = 50) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT s.id AS session_id, s.test_key, s.completed_at,
               p.code_name, r.primary_narrative_key, r.primary_score,
               r.confidence, r.result_text
        FROM test_sessions s
        JOIN test_results r ON r.session_id = s.id
        LEFT JOIN projects p ON p.id = s.project_id
        WHERE s.user_id = $1
        ORDER BY s.completed_at DESC
        LIMIT $2
        """,
        user_id, limit,
    )
    return [_row(row) for row in rows]


async def log_event(event_name: str, user_id: int | None, session_id: str | None, payload: dict | None = None) -> None:
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO analytics_events (user_id, session_id, event_name, payload, created_at) "
        "VALUES ($1, $2, $3, $4::jsonb, $5)",
        user_id, session_id, event_name, json.dumps(payload or {}, ensure_ascii=False), utc_now(),
    )

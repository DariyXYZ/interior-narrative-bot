"""Перенос данных из локального SQLite в Postgres (Supabase).

Запускается один раз при переезде и потом сколько угодно раз: всё вставляется
через ON CONFLICT DO NOTHING, поэтому повтор ничего не портит и не задваивает.

    python scripts/migrate_sqlite_to_postgres.py            # перенести
    python scripts/migrate_sqlite_to_postgres.py --check    # только сверить

Строка подключения берётся из DATABASE_URL (.env или окружение). Порядок таблиц
важен: сначала пользователи, потом всё, что на них ссылается.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime

import asyncpg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings  # noqa: E402

TABLES = ["users", "projects", "test_sessions", "session_answers", "test_results", "analytics_events"]


def _moment(value: str | None) -> datetime | None:
    """ISO-строка SQLite → datetime, который ждёт timestamptz."""
    return datetime.fromisoformat(value) if value else None


def _read_sqlite(path: str) -> dict[str, list[sqlite3.Row]]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in TABLES}
    finally:
        connection.close()


async def _copy(pool: asyncpg.Pool, rows: dict[str, list[sqlite3.Row]]) -> None:
    async with pool.acquire() as db, db.transaction():
        for row in rows["users"]:
            await db.execute(
                """INSERT INTO interior.users (id, telegram_user_id, username, first_name, last_name,
                       language_code, created_at, updated_at, last_seen_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT (id) DO NOTHING""",
                row["id"], row["telegram_user_id"], row["username"], row["first_name"], row["last_name"],
                row["language_code"], _moment(row["created_at"]), _moment(row["updated_at"]),
                _moment(row["last_seen_at"]),
            )
        for row in rows["projects"]:
            await db.execute(
                """INSERT INTO interior.projects (id, user_id, code_name, object_type, area_m2,
                       project_started_on, concept_due_on, presentation_on, implementation_on,
                       created_at, updated_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) ON CONFLICT (id) DO NOTHING""",
                row["id"], row["user_id"], row["code_name"], row["object_type"], row["area_m2"],
                row["project_started_on"], row["concept_due_on"], row["presentation_on"],
                row["implementation_on"], _moment(row["created_at"]), _moment(row["updated_at"]),
            )
        for row in rows["test_sessions"]:
            await db.execute(
                """INSERT INTO interior.test_sessions (id, user_id, project_id, test_key, test_version,
                       scoring_version, phrase_bank_version, status, current_question_id,
                       started_at, updated_at, completed_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) ON CONFLICT (id) DO NOTHING""",
                row["id"], row["user_id"], row["project_id"], row["test_key"], row["test_version"],
                row["scoring_version"], row["phrase_bank_version"], row["status"], row["current_question_id"],
                _moment(row["started_at"]), _moment(row["updated_at"]), _moment(row["completed_at"]),
            )
        for row in rows["session_answers"]:
            await db.execute(
                """INSERT INTO interior.session_answers (session_id, question_id, answer, answered_at)
                   VALUES ($1,$2,$3::jsonb,$4) ON CONFLICT (session_id, question_id) DO NOTHING""",
                row["session_id"], row["question_id"], row["answer_json"], _moment(row["answered_at"]),
            )
        for row in rows["test_results"]:
            await db.execute(
                """INSERT INTO interior.test_results (id, session_id, primary_narrative_key, primary_score,
                       alternatives, confidence, result_text, fragment_ids, scoring_trace, created_at)
                   VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7,$8::jsonb,$9::jsonb,$10)
                   ON CONFLICT (id) DO NOTHING""",
                row["id"], row["session_id"], row["primary_narrative_key"], row["primary_score"],
                row["alternatives_json"], row["confidence"], row["result_text"],
                row["fragment_ids_json"], row["scoring_trace_json"], _moment(row["created_at"]),
            )
        for row in rows["analytics_events"]:
            await db.execute(
                """INSERT INTO interior.analytics_events (id, user_id, session_id, event_name, payload, created_at)
                   VALUES ($1,$2,$3,$4,$5::jsonb,$6) ON CONFLICT (id) DO NOTHING""",
                row["id"], row["user_id"], row["session_id"], row["event_name"],
                row["payload_json"], _moment(row["created_at"]),
            )

        # Идентити-счётчики не знают о вставленных вручную id — следующий INSERT
        # без них упёрся бы в уже занятый первичный ключ.
        for table in ("users", "analytics_events"):
            await db.execute(
                f"""SELECT setval(pg_get_serial_sequence('interior.{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM interior.{table}), 1), true)"""
            )


async def _compare(pool: asyncpg.Pool, rows: dict[str, list[sqlite3.Row]]) -> bool:
    print(f"{'таблица':<18}{'sqlite':>8}{'postgres':>10}")
    ok = True
    for table in TABLES:
        there = await pool.fetchval(f"SELECT count(*) FROM interior.{table}")
        here = len(rows[table])
        mark = "" if there >= here else "  ← не хватает"
        ok = ok and there >= here
        print(f"{table:<18}{here:>8}{there:>10}{mark}")
    return ok


async def main() -> int:
    settings = get_settings()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        print("DATABASE_URL не задан — положите строку подключения в .env")
        return 2

    rows = _read_sqlite(str(settings.db_path))
    # statement_cache_size=0 обязателен: пулер Supabase в transaction-режиме
    # (порт 6543) не держит prepared statements между запросами.
    pool = await asyncpg.create_pool(dsn, statement_cache_size=0, min_size=1, max_size=2)
    try:
        if "--check" not in sys.argv:
            await _copy(pool, rows)
        return 0 if await _compare(pool, rows) else 1
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

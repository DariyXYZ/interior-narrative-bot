"""Общая обвязка тестов: своя схема в той же базе Supabase.

Тесты ходят в настоящий Postgres, а не в подменённое хранилище: половина того,
что здесь проверяется — гонки при завершении сессии, UNIQUE по session_id,
поведение ON CONFLICT — живёт именно в базе, и на заглушке доказывает ровно
ничего. Чтобы рабочие данные при этом были в безопасности, всё происходит в
схеме `interior_test`: она пересоздаётся перед прогоном и чистится перед каждым
тестом.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import BASE_DIR, get_settings  # noqa: E402

TEST_SCHEMA = "interior_test"
TABLES = ("analytics_events", "test_results", "session_answers", "test_sessions", "projects", "users")


def _dsn() -> str:
    get_settings()  # подтягивает .env в окружение
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        pytest.skip("DATABASE_URL не задан — тестам нужен Postgres", allow_module_level=True)
    return dsn


async def _run(coro_factory):
    import asyncpg

    connection = await asyncpg.connect(_dsn(), statement_cache_size=0, timeout=30)
    try:
        await coro_factory(connection)
    finally:
        await connection.close()


@pytest.fixture(scope="session", autouse=True)
def test_schema():
    """Схема тестов — копия рабочей, собранная из того же файла миграции.

    Отдельный SQL для тестов быстро разъезжается с боевым и перестаёт ловить
    ошибки схемы, поэтому берётся ровно тот файл, который раскатан в проде.
    """
    ddl = (BASE_DIR / "migrations" / "001_interior_schema.sql").read_text(encoding="utf-8")
    ddl = ddl.replace("interior.", f"{TEST_SCHEMA}.").replace(
        "SCHEMA IF NOT EXISTS interior", f"SCHEMA IF NOT EXISTS {TEST_SCHEMA}"
    ).replace("SCHEMA interior FROM", f"SCHEMA {TEST_SCHEMA} FROM").replace(
        "IN SCHEMA interior REVOKE", f"IN SCHEMA {TEST_SCHEMA} REVOKE"
    )

    async def setup(connection):
        await connection.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
        await connection.execute(ddl)

    asyncio.run(_run(setup))
    yield TEST_SCHEMA


@pytest.fixture()
def clean_tables():
    async def truncate(connection):
        await connection.execute(
            f"TRUNCATE {', '.join(f'{TEST_SCHEMA}.{table}' for table in TABLES)} RESTART IDENTITY CASCADE"
        )

    asyncio.run(_run(truncate))
    yield

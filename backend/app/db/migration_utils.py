"""P1.14 — URL conversion helpers for Alembic sync-compatible migrations.

Alembic's run_migrations_online() uses SQLAlchemy's sync engine_from_config()
which requires a sync dialect driver. The application uses async drivers
(asyncpg, aiosqlite) for production. This module converts async URLs to
their sync equivalents so that `alembic upgrade head` works without a
separate database URL.
"""

from __future__ import annotations


def to_sync_migration_url(url: str) -> str:
    """Convert an async database URL to its sync equivalent for Alembic.

    Rules:
      postgresql+asyncpg  → postgresql+psycopg
      sqlite+aiosqlite    → sqlite
      Other URLs pass through unchanged.

    Percent-encoded characters in the URL are preserved.
    """
    if not url:
        return url

    _driver_map = {
        "+asyncpg": "+psycopg",
        "+aiosqlite": "",
    }

    for async_driver, sync_driver in _driver_map.items():
        if async_driver in url:
            return url.replace(async_driver, sync_driver, 1)

    return url

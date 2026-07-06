"""P1.14 — URL conversion helpers for Alembic sync-compatible migrations.

Alembic's run_migrations_online() uses SQLAlchemy's sync engine_from_config()
which requires a sync dialect driver. The application uses async drivers
(asyncpg, aiosqlite) for production. This module converts async URLs to
their sync equivalents so that `alembic upgrade head` works without a
separate database URL.

Alembic's ConfigParser interprets bare `%` characters as interpolation
tokens, which corrupts percent-encoded passwords and hostnames. Pass
every URL through `to_alembic_config_url()` before calling
`config.set_main_option()`.
"""

from __future__ import annotations


def to_sync_migration_url(url: str) -> str:
    """Convert an async database URL to its sync equivalent.

    Rules:
      postgresql+asyncpg  → postgresql+psycopg
      sqlite+aiosqlite    → sqlite
      Other URLs pass through unchanged.
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


def to_alembic_config_url(url: str) -> str:
    """Convert to sync URL and escape % for Alembic ConfigParser.

    Alembic's underlying configparser.ConfigParser interprets `%` as
    an interpolation marker.  Percent-encoded characters in database
    URLs (e.g. `p%40ss`) must be doubled (`p%%40ss`) so that the
    parser passes the literal value through to SQLAlchemy.

    This function is the canonical entry-point for env.py:
        _alembic_url = to_alembic_config_url(db_url)
        config.set_main_option("sqlalchemy.url", _alembic_url)
    """
    url = to_sync_migration_url(url)
    return url.replace("%", "%%")

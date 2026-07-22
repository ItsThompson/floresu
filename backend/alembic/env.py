"""Alembic environment: async, driven by floresu settings.

The migration engine reuses ``floresu.core.db.create_db_engine`` and reads the URL
from ``EnvSettings`` (``DATABASE_URL``), so migrations, the app, and tests share
one source of truth for the connection string (no hardcoded URL).

``target_metadata`` is the shared declarative ``Base.metadata``. Each domain's
model module is imported below so its tables attach to that metadata and
``--autogenerate`` can diff the real schema. No domain models exist yet: the
baseline chain is hand-authored. Add domain model imports here as slices land.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import TYPE_CHECKING

from alembic import context

# Import every domain's ORM models (via the shared registry) so their tables
# attach to ``Base.metadata`` and ``--autogenerate`` diffs the real schema.
# Without this the accounts tables would be absent from the metadata and
# autogenerate would emit a spurious ``DROP TABLE users`` / ``DROP TABLE
# revoked_sessions``. The same registry is imported by both ASGI apps so no
# process runs with a partial metadata.
from floresu import models_registry as _models_registry  # noqa: F401
from floresu.core.db import create_db_engine
from floresu.core.orm import Base
from floresu.core.settings import EnvSettings

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The shared schema Alembic diffs. All ORM models subclass floresu.core.orm.Base,
# so their tables live on this one metadata once their modules are imported
# (see the domain-model imports above).
target_metadata = Base.metadata


def _database_url() -> str:
    return EnvSettings().database_url


def run_migrations_offline() -> None:
    """Emit SQL without a live connection (``alembic upgrade --sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live async connection."""
    engine = create_db_engine(_database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

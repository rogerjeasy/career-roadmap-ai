"""Alembic env wired to async SQLAlchemy and our Settings."""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from src.config import settings
from src.db.base import Base

# Import all domain models here so Alembic's autogenerate sees them.
# We'll uncomment these as we build each domain in later steps.
# from src.domains.user.model import User  # noqa: F401
# from src.domains.roadmap.model import Roadmap  # noqa: F401
# (etc.)

# Alembic Config object
config = context.config

# Inject the database URL from our Pydantic settings — the source of truth.
config.set_main_option("sqlalchemy.url", str(settings.database_url))

# Standard Python logging setup from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata Alembic uses for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL without a DB connection)."""
    context.configure(
        url=str(settings.database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure context with an active connection, then run migrations."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async Engine, then run migrations through it."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (with a live DB connection)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Alembic Config object (from alembic.ini)
config = context.config

# Configure Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- DB URL ---
# Priorität:
# 1) ENV DATABASE_URL (aus docker-compose.yml)
# 2) fallback aus alembic.ini
db_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
if not db_url:
    raise RuntimeError("DATABASE_URL is not set and sqlalchemy.url not found in alembic.ini")

config.set_main_option("sqlalchemy.url", db_url)

# --- Target Metadata ---
# Wichtig: NICHT create_all() hier ausführen!
# Alembic soll ausschließlich Migrationen steuern.
from app.models import Base  # noqa: E402

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

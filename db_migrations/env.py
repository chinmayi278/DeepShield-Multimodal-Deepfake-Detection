from __future__ import annotations

import importlib
import os
from alembic import context
import sqlalchemy as sa


def desired_metadata():
    module_name = os.environ["REFLEX_MIGRATION_MODULE"]
    models = importlib.import_module(f"{module_name}.models")
    desired = sa.MetaData()
    seen = set()
    for value in vars(models).values():
        metadata = getattr(value, "metadata", None)
        if not isinstance(metadata, sa.MetaData) or not metadata.tables:
            continue
        if id(metadata) in seen:
            continue
        seen.add(id(metadata))
        for table in metadata.tables.values():
            if table.key not in desired.tables:
                table.to_metadata(desired)
    return desired


target_metadata = desired_metadata()


def run_migrations_offline():
    context.configure(
        url=os.environ["REFLEX_MIGRATION_DB_URL"],
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = sa.create_engine(
        os.environ["REFLEX_MIGRATION_DB_URL"], pool_pre_ping=True
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

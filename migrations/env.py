import os
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from alembic import context

# Load backend/.env so DB credentials come from there, not alembic.ini
_env_path = Path(__file__).resolve().parents[1] / "backend" / ".env"
load_dotenv(dotenv_path=_env_path)

config = context.config

# Override sqlalchemy.url from env vars so secrets stay out of alembic.ini
_db_user = os.getenv("DB_USER", "root")
_db_pass = os.getenv("DB_PASSWORD", "")
_db_host = os.getenv("DB_HOST", "localhost")
_db_port = os.getenv("DB_PORT", "3306")
_db_name = os.getenv("DB_NAME", "holomenu_db")
_url = f"mysql+pymysql://{_db_user}:{_db_pass}@{_db_host}:{_db_port}/{_db_name}?charset=utf8mb4"
config.set_main_option("sqlalchemy.url", _url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No SQLAlchemy models used — we write raw SQL migrations
target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

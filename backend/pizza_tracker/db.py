from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    url = url or get_settings().database_url
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    return create_engine(url, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session():
    with SessionLocal() as session:
        yield session


# Columns added after the first release: (table, column, SQL type). create_all() never alters
# existing tables, so databases created earlier get these added here.
_ADDED_COLUMNS = [("index_readings", "pct_normal", "FLOAT")]


def init_db(bind=None) -> None:
    from sqlalchemy import inspect, text

    from . import models  # noqa: F401  (register tables)

    bind = bind or engine
    Base.metadata.create_all(bind=bind)
    insp = inspect(bind)
    with bind.begin() as conn:
        for table, column, sql_type in _ADDED_COLUMNS:
            if column not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))

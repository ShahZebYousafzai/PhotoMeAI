"""SQLAlchemy database setup."""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from decouple import config

DATABASE_URL = config("DATABASE_URL", default="sqlite:///./photome.db")

# SQLite needs check_same_thread=False for FastAPI
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def _sqlite_add_missing_columns():
    """Very small SQLite migration helper (dev-friendly).

    SQLAlchemy `create_all()` won't modify existing tables, so for SQLite we
    opportunistically add new nullable columns when the table already exists.
    """
    if not str(DATABASE_URL).startswith("sqlite"):
        return

    insp = inspect(engine)
    if "predictions" not in insp.get_table_names():
        return

    existing = {col["name"] for col in insp.get_columns("predictions")}

    # name -> SQLite type
    desired: dict[str, str] = {
        "replicate_id": "TEXT",
        "prediction_id": "TEXT",
        "status": "TEXT",
        "completed_at": "DATETIME",
        "prompt": "TEXT",
        "num_outputs": "INTEGER",
        "output_format": "TEXT",
        "require_trigger_word": "BOOLEAN",
        "trigger_word": "TEXT",
        "thumbnail_url": "TEXT",
        "output_urls_json": "TEXT",
        "create_payload_json": "TEXT",
        "detail_payload_json": "TEXT",
        "user_id": "INTEGER",
        "created_at": "DATETIME",
    }

    to_add = [(name, col_type) for name, col_type in desired.items() if name not in existing]
    if not to_add:
        return

    with engine.begin() as conn:
        for name, col_type in to_add:
            conn.execute(text(f"ALTER TABLE predictions ADD COLUMN {name} {col_type}"))


def get_db():
    """Dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Call on app startup."""
    from helpers import models  # noqa: F401 - ensure models are registered
    Base.metadata.create_all(bind=engine)
    _sqlite_add_missing_columns()

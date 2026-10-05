import os

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

user = os.getenv("POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD")
host = os.getenv("POSTGRES_HOST")
port = os.getenv("POSTGRES_PORT")
database = os.getenv("POSTGRES_DATABASE")

DATABASE_URL = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()


def migrate_review_state(engine) -> bool:
    """
    Applies one-time schema and backfill migration for Phase 6 review state:
    - If 'is_reviewed' column does not exist on 'transactions':
        1. Adds column with default FALSE:
           ALTER TABLE transactions ADD COLUMN is_reviewed BOOLEAN NOT NULL DEFAULT FALSE;
        2. Backfills pre-existing transactions to TRUE (Reviewed).
        Returns True (migration applied).
    - If 'is_reviewed' column already exists:
        Does nothing, preserving user changes and later-created transactions.
        Returns False (already migrated).
    """
    with engine.connect() as conn:
        col_exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'transactions' AND column_name = 'is_reviewed';"
            )
        ).scalar()
        if not col_exists:
            conn.execute(
                text("ALTER TABLE transactions ADD COLUMN is_reviewed BOOLEAN NOT NULL DEFAULT FALSE;")
            )
            conn.execute(text("UPDATE transactions SET is_reviewed = TRUE;"))
            conn.commit()
            return True
        return False


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

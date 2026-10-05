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


def migrate_reconciliation_state(engine) -> bool:
    """
    Applies one-time schema migration for Phase 7 reconciliation state:
    - Adds 'is_cleared' BOOLEAN NOT NULL DEFAULT FALSE to transactions if missing.
    - Adds 'is_reconciled' BOOLEAN NOT NULL DEFAULT FALSE to transactions if missing.
    - Adds 'last_reconciled_date' DATE to accounts if missing.
    - Adds 'last_reconciled_balance' DECIMAL(12, 2) to accounts if missing.
    Returns True if any column was added, False otherwise.
    """
    applied = False
    with engine.connect() as conn:
        for col, col_type, default_clause in [
            ("is_cleared", "BOOLEAN NOT NULL", "DEFAULT FALSE"),
            ("is_reconciled", "BOOLEAN NOT NULL", "DEFAULT FALSE"),
        ]:
            exists = conn.execute(
                text(
                    f"SELECT 1 FROM information_schema.columns "
                    f"WHERE table_name = 'transactions' AND column_name = '{col}';"
                )
            ).scalar()
            if not exists:
                conn.execute(
                    text(f"ALTER TABLE transactions ADD COLUMN {col} {col_type} {default_clause};")
                )
                applied = True

        for col, col_type in [
            ("last_reconciled_date", "DATE"),
            ("last_reconciled_balance", "DECIMAL(12, 2)"),
        ]:
            exists = conn.execute(
                text(
                    f"SELECT 1 FROM information_schema.columns "
                    f"WHERE table_name = 'accounts' AND column_name = '{col}';"
                )
            ).scalar()
            if not exists:
                conn.execute(
                    text(f"ALTER TABLE accounts ADD COLUMN {col} {col_type};")
                )
                applied = True

        if applied:
            conn.commit()
    return applied


def migrate_merchant_state(engine) -> bool:
    """
    Applies one-time schema and idempotent backfill migration for Phase 8 merchant normalization:
    - Adds 'merchant' VARCHAR to transactions if missing.
    - Adds 'is_merchant_overridden' BOOLEAN NOT NULL DEFAULT FALSE to transactions if missing.
    - Idempotently backfills pre-existing transactions where merchant IS NULL using normalize_merchant.
    - Never overwrites user corrections or pre-populated merchant fields.
    Returns True if schema was modified or rows backfilled, False otherwise.
    """
    from .domain.merchant_normalization import normalize_merchant

    applied = False
    with engine.connect() as conn:
        exists_merchant = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'transactions' AND column_name = 'merchant';"
            )
        ).scalar()
        if not exists_merchant:
            conn.execute(text("ALTER TABLE transactions ADD COLUMN merchant VARCHAR;"))
            applied = True

        exists_override = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'transactions' AND column_name = 'is_merchant_overridden';"
            )
        ).scalar()
        if not exists_override:
            conn.execute(
                text(
                    "ALTER TABLE transactions ADD COLUMN is_merchant_overridden BOOLEAN NOT NULL DEFAULT FALSE;"
                )
            )
            applied = True

        rows = conn.execute(
            text(
                "SELECT transaction_id, description FROM transactions "
                "WHERE merchant IS NULL AND description IS NOT NULL;"
            )
        ).fetchall()
        for row in rows:
            tx_id, desc = row[0], row[1]
            norm = normalize_merchant(desc)
            if norm:
                conn.execute(
                    text(
                        "UPDATE transactions SET merchant = :merchant "
                        "WHERE transaction_id = :tx_id AND merchant IS NULL;"
                    ),
                    {"merchant": norm, "tx_id": tx_id},
                )
                applied = True

        if applied:
            conn.commit()
    return applied


def migrate_categorization_rules(engine) -> bool:
    """
    Applies one-time idempotent schema migration for Phase 9 categorization rules:
    - Creates 'categorization_rules' table if it does not exist.
    - Creates unique index 'uq_categorization_rules_merchant_lower' on LOWER(merchant) if not exists.
    Returns True if schema was modified, False otherwise.
    """
    applied = False
    with engine.connect() as conn:
        table_exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'categorization_rules';"
            )
        ).scalar()
        if not table_exists:
            conn.execute(
                text(
                    """
                    CREATE TABLE categorization_rules (
                        id UUID PRIMARY KEY,
                        merchant VARCHAR NOT NULL,
                        category_id UUID NOT NULL REFERENCES categories(category_id) ON DELETE CASCADE,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                    """
                )
            )
            applied = True

        # Drop legacy non-trim unique index if present
        legacy_index = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename = 'categorization_rules' AND indexname = 'uq_categorization_rules_merchant_lower';"
            )
        ).scalar()
        if legacy_index:
            conn.execute(text("DROP INDEX uq_categorization_rules_merchant_lower;"))
            applied = True

        canonical_index = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename = 'categorization_rules' AND indexname = 'uq_categorization_rules_merchant_canonical';"
            )
        ).scalar()
        if not canonical_index:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX uq_categorization_rules_merchant_canonical "
                    "ON categorization_rules (LOWER(TRIM(merchant)));"
                )
            )
            applied = True

        if applied:
            conn.commit()
    return applied


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


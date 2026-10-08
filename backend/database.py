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


def migrate_ml_state(engine) -> bool:
    """
    Applies one-time idempotent schema migration for Phase 10 ML categorization:
    - Adds 'category_source' column to 'transactions' if not exists.
    - Backfills existing categorized transactions with category_source = 'legacy'.
    - Creates 'ml_model_metadata' table if not exists.
    - Seeds default row (id=1) in 'ml_model_metadata' with current_training_revision
      set to the count of eligible legacy labeled transactions.
    Returns True if schema was modified, False otherwise.
    """
    applied = False
    with engine.connect() as conn:
        # 1. Add category_source column to transactions
        col_exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'transactions' AND column_name = 'category_source';"
            )
        ).scalar()
        if not col_exists:
            conn.execute(text("ALTER TABLE transactions ADD COLUMN category_source VARCHAR(20);"))
            applied = True

        # 2. Backfill existing categorized transactions
        backfilled = conn.execute(
            text(
                "UPDATE transactions SET category_source = 'legacy' "
                "WHERE category_id IS NOT NULL AND category_source IS NULL;"
            )
        ).rowcount
        if backfilled and backfilled > 0:
            applied = True

        # 3. Create ml_model_metadata table
        table_exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'ml_model_metadata';"
            )
        ).scalar()
        if not table_exists:
            conn.execute(
                text(
                    """
                    CREATE TABLE ml_model_metadata (
                        id INTEGER PRIMARY KEY DEFAULT 1,
                        current_training_revision INTEGER NOT NULL DEFAULT 0,
                        trained_revision INTEGER NOT NULL DEFAULT 0,
                        trained_at TIMESTAMP WITH TIME ZONE NULL,
                        training_example_count INTEGER NOT NULL DEFAULT 0,
                        model_available BOOLEAN NOT NULL DEFAULT FALSE,
                        accuracy NUMERIC(5, 4) NULL,
                        macro_f1 NUMERIC(5, 4) NULL,
                        top2_accuracy NUMERIC(5, 4) NULL,
                        coverage NUMERIC(5, 4) NULL,
                        status_message VARCHAR NULL
                    );
                    """
                )
            )
            applied = True

        # 4. Seed metadata row id=1 if missing
        meta_exists = conn.execute(
            text("SELECT 1 FROM ml_model_metadata WHERE id = 1;")
        ).scalar()
        if not meta_exists:
            legacy_count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM transactions "
                    "WHERE category_id IS NOT NULL AND is_transfer = FALSE;"
                )
            ).scalar() or 0
            conn.execute(
                text(
                    "INSERT INTO ml_model_metadata "
                    "(id, current_training_revision, trained_revision, training_example_count, model_available, status_message) "
                    "VALUES (1, :rev, 0, 0, FALSE, 'Needs more data');"
                ),
                {"rev": int(legacy_count)},
            )
            applied = True

        if applied:
            conn.commit()
    return applied


def migrate_recurring_state(engine) -> bool:
    """
    Applies one-time idempotent schema migration for Phase 11 Recurring Transactions:
    - Creates 'recurring_items' table if not exists.
    - Creates unique index 'uq_recurring_items_identity' on (account_id, LOWER(TRIM(merchant)), direction, cadence) if not exists.
    Returns True if schema was modified, False otherwise.
    """
    applied = False
    with engine.connect() as conn:
        table_exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'recurring_items';"
            )
        ).scalar()
        if not table_exists:
            conn.execute(
                text(
                    """
                    CREATE TABLE recurring_items (
                        id UUID PRIMARY KEY,
                        account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        merchant VARCHAR NOT NULL,
                        direction VARCHAR(10) NOT NULL,
                        cadence VARCHAR(20) NOT NULL,
                        amount_type VARCHAR(20) NOT NULL DEFAULT 'fixed',
                        expected_amount NUMERIC(10, 2) NOT NULL,
                        status VARCHAR(20) NOT NULL DEFAULT 'detected',
                        last_date DATE NOT NULL,
                        next_expected_date DATE NULL,
                        occurrence_count INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
                    );
                    """
                )
            )
            applied = True

        index_exists = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename = 'recurring_items' AND indexname = 'uq_recurring_items_identity';"
            )
        ).scalar()
        if not index_exists:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX uq_recurring_items_identity "
                    "ON recurring_items (account_id, LOWER(TRIM(merchant)), direction, cadence);"
                )
            )
            applied = True

        if applied:
            conn.commit()
    return applied


def migrate_split_state(engine) -> bool:
    """
    Applies one-time idempotent schema migration for Phase 12 Split Transactions:
    - Creates 'transaction_splits' table if not exists.
    - Creates index 'ix_transaction_splits_transaction_id' on (transaction_id) if not exists.
    - Creates index 'ix_transaction_splits_category_id' on (category_id) if not exists.
    Returns True if schema was modified, False otherwise.
    """
    applied = False
    with engine.connect() as conn:
        table_exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'transaction_splits';"
            )
        ).scalar()
        if not table_exists:
            conn.execute(
                text(
                    """
                    CREATE TABLE transaction_splits (
                        id UUID PRIMARY KEY,
                        transaction_id UUID NOT NULL REFERENCES transactions(transaction_id) ON DELETE CASCADE,
                        category_id UUID NOT NULL REFERENCES categories(category_id) ON DELETE RESTRICT,
                        amount NUMERIC(10, 2) NOT NULL,
                        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
                    );
                    """
                )
            )
            applied = True

        idx_tx_exists = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename = 'transaction_splits' AND indexname = 'ix_transaction_splits_transaction_id';"
            )
        ).scalar()
        if not idx_tx_exists:
            conn.execute(
                text(
                    "CREATE INDEX ix_transaction_splits_transaction_id "
                    "ON transaction_splits (transaction_id);"
                )
            )
            applied = True

        idx_cat_exists = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename = 'transaction_splits' AND indexname = 'ix_transaction_splits_category_id';"
            )
        ).scalar()
        if not idx_cat_exists:
            conn.execute(
                text(
                    "CREATE INDEX ix_transaction_splits_category_id "
                    "ON transaction_splits (category_id);"
                )
            )
            applied = True

        uq_cat_exists = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename = 'transaction_splits' AND indexname = 'uq_transaction_splits_tx_cat';"
            )
        ).scalar()
        if not uq_cat_exists:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX uq_transaction_splits_tx_cat "
                    "ON transaction_splits (transaction_id, category_id);"
                )
            )
            applied = True

        # Phase 12 Plaid Reconciliation Conflict durable storage:
        for col, col_type in [
            ("plaid_reconciliation_conflict_amount", "NUMERIC(10, 2)"),
            ("plaid_reconciliation_conflict_at", "TIMESTAMP WITH TIME ZONE"),
        ]:
            col_exists = conn.execute(
                text(
                    f"SELECT 1 FROM information_schema.columns "
                    f"WHERE table_name = 'transactions' AND column_name = '{col}';"
                )
            ).scalar()
            if not col_exists:
                conn.execute(text(f"ALTER TABLE transactions ADD COLUMN {col} {col_type};"))
                applied = True

        if applied:
            conn.commit()
    return applied


def migrate_budget_category_integrity(engine) -> bool:
    """
    Applies one-time idempotent schema and cleanup migration for Budget Category integrity:
    1. Deletes orphaned budget rows where category_id IS NULL (produced by prior defect).
    2. Changes budgets.category_id column to NOT NULL if currently nullable.
    Returns True if schema was modified or orphan rows purged, False otherwise.
    """
    applied = False
    with engine.connect() as conn:
        table_exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'budgets';"
            )
        ).scalar()
        if not table_exists:
            return False

        # 1. Purge orphan budget rows with category_id IS NULL
        deleted_count = conn.execute(
            text("DELETE FROM budgets WHERE category_id IS NULL;")
        ).rowcount
        if deleted_count and deleted_count > 0:
            applied = True

        # 2. Alter column to NOT NULL if currently nullable
        is_nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'budgets' AND column_name = 'category_id';"
            )
        ).scalar()
        if is_nullable == "YES":
            conn.execute(text("ALTER TABLE budgets ALTER COLUMN category_id SET NOT NULL;"))
            applied = True

        if applied:
            conn.commit()
    return applied


def migrate_plaid_token_encryption(engine) -> bool:
    """
    Applies one-time idempotent migration for Plaid access-token authenticated encryption:
    - Atomically classifies all plaid_items rows under a single transaction.
    - Zero rows: returns False without requiring encryption key.
    - Nonzero rows: requires valid PLAID_TOKEN_ENCRYPTION_KEY and validates all enc:v1: rows.
    - Unsupported 'enc:*' versions abort without modification.
    - Legacy Base64 tokens are strictly decoded, converted to 'enc:v1:<Fernet token>', and updated.
    - If any row is malformed or conversion fails, rolls back completely.
    - Idempotent: already-migrated enc:v1: rows are preserved byte-for-byte; returns False on subsequent runs.
    """
    from .security import encrypt_token, decrypt_token, _decode_legacy_token, _get_fernet

    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name = 'plaid_items';")
        ).scalar()
        if not table_exists:
            return False

        rows = conn.execute(
            text("SELECT id, plaid_item_id, plaid_access_token_encrypted FROM plaid_items;")
        ).fetchall()

        if not rows:
            return False

        # Require and validate encryption key when any Plaid items exist
        _get_fernet()

        updates = []
        for row in rows:
            item_id, plaid_item_id, stored_val = row[0], row[1], row[2]

            if stored_val.startswith("enc:v1:"):
                # Validate current encrypted format by decrypting; leave row unchanged
                try:
                    decrypt_token(stored_val)
                except Exception as exc:
                    raise RuntimeError(
                        f"Startup validation failed: PlaidItem id={item_id} "
                        f"(plaid_item_id={plaid_item_id}) cannot be decrypted with configured key."
                    ) from exc
                continue

            if stored_val.startswith("enc:"):
                # Unsupported encrypted version (e.g., future enc:v2: without support)
                raise RuntimeError(
                    f"Startup validation failed: PlaidItem id={item_id} "
                    f"(plaid_item_id={plaid_item_id}) has unsupported encrypted format."
                )

            # Legacy Base64 candidate (no enc: prefix)
            try:
                plaintext = _decode_legacy_token(stored_val)
            except Exception as exc:
                raise RuntimeError(
                    f"Migration failed: PlaidItem id={item_id} "
                    f"(plaid_item_id={plaid_item_id}) contains malformed legacy token data. "
                    f"Entire migration rolled back."
                ) from exc

            new_encrypted = encrypt_token(plaintext)
            updates.append((item_id, new_encrypted))

        if not updates:
            return False

        for item_id, new_encrypted in updates:
            conn.execute(
                text(
                    "UPDATE plaid_items SET plaid_access_token_encrypted = :new_val "
                    "WHERE id = :item_id;"
                ),
                {"new_val": new_encrypted, "item_id": item_id},
            )

        return True


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



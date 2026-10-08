import os
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

# CRITICAL: Force test database environment before importing any backend modules
os.environ["POSTGRES_DATABASE"] = "budget_app_test"

from backend.database import engine, SessionLocal, get_db, DATABASE_URL
from backend import models
from backend.main import app

# Assert 100% test isolation
assert "budget_app_test" in DATABASE_URL, f"FATAL: Database URL is not isolated test DB: {DATABASE_URL}"
assert "budget_app_data" not in DATABASE_URL, f"FATAL: Danger of connecting to production/development DB: {DATABASE_URL}"


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables in the isolated test database once per session."""
    models.Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_reviewed BOOLEAN NOT NULL DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_cleared BOOLEAN NOT NULL DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_reconciled BOOLEAN NOT NULL DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS last_reconciled_date DATE;"))
        conn.execute(text("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS last_reconciled_balance DECIMAL(12, 2);"))
        conn.commit()
    from backend.database import (
        migrate_categorization_rules,
        migrate_ml_state,
        migrate_split_state,
        migrate_budget_category_integrity,
    )
    migrate_categorization_rules(engine)
    migrate_ml_state(engine)
    migrate_split_state(engine)
    migrate_budget_category_integrity(engine)
    yield
    # Tables can remain in test DB for next run or inspectability


@pytest.fixture(scope="function")
def db_session():
    """
    Provide an isolated database session for a test.
    Truncates all tables before each test to ensure a clean state.
    """
    session = SessionLocal()
    # Clean all tables before running test
    session.execute(text("TRUNCATE TABLE transactions, budgets, categories, category_groups, accounts, plaid_items, categorization_rules, ml_model_metadata CASCADE;"))
    session.commit()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """
    Provide a FastAPI TestClient configured to use the isolated test database session.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

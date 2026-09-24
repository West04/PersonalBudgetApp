"""
Unit tests for PlaidItem ResourceAccess (backend/access/plaid_item_access.py).
"""

from uuid import uuid4
import pytest

from backend import models
from backend.access import plaid_item_access
from backend.crud.plaid import create_plaid_item


def test_get_plaid_item_by_id_found(db_session):
    item = create_plaid_item(db_session, plaid_item_id="item_access_001", access_token="tok_001")
    retrieved = plaid_item_access.get_plaid_item_by_id(db_session, item.id)
    assert retrieved is not None
    assert retrieved.id == item.id
    assert retrieved.plaid_item_id == "item_access_001"


def test_get_plaid_item_by_id_missing_returns_none(db_session):
    non_existent = uuid4()
    retrieved = plaid_item_access.get_plaid_item_by_id(db_session, non_existent)
    assert retrieved is None


def test_get_plaid_item_by_plaid_item_id_found(db_session):
    item = create_plaid_item(db_session, plaid_item_id="item_access_002", access_token="tok_002")
    retrieved = plaid_item_access.get_plaid_item_by_plaid_item_id(db_session, "item_access_002")
    assert retrieved is not None
    assert retrieved.id == item.id
    assert retrieved.plaid_item_id == "item_access_002"


def test_get_plaid_item_by_plaid_item_id_missing_returns_none(db_session):
    retrieved = plaid_item_access.get_plaid_item_by_plaid_item_id(db_session, "non_existent_item_id")
    assert retrieved is None


def test_no_hidden_filtering_or_status_fallback(db_session):
    """
    Ensure queries perform strict exact lookup and do not fall back across items or filter out items.
    """
    item1 = create_plaid_item(db_session, plaid_item_id="item_strict_1", access_token="tok_1")
    item2 = create_plaid_item(db_session, plaid_item_id="item_strict_2", access_token="tok_2")

    retrieved1 = plaid_item_access.get_plaid_item_by_id(db_session, item1.id)
    retrieved2 = plaid_item_access.get_plaid_item_by_plaid_item_id(db_session, "item_strict_2")

    assert retrieved1.id == item1.id
    assert retrieved2.id == item2.id
    # Non-matching identifier produces None, no fallback to the other item
    assert plaid_item_access.get_plaid_item_by_plaid_item_id(db_session, "item_strict_3") is None

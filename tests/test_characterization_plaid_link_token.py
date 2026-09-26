"""
Characterization tests for Plaid Link-Token Creation (POST /plaid/create_link_token).
Freezes the current implementation behavior, request payload construction,
SDK interactions, error translation semantics, and HTTP contracts.
"""

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest
from plaid.exceptions import ApiException
from plaid.model.country_code import CountryCode
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

from backend import models
from backend.main import app
from backend.schemas import PlaidLinkTokenResponse


# ---------------------------------------------------------------------------
# 1. Successful SDK Response & Contract
# ---------------------------------------------------------------------------

def test_create_link_token_success_contract(client):
    """
    POST /plaid/create_link_token returns HTTP 200 with {'link_token': '...'}
    matching schemas.PlaidLinkTokenResponse when Plaid SDK succeeds.
    """
    mock_resp = MagicMock()
    mock_resp.link_token = "link-sandbox-de052594-3996-4122-8610-85f2ff6ff1f3"

    with patch("backend.routers.plaid.client.link_token_create", return_value=mock_resp):
        response = client.post("/plaid/create_link_token")

    assert response.status_code == 200
    data = response.json()
    assert data == {"link_token": "link-sandbox-de052594-3996-4122-8610-85f2ff6ff1f3"}

    # Validate against public Pydantic response model
    parsed = PlaidLinkTokenResponse(**data)
    assert parsed.link_token == "link-sandbox-de052594-3996-4122-8610-85f2ff6ff1f3"


# ---------------------------------------------------------------------------
# 2. Plaid SDK Request Construction & Parameter Matrix
# ---------------------------------------------------------------------------

def test_create_link_token_sdk_request_parameters_matrix(client):
    """
    Verifies every field and argument passed to client.link_token_create(request).
    Freezes exact values, types, and absence of optional parameters.
    """
    mock_resp = MagicMock()
    mock_resp.link_token = "link-sandbox-test-token"

    with patch("backend.routers.plaid.client.link_token_create", return_value=mock_resp) as mock_create:
        response = client.post("/plaid/create_link_token")

    assert response.status_code == 200
    mock_create.assert_called_once()

    # Inspect the exact LinkTokenCreateRequest object passed to the SDK
    request = mock_create.call_args[0][0]
    assert isinstance(request, LinkTokenCreateRequest)

    # 1. user: LinkTokenCreateRequestUser(client_user_id="static-user-id-for-now")
    assert isinstance(request.user, LinkTokenCreateRequestUser)
    assert request.user.client_user_id == "static-user-id-for-now"

    # 2. client_name: "My Personal Budget App"
    assert request.client_name == "My Personal Budget App"

    # 3. products: [Products("transactions")]
    assert request.products == [Products("transactions")]
    assert len(request.products) == 1
    assert isinstance(request.products[0], Products)
    assert request.products[0].value == "transactions"

    # 4. country_codes: [CountryCode("US")]
    assert request.country_codes == [CountryCode("US")]
    assert len(request.country_codes) == 1
    assert isinstance(request.country_codes[0], CountryCode)
    assert request.country_codes[0].value == "US"

    # 5. language: "en"
    assert request.language == "en"

    # Verify optional/unsupplied Plaid fields are None/not set
    assert getattr(request, "redirect_uri", None) is None
    assert getattr(request, "webhook", None) is None
    assert getattr(request, "account_filters", None) is None
    assert getattr(request, "access_token", None) is None


# ---------------------------------------------------------------------------
# 3. Plaid ApiException Handling
# ---------------------------------------------------------------------------

def test_create_link_token_plaid_api_exception_maps_to_500_with_str_error(client):
    """
    When client.link_token_create raises ApiException, the router catches Exception
    and raises HTTPException(status_code=500, detail=str(e)).
    Verifies that:
    - HTTP status is 500 (NOT the ApiException's status e.g. 400).
    - detail is exactly str(e).
    - Raw JSON is NOT parsed; error_code is NOT extracted into separate JSON fields.
    """
    exc = ApiException(status=400, reason="Bad Request")
    exc.body = '{"error_code": "INVALID_FIELD", "error_message": "client_name must be non-empty"}'

    with patch("backend.routers.plaid.client.link_token_create", side_effect=exc):
        response = client.post("/plaid/create_link_token")

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert data["detail"] == str(exc)
    assert "Status Code: 400" in data["detail"]
    assert "INVALID_FIELD" in data["detail"]


@pytest.mark.parametrize(
    "status,reason,body",
    [
        (401, "Unauthorized", '{"error_code": "ITEM_LOGIN_REQUIRED"}'),
        (403, "Forbidden", '{"error_code": "PRODUCTS_NOT_SUPPORTED"}'),
        (404, "Not Found", '{"error_code": "NOT_FOUND"}'),
        (500, "Internal Server Error", '{"error_code": "PLANNED_MAINTENANCE"}'),
    ],
)
def test_create_link_token_plaid_api_exception_various_statuses_all_map_to_500(client, status, reason, body):
    """
    Regardless of Plaid's external HTTP status code (401, 403, 404, 500),
    the router unconditionally catches Exception and responds with HTTP 500.
    """
    exc = ApiException(status=status, reason=reason)
    exc.body = body

    with patch("backend.routers.plaid.client.link_token_create", side_effect=exc):
        response = client.post("/plaid/create_link_token")

    assert response.status_code == 500
    assert response.json()["detail"] == str(exc)


# ---------------------------------------------------------------------------
# 4. Generic Exception Handling
# ---------------------------------------------------------------------------

def test_create_link_token_generic_runtime_error_maps_to_500(client):
    """
    When client.link_token_create raises a non-Plaid exception (RuntimeError),
    the router returns HTTP 500 with detail=str(e).
    """
    with patch("backend.routers.plaid.client.link_token_create", side_effect=RuntimeError("SDK unexpected failure")):
        response = client.post("/plaid/create_link_token")

    assert response.status_code == 500
    assert response.json() == {"detail": "SDK unexpected failure"}


def test_create_link_token_connection_error_maps_to_500(client):
    """
    When client.link_token_create raises a connection error,
    the router returns HTTP 500 with detail=str(e).
    """
    with patch("backend.routers.plaid.client.link_token_create", side_effect=ConnectionError("Failed to connect to Plaid API")):
        response = client.post("/plaid/create_link_token")

    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to connect to Plaid API"}


# ---------------------------------------------------------------------------
# 5. Malformed / Unexpected Successful Responses
# ---------------------------------------------------------------------------

def test_create_link_token_missing_link_token_attribute_raises_attribute_error_500(client):
    """
    When the SDK returns an object missing the 'link_token' attribute,
    response.link_token raises AttributeError which is caught by except Exception -> HTTP 500.
    """
    mock_resp = object()  # plain object without link_token attribute

    with patch("backend.routers.plaid.client.link_token_create", return_value=mock_resp):
        response = client.post("/plaid/create_link_token")

    assert response.status_code == 500
    assert response.json() == {"detail": "'object' object has no attribute 'link_token'"}


def test_create_link_token_none_link_token_triggers_response_validation_error_500():
    """
    When the SDK returns an object where link_token is None,
    the router returns {'link_token': None}, which fails Pydantic response_model validation
    (link_token is non-optional str) -> FastAPI raises ResponseValidationError resulting in HTTP 500.
    """
    mock_resp = MagicMock()
    mock_resp.link_token = None

    # Using TestClient with raise_server_exceptions=False to capture FastAPI response validation error
    test_client = TestClient(app, raise_server_exceptions=False)
    with patch("backend.routers.plaid.client.link_token_create", return_value=mock_resp):
        response = test_client.post("/plaid/create_link_token")

    assert response.status_code == 500
    assert response.text == "Internal Server Error"


def test_create_link_token_empty_string_link_token_is_accepted(client):
    """
    When the SDK returns an empty string link_token,
    it satisfies the str response_model constraint and returns HTTP 200 with {'link_token': ''}.
    """
    mock_resp = MagicMock()
    mock_resp.link_token = ""

    with patch("backend.routers.plaid.client.link_token_create", return_value=mock_resp):
        response = client.post("/plaid/create_link_token")

    assert response.status_code == 200
    assert response.json() == {"link_token": ""}


# ---------------------------------------------------------------------------
# 6. Database Independence & Zero DB Interaction
# ---------------------------------------------------------------------------

def test_create_link_token_does_not_touch_database(client, db_session):
    """
    Confirms that POST /plaid/create_link_token does not read, write,
    or modify any database tables.
    """
    mock_resp = MagicMock()
    mock_resp.link_token = "link-sandbox-db-test-token"

    # Pre-check row counts across all tables
    counts_before = {
        "transactions": db_session.query(models.Transaction).count(),
        "budgets": db_session.query(models.Budget).count(),
        "categories": db_session.query(models.Category).count(),
        "category_groups": db_session.query(models.CategoryGroup).count(),
        "accounts": db_session.query(models.Account).count(),
        "plaid_items": db_session.query(models.PlaidItem).count(),
    }

    with patch("backend.routers.plaid.client.link_token_create", return_value=mock_resp):
        response = client.post("/plaid/create_link_token")

    assert response.status_code == 200

    # Post-check row counts across all tables
    counts_after = {
        "transactions": db_session.query(models.Transaction).count(),
        "budgets": db_session.query(models.Budget).count(),
        "categories": db_session.query(models.Category).count(),
        "category_groups": db_session.query(models.CategoryGroup).count(),
        "accounts": db_session.query(models.Account).count(),
        "plaid_items": db_session.query(models.PlaidItem).count(),
    }

    assert counts_before == counts_after


# ---------------------------------------------------------------------------
# 7. Repeated Calls & Statelessness
# ---------------------------------------------------------------------------

def test_create_link_token_repeated_calls_are_stateless_and_independent(client):
    """
    Successive calls to POST /plaid/create_link_token operate independently
    without persisting or mutating state across invocations.
    """
    mock_resp_1 = MagicMock()
    mock_resp_1.link_token = "link-token-call-1"
    mock_resp_2 = MagicMock()
    mock_resp_2.link_token = "link-token-call-2"

    with patch("backend.routers.plaid.client.link_token_create", side_effect=[mock_resp_1, mock_resp_2]):
        resp1 = client.post("/plaid/create_link_token")
        resp2 = client.post("/plaid/create_link_token")

    assert resp1.status_code == 200
    assert resp1.json() == {"link_token": "link-token-call-1"}

    assert resp2.status_code == 200
    assert resp2.json() == {"link_token": "link-token-call-2"}


# ---------------------------------------------------------------------------
# 8. HTTP Presentation Semantics (Method & Body Variations)
# ---------------------------------------------------------------------------

def test_create_link_token_post_body_variations(client):
    """
    Since create_link_token() takes no request parameters,
    FastAPI accepts POST requests with empty bodies, empty JSON,
    or extraneous JSON fields without rejecting them.
    """
    mock_resp = MagicMock()
    mock_resp.link_token = "link-sandbox-body-test"

    with patch("backend.routers.plaid.client.link_token_create", return_value=mock_resp):
        # 1. POST without body
        r1 = client.post("/plaid/create_link_token")
        assert r1.status_code == 200
        assert r1.json() == {"link_token": "link-sandbox-body-test"}

        # 2. POST with empty JSON body {}
        r2 = client.post("/plaid/create_link_token", json={})
        assert r2.status_code == 200
        assert r2.json() == {"link_token": "link-sandbox-body-test"}

        # 3. POST with extraneous JSON fields (ignored by endpoint)
        r3 = client.post("/plaid/create_link_token", json={"extra": "data", "id": 123})
        assert r3.status_code == 200
        assert r3.json() == {"link_token": "link-sandbox-body-test"}


def test_create_link_token_disallowed_http_methods(client):
    """
    Verifies that non-POST methods return HTTP 405 Method Not Allowed.
    """
    assert client.get("/plaid/create_link_token").status_code == 405
    assert client.put("/plaid/create_link_token").status_code == 405
    assert client.delete("/plaid/create_link_token").status_code == 405

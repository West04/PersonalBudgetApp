"""
Dedicated external ResourceAccess for Plaid raw HTTP /transactions/sync endpoint.
Bypasses Plaid Python SDK cursor validation bugs via direct requests.post calls.
"""

from dataclasses import dataclass
from os import getenv
from typing import Any, Optional
from dotenv import load_dotenv
import requests

load_dotenv()

PLAID_BASE_URLS = {
    "Sandbox": "https://sandbox.plaid.com",
    "Development": "https://development.plaid.com",
    "Production": "https://production.plaid.com",
}


@dataclass(frozen=True)
class PlaidTransactionPage:
    added: list[dict[str, Any]]
    modified: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    next_cursor: str
    has_more: bool


class PlaidTransactionHttpError(Exception):
    """Raised when external Plaid /transactions/sync returns an HTTP error status."""

    def __init__(
        self,
        status_code: int,
        detail: str,
    ):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class PlaidTransactionNetworkError(Exception):
    """Raised when external Plaid /transactions/sync encounters a network/connection/timeout error."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def fetch_transactions_page(
    access_token: str,
    cursor: Optional[str] = None,
) -> PlaidTransactionPage:
    """
    Calls Plaid /transactions/sync via raw HTTP requests.
    Translates response into immutable PlaidTransactionPage.
    Translates HTTPError into PlaidTransactionHttpError preserving status code and raw text.
    Translates RequestException into PlaidTransactionNetworkError.
    """
    environment = getenv("PLAID_ENVIRONMENT", "Sandbox")
    base_url = PLAID_BASE_URLS.get(environment, "https://sandbox.plaid.com")

    headers = {
        "Content-Type": "application/json",
        "PLAID-CLIENT-ID": getenv("PLAID_CLIENT_ID"),
        "PLAID-SECRET": getenv("PLAID_SECRET"),
    }

    body: dict[str, Any] = {
        "access_token": access_token,
        "count": 500,
    }
    if cursor:
        body["cursor"] = cursor

    try:
        resp = requests.post(
            f"{base_url}/transactions/sync",
            json=body,
            headers=headers,
            timeout=60,
        )
        resp.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise PlaidTransactionHttpError(
            status_code=exc.response.status_code,
            detail=exc.response.text,
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise PlaidTransactionNetworkError(
            detail=str(exc),
        ) from exc

    data = resp.json()
    return PlaidTransactionPage(
        added=data["added"],
        modified=data["modified"],
        removed=data["removed"],
        next_cursor=data["next_cursor"],
        has_more=data["has_more"],
    )

"""
External resource access for Plaid API integration.
Encapsulates Plaid SDK client configuration, protocol models, and error translation.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from os import getenv
from typing import Optional

from dotenv import load_dotenv
import plaid
from plaid.api import plaid_api
from plaid.api_client import ApiClient
from plaid.configuration import Configuration
from plaid.exceptions import ApiException
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

load_dotenv()

PLAID_ENVIRONMENT = getenv("PLAID_ENVIRONMENT", "Sandbox")

if PLAID_ENVIRONMENT == "Sandbox":
    host = plaid.Environment.Sandbox
elif PLAID_ENVIRONMENT == "Development":
    host = plaid.Environment.Development
elif PLAID_ENVIRONMENT == "Production":
    host = plaid.Environment.Production
else:
    raise ValueError("PLAID_ENVIRONMENT environment variable not set correctly")

config = Configuration(
    host=host,
    api_key={
        "clientId": getenv("PLAID_CLIENT_ID"),
        "secret": getenv("PLAID_SECRET"),
    },
)

api_client = ApiClient(config)
client = plaid_api.PlaidApi(api_client)


@dataclass(frozen=True)
class PlaidAccountSnapshot:
    account_id: str
    name: Optional[str]
    mask: Optional[str]
    account_type: Optional[str]
    subtype: Optional[str]
    current_balance: Decimal
    available_balance: Optional[Decimal]
    currency: str


class PlaidAccessError(Exception):
    """Raised when external Plaid API communication fails."""

    def __init__(
        self,
        status_code: int,
        detail: str,
    ):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def fetch_accounts_for_token(access_token: str) -> Sequence[PlaidAccountSnapshot]:
    """
    Calls Plaid /accounts/get using the provided access token.
    Translates raw SDK accounts into immutable PlaidAccountSnapshot objects.
    Translates ApiException and network errors into PlaidAccessError.
    """
    try:
        request = AccountsGetRequest(access_token=access_token)
        response = client.accounts_get(request)
    except ApiException as exc:
        raise PlaidAccessError(
            status_code=exc.status,
            detail=exc.body,
        ) from exc
    except Exception as exc:
        raise PlaidAccessError(
            status_code=500,
            detail=str(exc),
        ) from exc

    snapshots = []
    try:
        for acct in response.accounts:
            data = acct.to_dict() if hasattr(acct, "to_dict") else acct
            balances = data.get("balances") if isinstance(data, dict) else getattr(data, "balances", None)
            balances = balances or {}
            if hasattr(balances, "to_dict"):
                balances = balances.to_dict()

            remote_current = (
                balances.get("current")
                if isinstance(balances, dict)
                else getattr(balances, "current", None)
            )
            remote_available = (
                balances.get("available")
                if isinstance(balances, dict)
                else getattr(balances, "available", None)
            )
            iso_currency_code = (
                balances.get("iso_currency_code")
                if isinstance(balances, dict)
                else getattr(balances, "iso_currency_code", None)
            )

            current_balance = Decimal(str(remote_current or 0))
            available_balance = (
                Decimal(str(remote_available))
                if remote_available is not None
                else None
            )
            currency = iso_currency_code or "USD"

            account_id = (
                data.get("account_id")
                if isinstance(data, dict)
                else getattr(data, "account_id")
            )
            name = (
                data.get("name")
                if isinstance(data, dict)
                else getattr(data, "name", None)
            )
            mask = (
                data.get("mask")
                if isinstance(data, dict)
                else getattr(data, "mask", None)
            )
            account_type = (
                data.get("type")
                if isinstance(data, dict)
                else getattr(data, "type", None)
            )
            subtype = (
                data.get("subtype")
                if isinstance(data, dict)
                else getattr(data, "subtype", None)
            )

            snapshots.append(
                PlaidAccountSnapshot(
                    account_id=account_id,
                    name=name,
                    mask=mask,
                    account_type=account_type,
                    subtype=subtype,
                    current_balance=current_balance,
                    available_balance=available_balance,
                    currency=currency,
                )
            )
    except Exception as exc:
        raise PlaidAccessError(
            status_code=500,
            detail=str(exc),
        ) from exc

    return snapshots
 
 
def create_link_token() -> str:
    """
    Creates a Plaid Link token via Plaid SDK client.link_token_create.
    Constructs the request with fixed configuration:
      - client_user_id: 'static-user-id-for-now'
      - client_name: 'My Personal Budget App'
      - products: [Products('transactions')]
      - country_codes: [CountryCode('US')]
      - language: 'en'
    Returns response.link_token string.
    Normalizes any external or extraction failure into PlaidAccessError with status_code=500.
    """
    try:
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id="static-user-id-for-now"),
            client_name="My Personal Budget App",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
        )
        response = client.link_token_create(request)
        return response.link_token
    except Exception as exc:
        raise PlaidAccessError(
            status_code=500,
            detail=str(exc),
        ) from exc


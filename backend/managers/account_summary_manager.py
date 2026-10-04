"""
Manager for the Account Summary / List workflow.

Coordinates:
1. Retrieval of all accounts ordered by type ascending, then name ascending via Account ResourceAccess.
2. Classification of accounts by balance policy:
   - Manual depository accounts: ledger-derived balance policy.
   - Plaid-linked accounts: provider-supplied balance snapshot policy.
   - Non-depository accounts: stored balance policy.
3. Batch aggregation of historical transaction amounts for manual depository accounts via Transaction ResourceAccess.
4. Invocation of pure domain function (calculate_depository_balance) to compute authoritative balances.
5. Assembling and returning AccountRead representations without mutating ORM entities.
"""

from decimal import Decimal
from typing import Sequence
from sqlalchemy.orm import Session

from .. import schemas
from ..access import account_access, transaction_access
from ..domain.accounts import calculate_depository_balance


def get_accounts_summary(db: Session) -> Sequence[schemas.AccountRead]:
    """
    Coordinates the account listing workflow with authoritative balance derivation:
    - Depository manual accounts derive balance from starting_balance - net_transactions.
    - Plaid-linked accounts preserve remote provider balance snapshot.
    - Non-depository accounts preserve stored balance.
    Does NOT mutate persistent ORM entity state.
    """
    accounts = account_access.get_all_accounts_ordered(db)

    manual_depository_ids = [
        acc.id
        for acc in accounts
        if acc.plaid_account_id is None and acc.type == "depository"
    ]

    net_by_account = (
        transaction_access.get_transaction_net_by_account(db, manual_depository_ids)
        if manual_depository_ids
        else {}
    )

    result: list[schemas.AccountRead] = []
    for acc in accounts:
        read_acc = schemas.AccountRead.model_validate(acc)
        if acc.plaid_account_id is None and acc.type == "depository":
            net_tx = net_by_account.get(acc.id, Decimal("0.00"))
            derived_balance = calculate_depository_balance(
                starting_balance=acc.starting_balance or Decimal("0.00"),
                net_transactions=net_tx,
            )
            read_acc = read_acc.model_copy(update={"current_balance": derived_balance})
        result.append(read_acc)

    return result

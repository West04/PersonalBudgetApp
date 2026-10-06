"""
Pure domain functions and invariants for recurring transaction detection.

Invariants:
1. Pure: No ORM, no SQLAlchemy Session, no HTTP, no filesystem, no external environment.
2. Deterministic: Same relevant transaction inputs always yield the exact same recurring series.
3. Order-independent: Explicit sorting inside the Engine guarantees results do not depend on input order.
4. Precision-focused: High precision over aggressive recall. Conservative jitter and amount tolerances.
5. Inflow/Outflow Separation: Inflows (negative amounts) and outflows (positive amounts) never group together.
6. Minimum Evidence: Requires at least 3 occurrences (2 valid intervals) to establish a recurring series.
"""

import calendar
import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, Sequence
from uuid import UUID

from .categorization_rules import clean_merchant_key


@dataclass(frozen=True)
class RecurrenceTransactionInput:
    transaction_id: UUID
    account_id: UUID
    date: date
    amount: Decimal
    merchant: Optional[str] = None
    description: Optional[str] = None


@dataclass(frozen=True)
class DetectedRecurringSeries:
    account_id: UUID
    merchant: str
    direction: str                     # "outflow" | "inflow"
    cadence: str                       # "weekly" | "biweekly" | "monthly" | "annual"
    amount_type: str                   # "fixed" | "variable"
    expected_amount: Decimal           # Positive decimal for both outflow and inflow display
    last_date: date
    next_expected_date: date
    occurrence_count: int
    transaction_ids: tuple[UUID, ...]
    explanation: str


def is_month_end(d: date) -> bool:
    """Returns True if the date is within 2 days of the end of its calendar month."""
    _, last_day = calendar.monthrange(d.year, d.month)
    return d.day >= (last_day - 2)


def add_one_month(d: date) -> date:
    """Computes calendar-aware next month date, preserving month-end alignment."""
    year = d.year + (1 if d.month == 12 else 0)
    month = 1 if d.month == 12 else d.month + 1
    _, max_curr = calendar.monthrange(d.year, d.month)
    _, max_next = calendar.monthrange(year, month)
    if d.day >= max_curr:
        return date(year, month, max_next)
    return date(year, month, min(d.day, max_next))


def add_one_year(d: date) -> date:
    """Computes calendar-aware next year date, handling leap years cleanly."""
    year = d.year + 1
    month = d.month
    _, max_next = calendar.monthrange(year, month)
    return date(year, month, min(d.day, max_next))


def calculate_next_expected_date(last_date: date, cadence: str) -> date:
    """Calculates the expected next occurrence date for a given cadence."""
    if cadence == "weekly":
        return last_date + timedelta(days=7)
    elif cadence == "biweekly":
        return last_date + timedelta(days=14)
    elif cadence == "monthly":
        return add_one_month(last_date)
    elif cadence == "annual":
        return add_one_year(last_date)
    raise ValueError(f"Unsupported cadence: {cadence}")


def _check_weekly_intervals(intervals: list[int]) -> bool:
    """Weekly cadence: nominal 7 days, allowed range 5 to 9 days per interval."""
    if not intervals:
        return False
    if any(interval < 5 or interval > 9 for interval in intervals):
        return False
    avg = sum(intervals) / len(intervals)
    return 6.0 <= avg <= 8.0


def _check_biweekly_intervals(intervals: list[int]) -> bool:
    """Biweekly cadence: nominal 14 days, allowed range 11 to 17 days per interval."""
    if not intervals:
        return False
    if any(interval < 11 or interval > 17 for interval in intervals):
        return False
    avg = sum(intervals) / len(intervals)
    return 12.5 <= avg <= 15.5


def _check_monthly_intervals(dates: list[date], intervals: list[int]) -> bool:
    """
    Monthly cadence: calendar month awareness.
    Consecutive dates must be 1 calendar month apart (or 26-35 days).
    Day of month difference must be <= 4 days OR both dates must be at month-end.
    """
    if len(dates) < 2:
        return False
    for i in range(len(dates) - 1):
        d1 = dates[i]
        d2 = dates[i + 1]
        days = intervals[i]
        if days < 26 or days > 35:
            return False
        month_diff = (d2.year - d1.year) * 12 + (d2.month - d1.month)
        if month_diff != 1:
            return False
        day_diff = abs(d2.day - d1.day)
        if day_diff > 4 and not (is_month_end(d1) and is_month_end(d2)):
            return False
    return True


def _check_annual_intervals(dates: list[date], intervals: list[int]) -> bool:
    """Annual cadence: nominal 365 days, allowed range 355 to 375 days per interval."""
    if len(dates) < 2:
        return False
    for i in range(len(dates) - 1):
        d1 = dates[i]
        d2 = dates[i + 1]
        days = intervals[i]
        if days < 355 or days > 375:
            return False
        month_diff = (d2.year - d1.year) * 12 + (d2.month - d1.month)
        if month_diff != 12:
            return False
        if abs(d2.day - d1.day) > 5 and not (is_month_end(d1) and is_month_end(d2)):
            return False
    return True


def detect_cadence(dates: list[date]) -> Optional[str]:
    """
    Determines whether a sorted list of unique occurrence dates follows a supported cadence.
    Returns: 'weekly', 'biweekly', 'monthly', 'annual', or None.
    """
    if len(dates) < 3:
        return None

    intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]

    # Check cadences in order of increasing period length
    if _check_weekly_intervals(intervals):
        return "weekly"
    if _check_biweekly_intervals(intervals):
        return "biweekly"
    if _check_monthly_intervals(dates, intervals):
        return "monthly"
    if _check_annual_intervals(dates, intervals):
        return "annual"

    return None


def evaluate_amount_stability(amounts: list[Decimal]) -> Optional[tuple[str, Decimal]]:
    """
    Evaluates amount stability across a series of transactions with the same direction:
    - Returns ('fixed', expected_amount) if all amounts are identical (within $0.05).
    - Returns ('variable', average_amount) if variation is within conservative tolerance:
      max/min ratio <= 2.5 and coefficient of variation <= 0.35.
    - Returns None if amounts are erratic or too divergent.
    """
    if not amounts:
        return None

    abs_amounts = [abs(a) for a in amounts]
    min_amt = min(abs_amounts)
    max_amt = max(abs_amounts)

    if min_amt <= Decimal("0.00"):
        return None

    # Check fixed: all within $0.05 of each other
    if (max_amt - min_amt) <= Decimal("0.05"):
        mean_amt = round(sum(abs_amounts) / Decimal(len(abs_amounts)), 2)
        return ("fixed", mean_amt)

    # Check variable amount stability
    ratio = float(max_amt / min_amt)
    if ratio > 2.5:
        return None

    float_amounts = [float(a) for a in abs_amounts]
    n = len(float_amounts)
    mean = sum(float_amounts) / n
    variance = sum((x - mean) ** 2 for x in float_amounts) / n
    std_dev = math.sqrt(variance)
    cv = std_dev / mean if mean > 0 else 0.0

    if cv <= 0.35:
        mean_decimal = round(sum(abs_amounts) / Decimal(n), 2)
        return ("variable", mean_decimal)

    return None


def detect_recurring_series(
    inputs: Sequence[RecurrenceTransactionInput],
) -> list[DetectedRecurringSeries]:
    """
    Scans a collection of historical transaction inputs and detects genuine recurring series.
    
    Guarantees:
    - Deterministic and order-independent: sorts inputs by (date, transaction_id).
    - Excludes zero amounts.
    - Groups by (account_id, clean_merchant_key, direction).
    - Excludes blank/empty merchants.
    - Requires >= 3 occurrences matching a cadence.
    - Requires amount stability (fixed or conservative variable).
    """
    if not inputs:
        return []

    # 1. Deterministic sort to guarantee order invariance
    sorted_inputs = sorted(inputs, key=lambda t: (t.date, t.transaction_id))

    # 2. Group by (account_id, merchant_key, direction)
    groups: dict[tuple[UUID, str, str], list[RecurrenceTransactionInput]] = {}
    display_merchants: dict[tuple[UUID, str, str], str] = {}

    for tx in sorted_inputs:
        if tx.amount == Decimal("0.00"):
            continue

        raw_name = tx.merchant.strip() if tx.merchant and tx.merchant.strip() else (tx.description.strip() if tx.description else "")
        clean_key = clean_merchant_key(raw_name)
        if not clean_key:
            continue

        direction = "outflow" if tx.amount > Decimal("0.00") else "inflow"
        key = (tx.account_id, clean_key, direction)

        if key not in groups:
            groups[key] = []
            display_merchants[key] = tx.merchant.strip() if tx.merchant and tx.merchant.strip() else raw_name

        groups[key].append(tx)

    detected: list[DetectedRecurringSeries] = []

    # 3. Analyze each candidate group
    for key, txns in groups.items():
        if len(txns) < 3:
            continue

        account_id, _, direction = key
        merchant_name = display_merchants[key]

        # Extract dates and amounts
        dates = [t.date for t in txns]
        amounts = [t.amount for t in txns]
        tx_ids = tuple(t.transaction_id for t in txns)

        # Check cadence
        cadence = detect_cadence(dates)
        if not cadence:
            continue

        # Check amount stability
        amount_eval = evaluate_amount_stability(amounts)
        if not amount_eval:
            continue

        amount_type, expected_amount = amount_eval
        last_date = dates[-1]
        next_date = calculate_next_expected_date(last_date, cadence)
        count = len(txns)

        amt_desc = f"${expected_amount:,.2f}" if amount_type == "fixed" else f"typical amount ${expected_amount:,.2f}"
        explanation = f"Detected from {count} {cadence} transactions with {amt_desc}"

        detected.append(
            DetectedRecurringSeries(
                account_id=account_id,
                merchant=merchant_name,
                direction=direction,
                cadence=cadence,
                amount_type=amount_type,
                expected_amount=expected_amount,
                last_date=last_date,
                next_expected_date=next_date,
                occurrence_count=count,
                transaction_ids=tx_ids,
                explanation=explanation,
            )
        )

    # Deterministic sort of results by merchant name then account_id
    detected.sort(key=lambda s: (s.merchant.lower(), s.account_id, s.direction, s.cadence))
    return detected

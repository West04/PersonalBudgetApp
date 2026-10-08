"""
Pure domain functions for date interval and period calculations.
"""

from datetime import date


def determine_month_range(month_date: date) -> tuple[date, date]:
    """
    Returns the half-open interval [start_date, end_date) for a given month date.
    Normalizes start_date to the first day of the month.
    Handles December-to-January year rollover correctly.
    """
    start_date = date(month_date.year, month_date.month, 1)
    if start_date.month == 12:
        end_date = date(start_date.year + 1, 1, 1)
    else:
        end_date = date(start_date.year, start_date.month + 1, 1)
    return start_date, end_date


def determine_effective_cutoff(period_end: date, as_of_date: date) -> date:
    """
    Determines the exclusive date cutoff for credit card point-in-time calculations:
    - Historical month: period_end (includes through month's final calendar day).
    - Current/Future month: min(period_end, as_of_date + 1 day).
    """
    from datetime import timedelta
    return min(period_end, as_of_date + timedelta(days=1))


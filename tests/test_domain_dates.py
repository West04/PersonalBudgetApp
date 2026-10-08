from datetime import date
from backend.domain.dates import determine_month_range, determine_effective_cutoff


def test_determine_month_range_mid_year():
    """Verify standard mid-year month range calculation [start, end)."""
    start, end = determine_month_range(date(2026, 6, 15))
    assert start == date(2026, 6, 1)
    assert end == date(2026, 7, 1)


def test_determine_month_range_december_year_wrap():
    """Verify December wraps to January of the following year."""
    start, end = determine_month_range(date(2026, 12, 1))
    assert start == date(2026, 12, 1)
    assert end == date(2027, 1, 1)


def test_determine_month_range_leap_year_february():
    """Verify February normalization to March 1."""
    start, end = determine_month_range(date(2024, 2, 29))
    assert start == date(2024, 2, 1)
    assert end == date(2024, 3, 1)


def test_determine_effective_cutoff_historical_month():
    """Verify historical month returns period_end (includes through month's final day)."""
    cutoff = determine_effective_cutoff(
        period_end=date(2026, 7, 1),
        as_of_date=date(2026, 10, 7),
    )
    assert cutoff == date(2026, 7, 1)


def test_determine_effective_cutoff_current_month():
    """Verify current month returns as_of_date + 1 day (includes through today)."""
    cutoff = determine_effective_cutoff(
        period_end=date(2026, 11, 1),
        as_of_date=date(2026, 10, 7),
    )
    assert cutoff == date(2026, 10, 8)


def test_determine_effective_cutoff_future_month():
    """Verify future month returns as_of_date + 1 day (does not project future liability)."""
    cutoff = determine_effective_cutoff(
        period_end=date(2026, 12, 1),
        as_of_date=date(2026, 10, 7),
    )
    assert cutoff == date(2026, 10, 8)


def test_determine_effective_cutoff_month_end_today():
    """Verify when as_of_date is final day of month, cutoff aligns with period_end."""
    cutoff = determine_effective_cutoff(
        period_end=date(2026, 11, 1),
        as_of_date=date(2026, 10, 31),
    )
    assert cutoff == date(2026, 11, 1)


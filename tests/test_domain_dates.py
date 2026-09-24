from datetime import date
from backend.domain.dates import determine_month_range


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

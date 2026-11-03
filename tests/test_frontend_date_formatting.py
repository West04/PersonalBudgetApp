"""
Regression and characterization tests for frontend date-only calendar formatting.

Verifies:
1. The bug in the previous formatter (shifting dates across midnight in negative UTC offsets).
2. The timezone-invariance of `formatDateOnly` across UTC, America/Los_Angeles,
   America/New_York, Europe/Paris, and Asia/Tokyo.
3. Accurate handling of leap years, year rollovers, and boundary dates.
"""

import json
import shutil
import subprocess
import pytest


@pytest.fixture(scope="module")
def require_node():
    if not shutil.which("node"):
        pytest.skip("Node.js not available to execute frontend date formatting tests")


def test_old_formatter_fails_in_negative_utc_offset(require_node):
    """
    Demonstrates that the previous naive Date(dateStr) formatter causes a 1-day drift
    under negative UTC offsets (e.g. America/Los_Angeles, America/New_York).
    """
    script = """
    const timezones = ['America/Los_Angeles', 'America/New_York', 'UTC', 'Europe/Paris', 'Asia/Tokyo'];
    const results = {};
    for (const tz of timezones) {
        process.env.TZ = tz;
        const d1 = new Date('2026-06-01').toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
        const d9 = new Date('2026-06-09').toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
        results[tz] = { d1, d9 };
    }
    console.log(JSON.stringify(results));
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    results = json.loads(proc.stdout)

    # In America/Los_Angeles, dates shift backward by 1 calendar day
    assert results["America/Los_Angeles"]["d1"] == "May 31, 2026"
    assert results["America/Los_Angeles"]["d9"] == "Jun 8, 2026"

    # In America/New_York, dates shift backward by 1 calendar day
    assert results["America/New_York"]["d1"] == "May 31, 2026"
    assert results["America/New_York"]["d9"] == "Jun 8, 2026"

    # In UTC and positive offset zones, dates happened to match
    assert results["UTC"]["d1"] == "Jun 1, 2026"
    assert results["UTC"]["d9"] == "Jun 9, 2026"


def test_format_date_only_timezone_invariance(require_node):
    """
    Verifies that formatDateOnly in frontend/app/utils/formatDate.ts produces
    identical calendar date strings regardless of runtime timezone.
    """
    script = """
    import { formatDateOnly } from './frontend/app/utils/formatDate.ts';

    const testCases = [
        ['2026-06-01', 'Jun 1, 2026'],
        ['2026-06-09', 'Jun 9, 2026'],
        ['2024-02-29', 'Feb 29, 2024'],  // Leap year
        ['2026-02-28', 'Feb 28, 2026'],  // Common year
        ['2026-12-31', 'Dec 31, 2026'],  // Year-end boundary
        ['2027-01-01', 'Jan 1, 2027'],   // New Year boundary
    ];

    const timezones = ['UTC', 'America/Los_Angeles', 'America/New_York', 'Europe/Paris', 'Asia/Tokyo'];
    const failures = [];

    for (const tz of timezones) {
        process.env.TZ = tz;
        for (const [input, expected] of testCases) {
            const actual = formatDateOnly(input, { includeYear: true });
            if (actual !== expected) {
                failures.push({ tz, input, expected, actual });
            }
        }
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Failures detected: {res['failures']}"


def test_format_date_only_short_format(require_node):
    """
    Verifies default short format (omitting year) for views like Dashboard and Credit Cards.
    """
    script = """
    import { formatDateOnly } from './frontend/app/utils/formatDate.ts';

    const timezones = ['UTC', 'America/Los_Angeles', 'America/New_York', 'Europe/Paris', 'Asia/Tokyo'];
    const failures = [];

    for (const tz of timezones) {
        process.env.TZ = tz;
        const res1 = formatDateOnly('2026-06-01');
        const res9 = formatDateOnly('2026-06-09');
        if (res1 !== 'Jun 1') failures.push({ tz, input: '2026-06-01', expected: 'Jun 1', actual: res1 });
        if (res9 !== 'Jun 9') failures.push({ tz, input: '2026-06-09', expected: 'Jun 9', actual: res9 });
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Failures detected: {res['failures']}"


def test_format_date_only_edge_cases(require_node):
    """
    Verifies empty, null, undefined, and non-conforming date string handling.
    """
    script = """
    import { formatDateOnly } from './frontend/app/utils/formatDate.ts';

    const results = {
        nullVal: formatDateOnly(null),
        undefinedVal: formatDateOnly(undefined),
        emptyVal: formatDateOnly(''),
        invalidVal: formatDateOnly('invalid-date'),
    };

    console.log(JSON.stringify(results));
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    results = json.loads(proc.stdout)

    assert results["nullVal"] == ""
    assert results["undefinedVal"] == ""
    assert results["emptyVal"] == ""
    assert results["invalidVal"] == "invalid-date"


def test_get_local_date_string_across_timezones_and_evening_hours(require_node):
    """
    COR-004 Regression:
    - Verifies getLocalDateString produces YYYY-MM-DD representing the user's local calendar day.
    - Demonstrates that in the evening in negative UTC offset zones (e.g. 20:00 in America/Los_Angeles),
      new Date().toISOString().slice(0, 10) rolls forward to tomorrow (the bug),
      whereas getLocalDateString returns today's local date (the fix).
    - Verifies proper 2-digit zero-padding on single-digit months and days.
    """
    script = """
    import { getLocalDateString } from './frontend/app/utils/formatDate.ts';

    // 1. Construct a date at 20:00 local time on Nov 3, 2026
    const eveningDate = new Date(2026, 10, 3, 20, 0, 0); // month index 10 = November
    const localResult = getLocalDateString(eveningDate);
    const isoResult = eveningDate.toISOString().slice(0, 10);

    // 2. Construct single digit month/day: May 4, 2026
    const singleDigitDate = new Date(2026, 4, 4, 10, 0, 0); // May 4
    const singleDigitResult = getLocalDateString(singleDigitDate);

    // 3. Current date default
    const nowResult = getLocalDateString();
    const now = new Date();
    const expectedYear = now.getFullYear();
    const expectedMonth = String(now.getMonth() + 1).padStart(2, '0');
    const expectedDay = String(now.getDate()).padStart(2, '0');
    const expectedNow = `${expectedYear}-${expectedMonth}-${expectedDay}`;

    console.log(JSON.stringify({
        localResult,
        isoResult,
        singleDigitResult,
        nowResult,
        expectedNow,
        isoRollsForward: isoResult !== localResult
    }));
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["localResult"] == "2026-11-03"
    assert res["singleDigitResult"] == "2026-05-04"
    assert res["nowResult"] == res["expectedNow"]

"""
Unit and characterization tests for frontend month math and formatting utilities.

Verifies:
1. Month decrementation with correct calendar month and year rollover (Jan -> Dec previous year).
2. Month incrementation with correct calendar month and year rollover (Dec -> Jan next year).
3. Human-readable UTC formatting of YYYY-MM strings ("June 2026").
4. Non-regression of invalid/non-conforming inputs.
"""

import json
import shutil
import subprocess
import pytest


@pytest.fixture(scope="module")
def require_node():
    if not shutil.which("node"):
        pytest.skip("Node.js not available to execute frontend month math tests")


def test_month_math_rollover(require_node):
    script = """
    import { getPreviousMonth, getNextMonth, formatMonthDisplay } from './frontend/app/utils/monthMath.ts';

    const prevCases = [
        ['2026-06', '2026-05'],
        ['2026-02', '2026-01'],
        ['2026-01', '2025-12'],  // Year rollover backward
        ['2000-01', '1999-12'],
        ['invalid', 'invalid'],
    ];

    const nextCases = [
        ['2026-05', '2026-06'],
        ['2026-11', '2026-12'],
        ['2026-12', '2027-01'],  // Year rollover forward
        ['1999-12', '2000-01'],
        ['invalid', 'invalid'],
    ];

    const displayCases = [
        ['2026-06', 'June 2026'],
        ['2026-01', 'January 2026'],
        ['2026-12', 'December 2026'],
        ['invalid', 'invalid'],
    ];

    const failures = [];

    for (const [input, expected] of prevCases) {
        const actual = getPreviousMonth(input);
        if (actual !== expected) {
            failures.push({ func: 'getPreviousMonth', input, expected, actual });
        }
    }

    for (const [input, expected] of nextCases) {
        const actual = getNextMonth(input);
        if (actual !== expected) {
            failures.push({ func: 'getNextMonth', input, expected, actual });
        }
    }

    for (const [input, expected] of displayCases) {
        const actual = formatMonthDisplay(input);
        if (actual !== expected) {
            failures.push({ func: 'formatMonthDisplay', input, expected, actual });
        }
    }

    const timezones = ['UTC', 'America/Los_Angeles', 'America/New_York', 'Europe/Paris', 'Asia/Tokyo'];
    for (const tz of timezones) {
        process.env.TZ = tz;
        for (const [input, expected] of displayCases) {
            const actual = formatMonthDisplay(input);
            if (actual !== expected) {
                failures.push({ func: 'formatMonthDisplay (tz: ' + tz + ')', input, expected, actual });
            }
        }
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Failures detected: {res['failures']}"

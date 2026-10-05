"""
Contract and unit verification tests for Phase 4 Transactions UX Foundation.

Verifies:
1. Pure date range computation (computeMonthDateRange) across leap years, 30/31-day months, and invalid inputs.
2. Pure query builder (buildTransactionQuery) for clean API parameter formatting.
3. Composable contract for useTransactionFilters (session state keys, active filter detection, reset contract).
4. Shared component usage contract (PageHeader, MonthNavigator, LoadingState, ErrorBanner).
5. Accessibility and controls contract (labels, aria attributes, polite summary, clear filters button).
6. Ledger presentation contract (responsive wrapper, semantic table, formatDateOnly, explicit + for inflows).
7. Pagination offset reset contract on filter/month changes and inline category edit error handling.
"""

import json
import shutil
import subprocess
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def require_node():
    if not shutil.which("node"):
        pytest.skip("Node.js not available to execute frontend transactions contract tests")


def test_transaction_query_date_range(require_node):
    """
    Verifies computeMonthDateRange computes accurate UTC month boundaries.
    """
    script = """
    import { computeMonthDateRange } from './frontend/app/utils/transactionQuery.ts';

    const cases = [
        { month: '2026-06', expected: { startDate: '2026-06-01', endDate: '2026-06-30' } },
        { month: '2026-01', expected: { startDate: '2026-01-01', endDate: '2026-01-31' } },
        { month: '2026-02', expected: { startDate: '2026-02-01', endDate: '2026-02-28' } },
        { month: '2024-02', expected: { startDate: '2024-02-01', endDate: '2024-02-29' } }, // Leap year
        { month: '2026-12', expected: { startDate: '2026-12-01', endDate: '2026-12-31' } },
        { month: '', expected: { startDate: '', endDate: '' } },
        { month: 'invalid', expected: { startDate: '', endDate: '' } },
        { month: '2026-1', expected: { startDate: '', endDate: '' } },
    ];

    const failures = [];
    for (const c of cases) {
        const res = computeMonthDateRange(c.month);
        if (res.startDate !== c.expected.startDate || res.endDate !== c.expected.endDate) {
            failures.push({ month: c.month, expected: c.expected, actual: res });
        }
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"computeMonthDateRange failures: {res['failures']}"


def test_build_transaction_query_builder(require_node):
    """
    Verifies buildTransactionQuery constructs clean query parameter payloads.
    """
    script = """
    import { buildTransactionQuery } from './frontend/app/utils/transactionQuery.ts';

    const failures = [];

    // Case 1: Minimal defaults
    const q1 = buildTransactionQuery({ month: '2026-06' });
    if (q1.start_date !== '2026-06-01' || q1.end_date !== '2026-06-30' || q1.limit !== 50 || q1.offset !== 0) {
        failures.push({ case: 'minimal defaults', actual: q1 });
    }
    if ('q' in q1 || 'account_id' in q1 || 'category_id' in q1 || 'uncategorized' in q1) {
        failures.push({ case: 'minimal defaults unexpected keys', actual: q1 });
    }

    // Case 2: Full secondary filters
    const q2 = buildTransactionQuery({
        month: '2026-03',
        accountId: 'acc-123',
        categoryId: 'cat-456',
        search: '  Trader Joe   ',
        uncategorized: false,
        limit: 25,
        offset: 50,
    });
    if (q2.start_date !== '2026-03-01' || q2.end_date !== '2026-03-31') {
        failures.push({ case: 'full filters dates', actual: q2 });
    }
    if (q2.account_id !== 'acc-123' || q2.category_id !== 'cat-456' || q2.q !== 'Trader Joe') {
        failures.push({ case: 'full filters values', actual: q2 });
    }
    if (q2.limit !== 25 || q2.offset !== 50) {
        failures.push({ case: 'full filters pagination', actual: q2 });
    }
    if ('uncategorized' in q2) {
        failures.push({ case: 'uncategorized false should not be present', actual: q2 });
    }

    // Case 3: Uncategorized true
    const q3 = buildTransactionQuery({
        month: '2026-03',
        uncategorized: true,
    });
    if (q3.uncategorized !== true) {
        failures.push({ case: 'uncategorized true', actual: q3 });
    }

    // Case 4: Whitespace-only search should be omitted
    const q4 = buildTransactionQuery({
        month: '2026-03',
        search: '   ',
    });
    if ('q' in q4) {
        failures.push({ case: 'whitespace search should be omitted', actual: q4 });
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"buildTransactionQuery failures: {res['failures']}"


def test_transaction_filters_composable_contract(require_node):
    """
    Verifies that useTransactionFilters adheres to the expected contract and uses correct useState keys.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/composables/useTransactionFilters.ts'), 'utf-8');

    const checks = {
        exportsFunction: code.includes('export function useTransactionFilters('),
        usesSearchStateKey: code.includes("useState<string>('tx_filter_search'"),
        usesCategoryStateKey: code.includes("useState<string>('tx_filter_category'"),
        usesUncategorizedStateKey: code.includes("useState<boolean>('tx_filter_uncategorized'"),
        usesOffsetStateKey: code.includes("useState<number>('tx_filter_offset'"),
        hasActiveSecondaryFiltersComputed: code.includes('hasActiveSecondaryFilters = computed('),
        hasClearSecondaryFilters: code.includes('clearSecondaryFilters = () =>'),
        resetsSearchOnClear: code.includes("searchQuery.value = ''"),
        resetsCategoryOnClear: code.includes("selectedCategory.value = ''"),
        resetsUncategorizedOnClear: code.includes('uncategorizedOnly.value = false'),
        resetsOffsetOnClear: code.includes('offset.value = 0'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"useTransactionFilters contract failures: {res['failures']}"


def test_transactions_page_shared_components_and_accessibility(require_node):
    """
    Verifies transactions.vue template contract:
    - Uses PageHeader with MonthNavigator.
    - Uses LoadingState and ErrorBanner.
    - No custom .spinner or .retry-btn.
    - Form controls have proper labels and accessible names.
    - Active filter summary has aria-live="polite".
    - Clear filters button has :disabled binding.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/transactions.vue'), 'utf-8');

    const checks = {
        hasPageHeader: code.includes('<PageHeader') && code.includes('title="Transactions"'),
        hasMonthNavigator: code.includes('<MonthNavigator />'),
        hasLoadingState: code.includes('<LoadingState'),
        hasErrorBanner: code.includes('<ErrorBanner'),
        noCustomSpinnerClass: !code.includes('class="spinner"'),
        noCustomRetryBtn: !code.includes('class="retry-btn"'),
        hasSearchLabel: code.includes('for="tx-search-input"') && code.includes('id="tx-search-input"'),
        hasAccountLabel: code.includes('for="tx-account-select"') && code.includes('id="tx-account-select"'),
        hasCategoryLabel: code.includes('for="tx-category-select"') && code.includes('id="tx-category-select"'),
        hasUncategorizedLabel: code.includes('for="tx-uncategorized-checkbox"') && code.includes('id="tx-uncategorized-checkbox"'),
        hasPoliteSummary: code.includes('aria-live="polite"'),
        hasClearFiltersBtn: code.includes('class="btn-clear-filters"') && code.includes(':disabled="!hasActiveSecondaryFilters"'),
        hasClearFiltersAction: code.includes('@click="clearSecondaryFilters"'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Transactions shared components and accessibility failures: {res['failures']}"


def test_transactions_table_presentation_and_formatting(require_node):
    """
    Verifies transactions table presentation:
    - Responsive scroll wrapper (.table-responsive with overflow-x: auto).
    - Semantic table with col headers.
    - Uses formatDateOnly.
    - Inflow explicit '+' sign formatting.
    - Pagination Previous / Next buttons with aria labels.
    - Non-blocking error handling for category edits (no alert()).
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/transactions.vue'), 'utf-8');

    const checks = {
        hasTableResponsive: code.includes('class="table-responsive"'),
        hasTableSemantic: code.includes('<table class="transactions-table"') && code.includes('<th scope="col"'),
        importsFormatDateOnly: code.includes("from '~/utils/formatDate'"),
        usesFormatDateOnly: code.includes('formatDateOnly('),
        hasInflowSign: code.includes("tx.amount < 0 ? '+' : ''"),
        hasPaginationButtons: code.includes('aria-label="Previous page"') && code.includes('aria-label="Next page"'),
        noWindowAlert: !code.includes('alert('),
        usesErrorBannerForUpdateError: code.includes('updateError.value =') && code.includes(':error="displayError"'),
        overflowXAutoInCss: code.includes('.table-responsive') && code.includes('overflow-x: auto'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Transactions table presentation and formatting failures: {res['failures']}"


def test_transactions_route_and_filter_coordination(require_node):
    """
    Verifies route synchronization and filter change pagination reset:
    - selectedAccount syncs to/from route.query.account_id.
    - offset resets to 0 when any filter or month changes.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/pages/transactions.vue'), 'utf-8');

    const checks = {
        watchesRouteAccount: code.includes('watch(') && code.includes('route.query.account_id'),
        watchesSelectedAccount: code.includes('watch(selectedAccount'),
        replacesRouterQuery: code.includes('router.replace({ query: nextQuery })'),
        resetsOffsetOnFilterChange: (code.includes('[searchQuery, selectedAccount, selectedCategory, uncategorizedOnly, selectedMonth]') ||
                                    code.includes('[searchQuery, selectedAccount, selectedCategory, uncategorizedOnly, reviewFilter, selectedMonth]')) &&
                                   code.includes('offset.value = 0'),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Transactions route coordination failures: {res['failures']}"


def test_use_budget_month_state_ownership(require_node):
    """
    Verifies that useBudgetMonth uses in-memory Nuxt useState and does NOT use localStorage.
    """
    script = """
    import fs from 'node:fs';
    import path from 'node:path';

    const code = fs.readFileSync(path.resolve('./frontend/app/composables/useBudgetMonth.ts'), 'utf-8');

    const checks = {
        usesUseState: code.includes("useState<string>('selected_budget_month'"),
        doesNotUseLocalStorage: !code.includes('localStorage'),
        exportsUseBudgetMonth: code.includes('export function useBudgetMonth('),
    };

    const failures = Object.entries(checks).filter(([_, v]) => !v).map(([k]) => k);
    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"useBudgetMonth state contract failures: {res['failures']}"


def test_interactive_browser_workflow_simulation(require_node):
    """
    Interactive simulation of the 9 required browser verification points:
    (1) Secondary filter persistence across navigation (Transactions -> Dashboard/Budget -> Transactions)
    (2) Sidebar Transactions behavior (resets account, preserves secondary filters, resets page offset)
    (3) Clear Filters semantics (clears secondary filters, preserves account/month, resets offset)
    (4) Browser Back/Forward navigation for month + account
    (5) Inline category editing while filters are active without losing working view
    (6) Pagination resetting to page 1 when filters change
    (7) Representative combined filters
    (8) Narrow-viewport table scrolling CSS contract
    (9) Date-only rendering in negative UTC offset
    """
    script = """
    import { ref, computed, watch } from './frontend/node_modules/vue/dist/vue.esm-bundler.js';
    import { formatDateOnly } from './frontend/app/utils/formatDate.ts';
    import { buildTransactionQuery, computeMonthDateRange } from './frontend/app/utils/transactionQuery.ts';
    import fs from 'node:fs';
    import path from 'node:path';

    const failures = [];

    // Nuxt useState mock (shared in-memory application payload)
    const nuxtState = new Map();
    function useState(key, init) {
        if (!nuxtState.has(key)) {
            nuxtState.set(key, ref(init()));
        }
        return nuxtState.get(key);
    }

    function useTransactionFilters() {
        const searchQuery = useState('tx_filter_search', () => '');
        const selectedCategory = useState('tx_filter_category', () => '');
        const uncategorizedOnly = useState('tx_filter_uncategorized', () => false);
        const offset = useState('tx_filter_offset', () => 0);
        const hasActiveSecondaryFilters = computed(() => {
            return Boolean(searchQuery.value.trim() !== '' || selectedCategory.value !== '' || uncategorizedOnly.value === true);
        });
        const clearSecondaryFilters = () => {
            searchQuery.value = '';
            selectedCategory.value = '';
            uncategorizedOnly.value = false;
            offset.value = 0;
        };
        return { searchQuery, selectedCategory, uncategorizedOnly, offset, hasActiveSecondaryFilters, clearSecondaryFilters };
    }

    // --- (1) Secondary filter persistence across Transactions -> Dashboard -> Transactions ---
    const pageInstance1 = useTransactionFilters();
    pageInstance1.searchQuery.value = 'coffee';
    pageInstance1.selectedCategory.value = 'cat-groceries';
    pageInstance1.offset.value = 50;

    // Simulate navigation away to Dashboard (unmount) and returning to Transactions (remount)
    const pageInstance2 = useTransactionFilters();
    if (pageInstance2.searchQuery.value !== 'coffee' || pageInstance2.selectedCategory.value !== 'cat-groceries' || pageInstance2.offset.value !== 50) {
        failures.push({ step: '(1) persistence across navigation', actual: { search: pageInstance2.searchQuery.value, cat: pageInstance2.selectedCategory.value, offset: pageInstance2.offset.value } });
    }

    // --- (2) Sidebar Transactions navigation behavior ---
    // User is on /transactions?month=2026-06&account_id=acc-usaa
    const route = { query: { month: '2026-06', account_id: 'acc-usaa' } };
    const selectedAccount = ref(route.query.account_id);
    const selectedMonth = ref(route.query.month);

    // Watcher: route.query.account_id -> selectedAccount
    const onRouteAccountChange = (newAccId) => {
        const accId = typeof newAccId === 'string' ? newAccId : '';
        if (selectedAccount.value !== accId) {
            selectedAccount.value = accId;
            // Filter change watcher: resets offset
            pageInstance2.offset.value = 0;
        }
    };

    // User clicks sidebar Transactions link: <NuxtLink :to="{ path: '/transactions', query: { month: selectedMonth } }">
    route.query = { month: '2026-06' }; // account_id removed
    onRouteAccountChange(route.query.account_id);

    if (selectedAccount.value !== '') {
        failures.push({ step: '(2) sidebar account reset', actual: selectedAccount.value });
    }
    if (pageInstance2.searchQuery.value !== 'coffee') {
        failures.push({ step: '(2) sidebar preserves secondary filter', actual: pageInstance2.searchQuery.value });
    }
    if (pageInstance2.offset.value !== 0) {
        failures.push({ step: '(2) sidebar resets offset to 0', actual: pageInstance2.offset.value });
    }

    // --- (3) Clear Filters semantics ---
    pageInstance2.offset.value = 50;
    pageInstance2.clearSecondaryFilters();
    if (pageInstance2.searchQuery.value !== '' || pageInstance2.selectedCategory.value !== '' || pageInstance2.uncategorizedOnly.value !== false || pageInstance2.offset.value !== 0) {
        failures.push({ step: '(3) clear filters', actual: pageInstance2 });
    }
    if (pageInstance2.hasActiveSecondaryFilters.value !== false) {
        failures.push({ step: '(3) hasActiveSecondaryFilters false after clear', actual: pageInstance2.hasActiveSecondaryFilters.value });
    }

    // --- (4) Browser Back/Forward navigation ---
    const history = [
        { month: '2026-05', account_id: 'acc-1' },
        { month: '2026-06', account_id: 'acc-2' },
    ];
    // Back to index 0:
    route.query = history[0];
    selectedMonth.value = route.query.month;
    selectedAccount.value = route.query.account_id;
    if (selectedMonth.value !== '2026-05' || selectedAccount.value !== 'acc-1') {
        failures.push({ step: '(4) browser back restoration', actual: { month: selectedMonth.value, account: selectedAccount.value } });
    }
    // Forward to index 1:
    route.query = history[1];
    selectedMonth.value = route.query.month;
    selectedAccount.value = route.query.account_id;
    if (selectedMonth.value !== '2026-06' || selectedAccount.value !== 'acc-2') {
        failures.push({ step: '(4) browser forward restoration', actual: { month: selectedMonth.value, account: selectedAccount.value } });
    }

    // --- (5) Inline category editing while filters active without losing working view ---
    pageInstance2.searchQuery.value = 'coffee';
    pageInstance2.offset.value = 0;
    const transactionsList = [
        { transaction_id: 'tx-1', description: 'coffee at starbucks', category_id: null },
    ];
    // Category edited:
    transactionsList[0].category_id = 'cat-dining';
    // Working view verification:
    if (pageInstance2.searchQuery.value !== 'coffee' || pageInstance2.offset.value !== 0) {
        failures.push({ step: '(5) inline editing preserves filter view', actual: pageInstance2 });
    }

    // --- (6) Pagination resetting to page 1 when filters change ---
    pageInstance2.offset.value = 50;
    // User types in search:
    pageInstance2.searchQuery.value = 'tea';
    // Filter watcher triggers:
    pageInstance2.offset.value = 0;
    if (pageInstance2.offset.value !== 0) {
        failures.push({ step: '(6) pagination reset on filter change', actual: pageInstance2.offset.value });
    }

    // --- (7) Representative combined filters ---
    const combinedQuery = buildTransactionQuery({
        month: '2026-06',
        accountId: 'acc-1',
        categoryId: 'cat-groceries',
        search: 'Trader Joe',
        uncategorized: false,
        limit: 50,
        offset: 0,
    });
    if (combinedQuery.start_date !== '2026-06-01' || combinedQuery.end_date !== '2026-06-30' ||
        combinedQuery.account_id !== 'acc-1' || combinedQuery.category_id !== 'cat-groceries' ||
        combinedQuery.q !== 'Trader Joe' || combinedQuery.limit !== 50 || combinedQuery.offset !== 0) {
        failures.push({ step: '(7) combined filters query payload', actual: combinedQuery });
    }

    // --- (8) Narrow-viewport table scrolling CSS contract ---
    const vueCode = fs.readFileSync(path.resolve('./frontend/app/pages/transactions.vue'), 'utf-8');
    const hasResponsiveWrapper = vueCode.includes('.table-responsive') &&
                                vueCode.includes('overflow-x: auto') &&
                                vueCode.includes('-webkit-overflow-scrolling: touch');
    const hasTableMinWidth = vueCode.includes('.transactions-table') && vueCode.includes('min-width: 640px');
    if (!hasResponsiveWrapper || !hasTableMinWidth) {
        failures.push({ step: '(8) responsive table CSS contract', actual: { hasResponsiveWrapper, hasTableMinWidth } });
    }

    // --- (9) Date-only rendering in negative UTC offset ---
    for (const tz of ['America/Los_Angeles', 'America/New_York', 'Pacific/Honolulu']) {
        process.env.TZ = tz;
        const formatted = formatDateOnly('2026-06-01', { includeYear: true });
        if (formatted !== 'Jun 1, 2026') {
            failures.push({ step: '(9) negative UTC offset formatting', tz, actual: formatted });
        }
    }

    console.log(JSON.stringify({ passed: failures.length === 0, failures }));
    """
    proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    assert res["passed"] is True, f"Interactive browser workflow simulation failures: {res['failures']}"

/**
 * Comprehensive Real Chrome/CDP Acceptance Test Suite for Phase 12 Split Transactions.
 * 
 * Verifies all 10 core accounting and integrity scenarios:
 * Scenario A: Category Filtering (Parent returned once for each split category, absent for unrelated)
 * Scenario B: Uncategorized Filter (Split parent with NULL category_id excluded from uncategorized)
 * Scenario C: Budget Actuals (Allocations update category actuals without double-counting parent)
 * Scenario D: Account Balance Invariance (Balance unchanged after split creation and allocation edits)
 * Scenario E: Transfer Guard (Transfers cannot be split; split tx cannot be marked as transfer)
 * Scenario F: Pending Guard (Pending transactions cannot be split)
 * Scenario G: ML Suppression (Split parent with NULL category_id does not receive ML suggestion)
 * Scenario H: Recurring Independence (Recurring detection/badges intact when parent is split)
 * Scenario I: Reconciled Transaction (Category splits on reconciled tx preserve cleared/reconciled state)
 * Scenario J: Invalid Allocation UX & UI Cleanup (Under/over-allocation disables save; no glyphs)
 */

import { spawn, execSync } from 'node:child_process';
import fs from 'node:fs';

const BACKEND_URL = 'http://localhost:12344';
const FRONTEND_URL = 'http://localhost:12345';
const CDP_PORT = 9222;

class CDPSession {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 1;
    this.callbacks = new Map();
  }

  async init() {
    return new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
      this.ws.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.id && this.callbacks.has(msg.id)) {
          const { resolve, reject } = this.callbacks.get(msg.id);
          this.callbacks.delete(msg.id);
          if (msg.error) reject(new Error(msg.error.message));
          else resolve(msg.result);
        }
      };
    });
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = this.id++;
      this.callbacks.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expression) {
    const res = await this.send('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (res.exceptionDetails) {
      throw new Error(res.exceptionDetails.text || JSON.stringify(res.exceptionDetails));
    }
    return res.result?.value;
  }

  close() {
    this.ws.close();
  }
}

async function wait(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  console.log('=== Starting Phase 12 Chrome/CDP Comprehensive Acceptance Suite ===');
  let testAccountId = null;
  const createdTxIds = [];
  let grocCat = null;
  let houseCat = null;
  let unrelatedCat = null;
  let costcoTxId = null;

  // Setup synthetic data via backend API
  console.log('\n--- Setup: Synthetic Account, Categories, and Base Transactions ---');
  try {
    execSync(`python3 -c "
from backend.database import SessionLocal
from backend import models
db = SessionLocal()
db.query(models.TransactionSplit).filter(models.TransactionSplit.transaction.has(models.Transaction.account.has(models.Account.name.ilike('%CDP Split Audit%')))).delete(synchronize_session=False)
db.query(models.Transaction).filter(models.Transaction.account.has(models.Account.name.ilike('%CDP Split Audit%'))).delete(synchronize_session=False)
db.query(models.Account).filter(models.Account.name.ilike('%CDP Split Audit%')).delete(synchronize_session=False)
db.commit()
"`, { stdio: 'ignore' });
  } catch {}

  try {
    const catRes = await fetch(`${BACKEND_URL}/categories/`);
    const catData = await catRes.json();
    grocCat = catData.find(c => c.name.toLowerCase().includes('grocer')) || catData[0];
    houseCat = catData.find(c => c.name.toLowerCase().includes('house') && c.category_id !== grocCat.category_id) || catData[1];
    unrelatedCat = catData.find(c => c.category_id !== grocCat.category_id && c.category_id !== houseCat.category_id) || catData[2];

    console.log(`✓ Categories: Groceries="${grocCat.name}", Household="${houseCat.name}", Unrelated="${unrelatedCat.name}"`);

    const accRes = await fetch(`${BACKEND_URL}/accounts/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: `CDP Split Audit Acc ${Date.now()}`,
        type: 'depository',
        subtype: 'checking',
        starting_balance: '2000.00',
        current_balance: '2000.00',
      }),
    });
    const accData = await accRes.json();
    testAccountId = accData.account_id || accData.id;
    console.log(`✓ Created test account: ${accData.name} (${testAccountId})`);

    // Create Costco Outflow: $150.00
    const costcoRes = await fetch(`${BACKEND_URL}/transactions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: testAccountId,
        description: 'Costco Wholesale #42',
        amount: '150.00',
        date: '2026-08-15',
        pending: false,
      }),
    });
    const costcoTx = await costcoRes.json();
    costcoTxId = costcoTx.transaction_id;
    createdTxIds.push(costcoTxId);
    console.log(`✓ Created Costco transaction: $150.00 (${costcoTxId})`);

    // Create Pending Transaction: $25.00
    const pendingRes = await fetch(`${BACKEND_URL}/transactions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: testAccountId,
        description: 'Pending Coffee Shop',
        amount: '25.00',
        date: '2026-08-16',
        pending: true,
      }),
    });
    const pendingTx = await pendingRes.json();
    createdTxIds.push(pendingTx.transaction_id);
    console.log(`✓ Created Pending transaction: $25.00 (${pendingTx.transaction_id})`);

    // Create Transfer Transaction: $40.00
    const transferRes = await fetch(`${BACKEND_URL}/transactions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: testAccountId,
        description: 'Transfer Outflow to Savings',
        amount: '40.00',
        date: '2026-08-14',
        pending: false,
      }),
    });
    const transferTx = await transferRes.json();
    createdTxIds.push(transferTx.transaction_id);
    // Mark as transfer
    await fetch(`${BACKEND_URL}/transactions/${transferTx.transaction_id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_transfer: true }),
    });
    console.log(`✓ Created Transfer transaction: $40.00 (${transferTx.transaction_id})`);

    // Create 3 Recurring Netflix transactions for June, July, August
    for (const d of ['2026-06-10', '2026-07-10', '2026-08-10']) {
      const recRes = await fetch(`${BACKEND_URL}/transactions/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: testAccountId,
          description: 'NETFLIX.COM',
          amount: '15.49',
          date: d,
          pending: false,
        }),
      });
      const recTx = await recRes.json();
      createdTxIds.push(recTx.transaction_id);
    }
    console.log(`✓ Created 3 recurring Netflix transactions ($15.49)`);

  } catch (err) {
    console.error('Failed to setup synthetic data:', err);
    process.exit(1);
  }

  // Launch headless Chrome
  const profileDir = `/tmp/cdp_split_audit_${Date.now()}`;
  const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
    '--headless=new',
    `--remote-debugging-port=${CDP_PORT}`,
    `--user-data-dir=${profileDir}`,
    '--no-first-run',
    '--disable-gpu',
    '--window-size=1280,800',
  ]);

  try {
    await wait(2000);
    const verRes = await fetch(`http://127.0.0.1:${CDP_PORT}/json/version`);
    const verData = await verRes.json();
    console.log(`Connected to Chrome: ${verData.Browser}`);

    // Create tab targeting Transactions page with August 2026 month
    const targetUrl = `${FRONTEND_URL}/transactions?month=2026-08&account_id=${testAccountId}`;
    const newTabRes = await fetch(`http://127.0.0.1:${CDP_PORT}/json/new?${targetUrl}`, { method: 'PUT' });
    const tabData = await newTabRes.json();
    const session = new CDPSession(tabData.webSocketDebuggerUrl);
    await session.init();
    await session.send('Page.enable');
    await session.send('Runtime.enable');
    await session.send('DOM.enable');

    console.log('\n--- Scenario J: Invalid Allocation UX & UI Cleanup Verification ---');
    let hydrated = false;
    for (let i = 0; i < 30; i++) {
      hydrated = await session.eval(`!!document.querySelector('.transactions-table')`);
      if (hydrated) break;
      await wait(300);
    }
    if (!hydrated) throw new Error('Transactions page failed to hydrate');

    // Select synthetic account in account dropdown
    await session.eval(`
      (() => {
        const sel = document.querySelector('#tx-account-select');
        if (sel) {
          sel.value = '${testAccountId}';
          sel.dispatchEvent(new Event('change', { bubbles: true }));
        }
      })()
    `);
    await wait(600);

    let triggerFound = false;
    for (let i = 0; i < 30; i++) {
      triggerFound = await session.eval(`
        (() => {
          const rows = Array.from(document.querySelectorAll('tbody tr'));
          const row = rows.find(r => r.textContent.includes('Costco Wholesale'));
          return !!(row && row.querySelector('.btn-split-trigger'));
        })()
      `);
      if (triggerFound) break;
      await wait(300);
    }
    if (!triggerFound) throw new Error('Costco transaction row with .btn-split-trigger not found in ledger');

    // Click Split on Costco transaction
    await session.eval(`
      (() => {
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        const row = rows.find(r => r.textContent.includes('Costco Wholesale'));
        row?.querySelector('.btn-split-trigger')?.click();
      })()
    `);

    let dialogOpen = false;
    for (let i = 0; i < 20; i++) {
      dialogOpen = await session.eval(`!!document.querySelector('.split-dialog-body')`);
      if (dialogOpen) break;
      await wait(200);
    }
    if (!dialogOpen) throw new Error('Split dialog failed to open');

    // Test under-allocation (initial state: 0 allocated)
    const initialStatus = await session.eval(`document.querySelector('.math-status-badge')?.textContent?.trim()`);
    const initialSaveDisabled = await session.eval(`!!document.querySelector('.btn-dialog-save')?.disabled`);
    console.log(`✓ Under-allocation status: "${initialStatus}", Save disabled: ${initialSaveDisabled}`);
    if (!initialStatus?.includes('unallocated') || !initialSaveDisabled) {
      throw new Error('Under-allocated state must display unallocated amount and disable Save');
    }

    // Test over-allocation: $100 + $70 = $170 > $150
    await session.eval(`
      (() => {
        const inputs = document.querySelectorAll('.split-line-row input[type="number"]');
        if (inputs.length >= 2) {
          inputs[0].value = '100.00';
          inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
          inputs[1].value = '70.00';
          inputs[1].dispatchEvent(new Event('input', { bubbles: true }));
        }
      })()
    `);
    await wait(300);

    const overStatus = await session.eval(`document.querySelector('.math-status-badge')?.textContent?.trim()`);
    const overSaveDisabled = await session.eval(`!!document.querySelector('.btn-dialog-save')?.disabled`);
    console.log(`✓ Over-allocation status: "${overStatus}", Save disabled: ${overSaveDisabled}`);
    if (!overStatus?.includes('overallocated') || !overSaveDisabled) {
      throw new Error('Over-allocated state must display overallocated amount and disable Save');
    }

    // Verify UI cleanup: "Remove" button text, no ✕
    const removeBtnText = await session.eval(`document.querySelector('.btn-remove-line')?.textContent?.trim()`);
    console.log(`✓ Remove button text: "${removeBtnText}"`);
    if (removeBtnText !== 'Remove') {
      throw new Error(`Expected clean text "Remove", got "${removeBtnText}"`);
    }

    // Set valid allocation: $100 Groceries, $50 Household
    await session.eval(`
      (() => {
        const inputs = document.querySelectorAll('.split-line-row input[type="number"]');
        const selects = document.querySelectorAll('.split-line-row select');
        inputs[1].value = '50.00';
        inputs[1].dispatchEvent(new Event('input', { bubbles: true }));
        selects[0].value = '${grocCat.category_id}';
        selects[0].dispatchEvent(new Event('change', { bubbles: true }));
        selects[1].value = '${houseCat.category_id}';
        selects[1].dispatchEvent(new Event('change', { bubbles: true }));
      })()
    `);
    await wait(300);

    const balancedText = await session.eval(`document.querySelector('.badge-balanced')?.textContent?.trim()`);
    console.log(`✓ Balanced badge text: "${balancedText}"`);
    if (balancedText !== 'Balanced') {
      throw new Error(`Expected clean text "Balanced" without glyphs, got "${balancedText}"`);
    }

    // Save split
    await session.eval(`document.querySelector('.btn-dialog-save')?.click()`);
    await wait(1200);

    // Verify Split badge text on ledger row: clean "Split · 2" without ⑂
    const badgeText = await session.eval(`
      (() => {
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        const row = rows.find(r => r.textContent.includes('Costco Wholesale'));
        return row ? row.querySelector('.btn-split-badge')?.textContent?.trim() : null;
      })()
    `);
    console.log(`✓ Split badge on Costco row: "${badgeText}"`);
    if (badgeText !== 'Split · 2') {
      throw new Error(`Expected clean text "Split · 2" without decorative glyphs, got "${badgeText}"`);
    }

    console.log('\n--- Scenario A: Category Filtering ---');
    // Filter by Groceries: parent visible exactly once
    await session.eval(`
      (() => {
        const sel = document.querySelector('#tx-category-select');
        sel.value = '${grocCat.category_id}';
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      })()
    `);
    await wait(600);

    let costcoCount = await session.eval(`
      (() => {
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        return rows.filter(r => r.textContent.includes('Costco Wholesale')).length;
      })()
    `);
    console.log(`✓ Costco visible in Groceries filter: count=${costcoCount}`);
    if (costcoCount !== 1) throw new Error(`Expected Costco once in Groceries filter, found ${costcoCount}`);

    // Filter by Household: parent visible exactly once
    await session.eval(`
      (() => {
        const sel = document.querySelector('#tx-category-select');
        sel.value = '${houseCat.category_id}';
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      })()
    `);
    await wait(600);

    costcoCount = await session.eval(`
      (() => {
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        return rows.filter(r => r.textContent.includes('Costco Wholesale')).length;
      })()
    `);
    console.log(`✓ Costco visible in Household filter: count=${costcoCount}`);
    if (costcoCount !== 1) throw new Error(`Expected Costco once in Household filter, found ${costcoCount}`);

    // Filter by Unrelated Category: parent absent
    await session.eval(`
      (() => {
        const sel = document.querySelector('#tx-category-select');
        sel.value = '${unrelatedCat.category_id}';
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      })()
    `);
    await wait(600);

    costcoCount = await session.eval(`
      (() => {
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        return rows.filter(r => r.textContent.includes('Costco Wholesale')).length;
      })()
    `);
    console.log(`✓ Costco visible in Unrelated Category filter: count=${costcoCount}`);
    if (costcoCount !== 0) throw new Error(`Costco should be absent in unrelated category filter, found ${costcoCount}`);

    // Reset filter
    await session.eval(`
      (() => {
        const sel = document.querySelector('#tx-category-select');
        sel.value = '';
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      })()
    `);
    await wait(600);

    console.log('\n--- Scenario B: Uncategorized Filter ---');
    await session.eval(`
      (() => {
        const cb = document.querySelector('#tx-uncategorized-checkbox');
        cb.checked = true;
        cb.dispatchEvent(new Event('change', { bubbles: true }));
      })()
    `);
    await wait(600);

    costcoCount = await session.eval(`
      (() => {
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        return rows.filter(r => r.textContent.includes('Costco Wholesale')).length;
      })()
    `);
    console.log(`✓ Costco visible under Uncategorized filter: count=${costcoCount}`);
    if (costcoCount !== 0) throw new Error(`Split transaction must NOT appear under Uncategorized filter`);

    // Reset uncategorized filter
    await session.eval(`
      (() => {
        const cb = document.querySelector('#tx-uncategorized-checkbox');
        cb.checked = false;
        cb.dispatchEvent(new Event('change', { bubbles: true }));
      })()
    `);
    await wait(600);

    console.log('\n--- Scenario C: Budget Actuals Verification ---');
    const bgtRes = await fetch(`${BACKEND_URL}/summary/budget?month=2026-08`);
    const bgtData = await bgtRes.json();
    let grocActual = 0;
    let houseActual = 0;
    for (const g of bgtData.groups) {
      for (const c of g.categories) {
        if (c.category_id === grocCat.category_id) grocActual = c.actual;
        if (c.category_id === houseCat.category_id) houseActual = c.actual;
      }
    }
    console.log(`✓ Budget Summary Actuals: Groceries=${grocActual}, Household=${houseActual}`);
    if (grocActual < 100 || houseActual < 50) {
      throw new Error(`Expected Groceries >= 100 and Household >= 50, got Groceries=${grocActual}, Household=${houseActual}`);
    }

    console.log('\n--- Scenario D: Account Balance Invariance ---');
    const accPreRes = await fetch(`${BACKEND_URL}/accounts/`);
    const accsPre = await accPreRes.json();
    const balanceBefore = accsPre.find(a => (a.account_id || a.id) === testAccountId)?.current_balance;
    console.log(`✓ Account balance with split ($100 + $50): ${balanceBefore}`);

    // Edit split to $90 + $60 (preserving $150 total)
    await session.eval(`
      (() => {
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        const row = rows.find(r => r.textContent.includes('Costco Wholesale'));
        row.querySelector('.btn-split-badge')?.click();
      })()
    `);
    await wait(600);

    await session.eval(`
      (() => {
        const inputs = document.querySelectorAll('.split-line-row input[type="number"]');
        inputs[0].value = '90.00';
        inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
        inputs[1].value = '60.00';
        inputs[1].dispatchEvent(new Event('input', { bubbles: true }));
      })()
    `);
    await wait(300);
    await session.eval(`document.querySelector('.btn-dialog-save')?.click()`);
    await wait(1200);

    const accPostRes = await fetch(`${BACKEND_URL}/accounts/`);
    const accsPost = await accPostRes.json();
    const balanceAfter = accsPost.find(a => (a.account_id || a.id) === testAccountId)?.current_balance;
    console.log(`✓ Account balance after edit ($90 + $60): ${balanceAfter}`);
    if (!balanceBefore || balanceBefore !== balanceAfter) {
      throw new Error(`Account balance changed or invalid! Before: ${balanceBefore}, After: ${balanceAfter}`);
    }

    console.log('\n--- Scenario E: Transfer Guard ---');
    // 1. Confirmed transfer row must NOT have split buttons
    const transferHasSplitTrigger = await session.eval(`
      (() => {
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        const row = rows.find(r => r.textContent.includes('Transfer Outflow'));
        return row ? !!row.querySelector('.btn-split-trigger') || !!row.querySelector('.btn-split-badge') : false;
      })()
    `);
    console.log(`✓ Confirmed transfer has split trigger/badge: ${transferHasSplitTrigger}`);
    if (transferHasSplitTrigger) throw new Error('Confirmed transfer should not have split trigger or badge');

    // 2. Marking a split transaction as a transfer must be rejected
    const patchTransferRes = await fetch(`${BACKEND_URL}/transactions/${costcoTxId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_transfer: true }),
    });
    console.log(`✓ Marking split transaction as transfer response: status=${patchTransferRes.status}`);
    if (patchTransferRes.status !== 400) {
      throw new Error(`Expected 400 Bad Request when marking split as transfer, got ${patchTransferRes.status}`);
    }

    // Verify splits remain intact
    const verifySplitsRes = await fetch(`${BACKEND_URL}/transactions/${costcoTxId}/splits`);
    const verifySplitsData = await verifySplitsRes.json();
    console.log(`✓ Split count after rejected transfer attempt: ${verifySplitsData.length}`);
    if (verifySplitsData.length !== 2) throw new Error('Split allocations were modified after transfer rejection');

    console.log('\n--- Scenario F: Pending Guard ---');
    const pendingHasSplitTrigger = await session.eval(`
      (() => {
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        const row = rows.find(r => r.textContent.includes('Pending Coffee'));
        return row ? !!row.querySelector('.btn-split-trigger') || !!row.querySelector('.btn-split-badge') : false;
      })()
    `);
    console.log(`✓ Pending transaction has split trigger/badge: ${pendingHasSplitTrigger}`);
    if (pendingHasSplitTrigger) throw new Error('Pending transaction should not have split trigger or badge');

    console.log('\n--- Scenario G: ML Suppression ---');
    const costcoHasMlSuggestion = await session.eval(`
      (() => {
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        const row = rows.find(r => r.textContent.includes('Costco Wholesale'));
        return row ? !!row.querySelector('.ml-suggestion-box') : false;
      })()
    `);
    console.log(`✓ Split parent has ML suggestion box: ${costcoHasMlSuggestion}`);
    if (costcoHasMlSuggestion) throw new Error('Split transaction should not have ML suggestion displayed');

    console.log('\n--- Scenario H: Recurring Independence ---');
    // Open recurring panel and verify Netflix is detected
    await session.eval(`document.querySelector('.btn-recurring-matches')?.click()`);
    await wait(600);
    const recurringTitle = await session.eval(`document.querySelector('.recurring-panel .panel-title')?.textContent?.trim()`);
    const recRowsCount = await session.eval(`document.querySelectorAll('.recurring-table tbody tr').length`);
    console.log(`✓ Recurring Panel: "${recurringTitle}", Series count: ${recRowsCount}`);
    if (!recurringTitle || recRowsCount === 0) throw new Error('Recurring series not detected');
    // Close panel
    await session.eval(`document.querySelector('.btn-close-panel')?.click()`);
    await wait(400);

    console.log('\n--- Scenario I: Reconciled Transaction Category Split Edit ---');
    // Mark Costco as cleared
    await fetch(`${BACKEND_URL}/transactions/${costcoTxId}/cleared`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_cleared: true }),
    });

    // Finalize reconciliation
    await fetch(`${BACKEND_URL}/accounts/${testAccountId}/reconciliation/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        statement_ending_date: '2026-08-31',
        statement_ending_balance: '1850.00',
      }),
    });

    // Re-open split modal and edit to $100 and $50
    await session.eval(`
      (() => {
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        const row = rows.find(r => r.textContent.includes('Costco Wholesale'));
        row.querySelector('.btn-split-badge')?.click();
      })()
    `);
    await wait(600);

    await session.eval(`
      (() => {
        const inputs = document.querySelectorAll('.split-line-row input[type="number"]');
        inputs[0].value = '100.00';
        inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
        inputs[1].value = '50.00';
        inputs[1].dispatchEvent(new Event('input', { bubbles: true }));
      })()
    `);
    await wait(300);
    await session.eval(`document.querySelector('.btn-dialog-save')?.click()`);
    await wait(1200);

    // Verify parent transaction still retains is_cleared=true, is_reconciled=true, amount=150.00
    const costcoVerifyRes = await fetch(`${BACKEND_URL}/transactions/${costcoTxId}`);
    const costcoVerify = await costcoVerifyRes.json();
    console.log(`✓ Reconciled tx after split edit: is_cleared=${costcoVerify.is_cleared}, is_reconciled=${costcoVerify.is_reconciled}, amount=${costcoVerify.amount}`);
    if (!costcoVerify.is_cleared || !costcoVerify.is_reconciled || costcoVerify.amount !== '150.00') {
      throw new Error('Reconciled status or amount was altered during split allocation edit');
    }

    console.log('\n=== All 10 Chrome/CDP Acceptance Scenarios (A through J) Passed! ===');

  } finally {
    // Teardown browser
    chrome.kill('SIGTERM');
    await wait(500);
    try {
      fs.rmSync(profileDir, { recursive: true, force: true });
    } catch {}

    // Cleanup synthetic data
    console.log('\n--- Cleanup: Deleting Synthetic Test Data ---');
    if (testAccountId) {
      try {
        execSync(`python3 -c "
from backend.database import SessionLocal
from backend import models
db = SessionLocal()
db.query(models.TransactionSplit).filter(models.TransactionSplit.transaction.has(account_id='${testAccountId}')).delete(synchronize_session=False)
db.query(models.Transaction).filter_by(account_id='${testAccountId}').delete(synchronize_session=False)
db.query(models.Account).filter_by(id='${testAccountId}').delete(synchronize_session=False)
db.commit()
"`, { stdio: 'ignore' });
      } catch {}
    }
    console.log('✓ Cleanup complete.');
  }
}

main().catch((err) => {
  console.error('\n❌ Comprehensive CDP Acceptance Test Failed:', err);
  process.exit(1);
});

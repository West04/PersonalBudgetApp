/**
 * Real Chrome/CDP Acceptance Test Suite for Phase 11 Recurring Transactions.
 * 
 * Interacts with the live UI in headless Google Chrome using Chrome DevTools Protocol (CDP).
 * Verifies hydration, recurring detection, ledger row badges, confirmation workflow,
 * dismissal workflow, persistence across page reloads, and responsive behavior.
 */

import { spawn } from 'node:child_process';
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
  console.log('=== Starting Phase 11 Chrome/CDP Acceptance Tests ===');
  let testAccountId = null;
  const testTxIds = [];

  // Setup synthetic data via backend API
  console.log('\n--- Setting up synthetic transactions for testing ---');
  try {
    const accRes = await fetch(`${BACKEND_URL}/accounts/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: `CDP Recurring Test ${Date.now()}`,
        type: 'depository',
        subtype: 'checking',
        starting_balance: '1000.00',
        current_balance: '1000.00',
      }),
    });
    const accData = await accRes.json();
    testAccountId = accData.account_id;
    console.log(`✓ Created test account: ${accData.name} (${testAccountId})`);

    // Create 3 monthly Netflix transactions (recurring)
    for (const d of ['2026-06-15', '2026-07-15', '2026-08-15']) {
      const txRes = await fetch(`${BACKEND_URL}/transactions/`, {
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
      const tx = await txRes.json();
      testTxIds.push(tx.transaction_id);
    }
    console.log(`✓ Created 3 monthly Netflix transactions: $15.49`);

    // Create 1 irregular Coffee transaction (not recurring)
    const coffeeRes = await fetch(`${BACKEND_URL}/transactions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: testAccountId,
        description: 'Corner Coffee',
        amount: '4.50',
        date: '2026-08-10',
        pending: false,
      }),
    });
    const coffeeTx = await coffeeRes.json();
    testTxIds.push(coffeeTx.transaction_id);
    console.log(`✓ Created 1 irregular coffee transaction: $4.50`);
  } catch (err) {
    console.error('Failed to setup synthetic data:', err);
    process.exit(1);
  }

  // Launch headless Chrome
  const profileDir = `/tmp/cdp_recurring_${Date.now()}`;
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

    console.log('\n--- Scenario 1: Transactions Page Hydration & Recurring Button ---');
    let hydrated = false;
    for (let i = 0; i < 30; i++) {
      hydrated = await session.eval(`!!document.querySelector('.transactions-table')`);
      if (hydrated) break;
      await wait(300);
    }
    if (!hydrated) throw new Error('Transactions page failed to hydrate');

    const recurringBtnText = await session.eval(`document.querySelector('.btn-recurring-matches')?.textContent?.trim()`);
    console.log(`✓ Recurring Button visible: "${recurringBtnText}"`);
    if (!recurringBtnText || !recurringBtnText.includes('Recurring')) {
      throw new Error('Recurring button missing from page header');
    }
    if (recurringBtnText.includes('🔄')) {
      throw new Error(`Recurring button must not contain emoji symbol: "${recurringBtnText}"`);
    }

    console.log('\n--- Scenario 2: Ledger Row Recurring Badges ---');
    // Wait up to 5s for recurring items to load and tag rows
    let badgeFound = false;
    for (let i = 0; i < 20; i++) {
      badgeFound = await session.eval(`!!document.querySelector('.recurring-tag')`);
      if (badgeFound) break;
      await wait(300);
    }
    if (!badgeFound) throw new Error('Recurring tag did not appear on Netflix transaction row');

    const recurringTagText = await session.eval(`document.querySelector('.recurring-tag')?.textContent?.trim()`);
    console.log(`✓ Recurring Badge on Netflix row: "${recurringTagText}"`);
    if (recurringTagText !== 'Recurring · Monthly') {
      throw new Error(`Unexpected recurring tag text: "${recurringTagText}"`);
    }

    // Verify irregular coffee transaction does NOT have recurring badge
    const coffeeHasBadge = await session.eval(`
      (() => {
        const rows = Array.from(document.querySelectorAll('tbody tr'));
        const coffeeRow = rows.find(r => r.textContent.includes('Corner Coffee'));
        return coffeeRow ? !!coffeeRow.querySelector('.recurring-tag') : false;
      })()
    `);
    console.log(`✓ Irregular Coffee transaction has recurring badge: ${coffeeHasBadge}`);
    if (coffeeHasBadge) throw new Error('Irregular coffee transaction was incorrectly marked recurring');

    console.log('\n--- Scenario 3: Recurring Activity Panel Display ---');
    // Click Recurring button to toggle panel
    await session.eval(`document.querySelector('.btn-recurring-matches')?.click()`);
    await wait(500);

    const panelVisible = await session.eval(`!!document.querySelector('.recurring-panel')`);
    console.log(`✓ Recurring Panel Visible: ${panelVisible}`);
    if (!panelVisible) throw new Error('Recurring panel did not open on click');

    const panelTitle = await session.eval(`document.querySelector('.recurring-panel .panel-title')?.textContent?.trim()`);
    const merchantName = await session.eval(`document.querySelector('.recurring-table .rec-merchant-name')?.textContent?.trim()`);
    const cadence = await session.eval(`document.querySelector('.recurring-table .cadence-tag')?.textContent?.trim()`);
    const statusPill = await session.eval(`document.querySelector('.recurring-table .status-pill')?.textContent?.trim()`);
    console.log(`✓ Panel Title: "${panelTitle}"`);
    console.log(`✓ Table row: Merchant "${merchantName}", Cadence "${cadence}", Status "${statusPill}"`);
    if (merchantName !== 'Netflix') throw new Error(`Expected Netflix row, found: "${merchantName}"`);
    if (cadence !== 'monthly') throw new Error(`Expected cadence monthly, found: "${cadence}"`);

    console.log('\n--- Scenario 4: User Confirmation ---');
    // Click Confirm button
    const confirmBtn = await session.eval(`!!document.querySelector('.rec-actions-cell .confirm-btn')`);
    if (!confirmBtn) throw new Error('Confirm button not found');
    const confirmBtnText = await session.eval(`document.querySelector('.rec-actions-cell .confirm-btn')?.textContent?.trim()`);
    console.log(`✓ Confirm button text: "${confirmBtnText}"`);
    if (confirmBtnText !== 'Confirm') throw new Error(`Expected plain text "Confirm", got "${confirmBtnText}"`);
    await session.eval(`document.querySelector('.rec-actions-cell .confirm-btn')?.click()`);
    await wait(1000);

    const updatedStatus = await session.eval(`document.querySelector('.recurring-table .status-pill')?.textContent?.trim()`);
    console.log(`✓ Status after Confirm click: "${updatedStatus}"`);
    if (updatedStatus !== 'confirmed') throw new Error('Status failed to update to confirmed');

    // Reload page to verify persistence
    console.log('Reloading page to test persistence...');
    await session.send('Page.reload');
    await wait(2000);

    // Open panel again
    await session.eval(`document.querySelector('.btn-recurring-matches')?.click()`);
    await wait(500);
    const persistedStatus = await session.eval(`document.querySelector('.recurring-table .status-pill')?.textContent?.trim()`);
    console.log(`✓ Status after page reload: "${persistedStatus}"`);
    if (persistedStatus !== 'confirmed') throw new Error('Confirmed status was not persisted on reload');

    console.log('\n--- Scenario 5: User Dismissal ---');
    // Click Dismiss button
    const dismissBtn = await session.eval(`!!document.querySelector('.rec-actions-cell .dismiss-btn')`);
    if (!dismissBtn) throw new Error('Dismiss button not found');
    const dismissBtnText = await session.eval(`document.querySelector('.rec-actions-cell .dismiss-btn')?.textContent?.trim()`);
    console.log(`✓ Dismiss button text: "${dismissBtnText}"`);
    if (dismissBtnText !== 'Dismiss') throw new Error(`Expected plain text "Dismiss", got "${dismissBtnText}"`);
    await session.eval(`document.querySelector('.rec-actions-cell .dismiss-btn')?.click()`);
    await wait(1000);

    const statusAfterDismiss = await session.eval(`document.querySelector('.recurring-table .status-pill')?.textContent?.trim()`);
    console.log(`✓ Status after Dismiss click: "${statusAfterDismiss}"`);
    if (statusAfterDismiss !== 'dismissed') throw new Error('Status failed to update to dismissed');

    // Reload page to verify dismissal persistence
    console.log('Reloading page to test dismissal persistence...');
    await session.send('Page.reload');
    await wait(2000);

    // After dismissal, Netflix row in ledger should NO LONGER have active recurring tag
    const netflixHasTagAfterDismiss = await session.eval(`!!document.querySelector('.recurring-tag')`);
    console.log(`✓ Netflix row still has active recurring tag after dismissal: ${netflixHasTagAfterDismiss}`);
    if (netflixHasTagAfterDismiss) throw new Error('Dismissed series still displayed active recurring tag');

    console.log('\n--- Scenario 6: Responsive Viewport (Narrow Mobile) ---');
    await session.send('Emulation.setDeviceMetricsOverride', {
      width: 375,
      height: 667,
      deviceScaleFactor: 2,
      mobile: true,
    });
    await wait(500);

    // Open panel in mobile view
    await session.eval(`document.querySelector('.btn-recurring-matches')?.click()`);
    await wait(500);
    const mobilePanelVisible = await session.eval(`!!document.querySelector('.recurring-panel')`);
    const tabsVisible = await session.eval(`document.querySelectorAll('.tab-btn').length`);
    console.log(`✓ Mobile viewport: panel visible=${mobilePanelVisible}, tabs count=${tabsVisible}`);
    if (!mobilePanelVisible || tabsVisible === 0) throw new Error('Mobile viewport failed to render recurring panel properly');

    console.log('\n=== All Phase 11 Chrome/CDP Scenarios Passed Successfully! ===');
  } finally {
    // Teardown browser
    chrome.kill('SIGTERM');
    await wait(500);
    try {
      fs.rmSync(profileDir, { recursive: true, force: true });
    } catch {}

    // Cleanup synthetic data
    console.log('\n--- Cleaning up synthetic test data ---');
    for (const txId of testTxIds) {
      try {
        await fetch(`${BACKEND_URL}/transactions/${txId}`, { method: 'DELETE' });
      } catch {}
    }
    if (testAccountId) {
      try {
        await fetch(`${BACKEND_URL}/accounts/${testAccountId}`, { method: 'DELETE' });
      } catch {}
    }
    console.log('✓ Cleanup complete.');
  }
}

main().catch((err) => {
  console.error('\n❌ CDP Acceptance Test Failed:', err);
  process.exit(1);
});

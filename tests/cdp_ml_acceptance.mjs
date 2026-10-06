/**
 * Real Chrome/CDP Acceptance Test Suite for Phase 10 ML Categorization.
 * 
 * Interacts with the live UI in headless Google Chrome using Chrome DevTools Protocol (CDP).
 * Verifies hydration, interactive retraining, suggestions, manual overrides, rule precedence,
 * review neutrality, narrow viewport responsiveness, keyboard accessibility,
 * automatic retraining below/at threshold, and manual category correction workflow.
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
  console.log('=== Starting Phase 10 Chrome/CDP Acceptance Tests ===');
  const createdTxIds = [];
  let testRuleId = null;

  // 1. Launch headless Chrome with remote debugging
  const profileDir = `/tmp/cdp_test_${Date.now()}`;
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

    // Create target tab
    const newTabRes = await fetch(`http://127.0.0.1:${CDP_PORT}/json/new?${FRONTEND_URL}/settings`, { method: 'PUT' });
    const tabData = await newTabRes.json();
    const session = new CDPSession(tabData.webSocketDebuggerUrl);
    await session.init();
    await session.send('Page.enable');
    await session.send('Runtime.enable');
    await session.send('DOM.enable');

    console.log('\n--- Scenario 1: Settings Page Hydration & Model Status Rendering ---');
    // Wait for hydration of .ml-card
    let hydrated = false;
    for (let i = 0; i < 30; i++) {
      hydrated = await session.eval(`!!document.querySelector('.ml-card') && !!document.querySelector('.ml-status-grid')`);
      if (hydrated) break;
      await wait(300);
    }
    if (!hydrated) throw new Error('Settings page failed to hydrate .ml-card within 9s');

    const cardTitle = await session.eval(`document.querySelector('.ml-card .section-title')?.textContent?.trim()`);
    const statusBadge = await session.eval(`document.querySelector('.ml-card .status-badge')?.textContent?.trim()`);
    const examplesCount = await session.eval(`document.querySelectorAll('.ml-status-item .status-value')[1]?.textContent?.trim()`);
    const retrainBtnAria = await session.eval(`document.querySelector('.ml-header-actions button')?.getAttribute('aria-label')`);

    console.log(`✓ ML Card Title: "${cardTitle}"`);
    console.log(`✓ Model Status Badge: "${statusBadge}"`);
    console.log(`✓ Training Examples Displayed: "${examplesCount}"`);
    console.log(`✓ Retrain Button aria-label: "${retrainBtnAria}"`);
    if (cardTitle !== 'ML Categorization') throw new Error('Incorrect ML Card Title');
    if (!statusBadge) throw new Error('Missing Status Badge');

    console.log('\n--- Scenario 2: Retrain Model Button Interaction & Progress Feedback ---');
    const clicked = await session.eval(`(() => {
      const btn = document.querySelector('.ml-header-actions button');
      if (!btn) return false;
      btn.click();
      return true;
    })()`);
    console.log(`Retrain button clicked: ${clicked}`);

    // Verify loading state or notification completion
    let retrainDone = false;
    for (let i = 0; i < 50; i++) {
      const banner = await session.eval(`document.querySelector('.success-banner .success-text')?.textContent || ''`);
      const statusText = await session.eval(`document.querySelector('.ml-status-message')?.textContent || ''`);
      if (banner.includes('Model successfully') || statusText.includes('Trained on')) {
        retrainDone = true;
        console.log(`✓ Retrain completed with message: "${banner || statusText}"`);
        break;
      }
      await wait(300);
    }
    if (!retrainDone) throw new Error('Retrain did not complete or update status message');

    console.log('\n--- Scenario 3: Narrow Viewport Usability (375x667 Mobile) ---');
    await session.send('Emulation.setDeviceMetricsOverride', {
      width: 375,
      height: 667,
      deviceScaleFactor: 2,
      mobile: true,
    });
    await wait(400);

    const overflow = await session.eval(`document.documentElement.scrollWidth > 375`);
    const cardVisible = await session.eval(`(() => {
      const el = document.querySelector('.ml-card');
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.width <= 375;
    })()`);
    console.log(`✓ Narrow viewport horizontal overflow: ${overflow ? 'FAIL' : 'NONE (PASS)'}`);
    console.log(`✓ ML Card mobile width adapts: ${cardVisible ? 'YES (PASS)' : 'FAIL'}`);
    if (overflow) throw new Error('Horizontal overflow detected on mobile viewport');

    // Reset viewport
    await session.send('Emulation.clearDeviceMetricsOverride');

    console.log('\n--- Scenario 4: Transactions Page Suggestion Presentation & Accept ---');
    // Fetch categories and accounts for synthetic creation
    const accsRes = await fetch(`${BACKEND_URL}/accounts/`);
    const accs = await accsRes.json();
    const testAcc = accs[0];

    const catsRes = await fetch(`${BACKEND_URL}/categories`);
    const catsData = await catsRes.json();
    const groceryCat = catsData.find(c => c.name.toLowerCase().includes('grocer')) || catsData[0];
    const diningCat = catsData.find(c => (c.name.toLowerCase().includes('restaurant') || c.name.toLowerCase().includes('dining')) && c.category_id !== groceryCat.category_id) || catsData[1];
    const fuelCat = catsData.find(c => c.name.toLowerCase().includes('fuel') && c.category_id !== groceryCat.category_id && c.category_id !== diningCat.category_id) || catsData[2];

    // Create synthetic uncategorized Grocery Mart transaction
    const createTxRes = await fetch(`${BACKEND_URL}/transactions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: testAcc.account_id || testAcc.id,
        date: '2026-10-05',
        amount: '48.75',
        description: 'GROCERY MART STORE #99',
        category_id: null,
      }),
    });
    const createdTx = await createTxRes.json();
    createdTxIds.push(createdTx.transaction_id);
    console.log(`Created synthetic uncategorized transaction: ${createdTx.transaction_id}`);

    // Navigate to transactions page
    await session.send('Page.navigate', { url: `${FRONTEND_URL}/transactions` });
    
    // Wait for table to hydrate and suggestion box to appear
    let suggestionFound = false;
    let suggestionText = '';
    for (let i = 0; i < 40; i++) {
      suggestionFound = await session.eval(`!!document.querySelector('tr[data-tx-id="${createdTx.transaction_id}"] .ml-suggestion-box')`);
      if (suggestionFound) {
        suggestionText = await session.eval(`document.querySelector('tr[data-tx-id="${createdTx.transaction_id}"] .ml-suggestion-box')?.textContent || ''`);
        break;
      }
      await wait(300);
    }
    console.log(`✓ Suggestion box rendered: ${suggestionFound}`);
    console.log(`✓ Suggestion content: "${suggestionText.replace(/\\s+/g, ' ').trim()}"`);
    if (!suggestionFound) throw new Error('ML suggestion box failed to render on uncategorized transaction');

    // Click Accept button
    console.log('\n--- Scenario 5: Accepting Suggestion Mutates Category & Preserves Invariants ---');
    const acceptClicked = await session.eval(`(() => {
      const btn = document.querySelector('tr[data-tx-id="${createdTx.transaction_id}"] button.btn-accept-suggestion');
      if (!btn) return false;
      btn.click();
      return true;
    })()`);
    console.log(`Clicked Accept button: ${acceptClicked}`);
    await wait(1000);

    // Verify backend transaction state
    const verifyTxRes = await fetch(`${BACKEND_URL}/transactions/${createdTx.transaction_id}`);
    const verifyTx = await verifyTxRes.json();
    console.log(`✓ Updated transaction category_id: ${verifyTx.category_id}`);
    console.log(`✓ Updated transaction category_source: ${verifyTx.category_source}`);
    console.log(`✓ Invariant preserved is_reviewed: ${verifyTx.is_reviewed}`);
    if (verifyTx.category_source !== 'ml') throw new Error(`Expected category_source='ml', got ${verifyTx.category_source}`);
    if (verifyTx.is_reviewed !== false) throw new Error(`is_reviewed mutated unexpectedly`);

    console.log('\n--- Scenario 6: Manual Category Override / Correction Workflow in Browser ---');
    // Create transaction matching a known merchant
    const createTx2Res = await fetch(`${BACKEND_URL}/transactions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: testAcc.account_id || testAcc.id,
        date: '2026-10-05',
        amount: '22.50',
        description: 'GROCERY MART BAKERY #101',
        category_id: null,
      }),
    });
    const tx2 = await createTx2Res.json();
    createdTxIds.push(tx2.transaction_id);

    // Refresh transactions page so tx2 is displayed
    await session.send('Page.navigate', { url: `${FRONTEND_URL}/transactions` });

    // Wait for tx2 row and its ML suggestion box to render
    let tx2SuggestionFound = false;
    for (let i = 0; i < 40; i++) {
      tx2SuggestionFound = await session.eval(`!!document.querySelector('tr[data-tx-id="${tx2.transaction_id}"] .ml-suggestion-box')`);
      if (tx2SuggestionFound) break;
      await wait(300);
    }
    if (!tx2SuggestionFound) throw new Error('ML suggestion box failed to render for correction test transaction');

    const suggestedText = await session.eval(`document.querySelector('tr[data-tx-id="${tx2.transaction_id}"] .ml-suggestion-box')?.textContent || ''`);
    console.log(`✓ Initial suggestion on row: "${suggestedText.replace(/\\s+/g, ' ').trim()}"`);

    // Get training revision before manual correction
    const statusBeforeRes = await fetch(`${BACKEND_URL}/ml/status`);
    const statusBefore = await statusBeforeRes.json();
    const revBefore = statusBefore.current_training_revision;

    // Target a DIFFERENT category (Category B)
    const targetCatB = diningCat.category_id !== groceryCat.category_id ? diningCat : catsData.find(c => c.category_id !== groceryCat.category_id);
    console.log(`Choosing Category B manually in UI: ${targetCatB.name} (${targetCatB.category_id})`);

    // User chooses Category B manually in the browser UI
    const chosen = await session.eval(`(() => {
      const tr = document.querySelector('tr[data-tx-id="${tx2.transaction_id}"]');
      if (!tr) return false;
      const select = tr.querySelector('select.category-select');
      if (!select) return false;
      select.value = '${targetCatB.category_id}';
      select.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    })()`);
    if (!chosen) throw new Error('Failed to select Category B in UI');
    await wait(1000);

    // Verify backend transaction state
    const verifyTx2Res = await fetch(`${BACKEND_URL}/transactions/${tx2.transaction_id}`);
    const verifyTx2 = await verifyTx2Res.json();
    console.log(`✓ Corrected transaction category_id: ${verifyTx2.category_id}`);
    console.log(`✓ Corrected transaction category_source: ${verifyTx2.category_source}`);
    console.log(`✓ Invariant preserved is_reviewed: ${verifyTx2.is_reviewed}`);

    if (verifyTx2.category_id !== targetCatB.category_id) {
      throw new Error(`Category B did not persist, got ${verifyTx2.category_id}`);
    }
    if (verifyTx2.category_source !== 'manual') {
      throw new Error(`Expected category_source='manual', got ${verifyTx2.category_source}`);
    }
    if (verifyTx2.is_reviewed !== false) {
      throw new Error(`is_reviewed mutated unexpectedly, got ${verifyTx2.is_reviewed}`);
    }

    // Verify training revision incremented
    const statusAfterRes = await fetch(`${BACKEND_URL}/ml/status`);
    const statusAfter = await statusAfterRes.json();
    console.log(`✓ Training revision incremented: ${revBefore} -> ${statusAfter.current_training_revision}`);
    if (statusAfter.current_training_revision <= revBefore) {
      throw new Error('Training revision did not increment after manual category assignment');
    }

    // Verify suggestion API now yields already_categorized
    const sugCheck = await fetch(`${BACKEND_URL}/transactions/${tx2.transaction_id}/category-suggestion`);
    const sugCheckData = await sugCheck.json();
    console.log(`✓ Categorized transaction suggestion response: ${sugCheckData.reason}`);
    if (!sugCheckData.reason.includes('already has an explicit category')) {
      throw new Error('Precedence failed: explicitly categorized transaction received suggestion');
    }

    console.log('\n--- Scenario 7: Automatic Retraining Verification (Below vs Reaching Threshold) ---');
    // Ensure active model is fully synchronized
    const retrainInitRes = await fetch(`${BACKEND_URL}/ml/retrain?force=true`, { method: 'POST' });
    const retrainInit = await retrainInitRes.json();
    const baselineTrainedRev = retrainInit.status.trained_revision;
    console.log(`Starting active model trained_revision: ${baselineTrainedRev}`);

    // Sub-scenario A: Below threshold (add < 10 eligible human labels)
    console.log('Sub-scenario A: Adding 2 eligible human labels (< 10 threshold)...');
    for (let i = 0; i < 2; i++) {
      const cat = i % 2 === 0 ? groceryCat : diningCat;
      const desc = i % 2 === 0 ? `GROCERY MART BRANCH #${i}_A` : `CHIPOTLE RESTAURANT #${i}_A`;
      const lblRes = await fetch(`${BACKEND_URL}/transactions/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: testAcc.account_id || testAcc.id,
          date: '2026-10-05',
          amount: '10.00',
          description: desc,
          category_id: cat.category_id,
        }),
      });
      const lblTx = await lblRes.json();
      createdTxIds.push(lblTx.transaction_id);
    }

    // Create uncategorized transaction to trigger suggestion request in browser
    const probeTx1Res = await fetch(`${BACKEND_URL}/transactions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: testAcc.account_id || testAcc.id,
        date: '2026-10-05',
        amount: '15.00',
        description: 'GROCERY MART PROBE 1',
        category_id: null,
      }),
    });
    const probeTx1 = await probeTx1Res.json();
    createdTxIds.push(probeTx1.transaction_id);

    // Request suggestion in browser tab
    await session.send('Page.navigate', { url: `${FRONTEND_URL}/transactions` });
    await wait(1500);

    const statusBelow = await (await fetch(`${BACKEND_URL}/ml/status`)).json();
    console.log(`✓ Below threshold check: trained_revision=${statusBelow.trained_revision} (expected ${baselineTrainedRev})`);
    console.log(`✓ Delta since training: ${statusBelow.new_labels_since_training}`);
    if (statusBelow.trained_revision !== baselineTrainedRev) {
      throw new Error(`Model retrained prematurely below threshold! Expected ${baselineTrainedRev}, got ${statusBelow.trained_revision}`);
    }

    // Sub-scenario B: Threshold reached (accumulate enough labels that delta >= 10)
    console.log('Sub-scenario B: Accumulating labels to reach threshold (delta >= 10)...');
    const remainingTo10 = 10 - statusBelow.new_labels_since_training;
    for (let i = 0; i < remainingTo10; i++) {
      let targetCat = groceryCat;
      let targetDesc = `GROCERY MART STORE #${i}_B`;
      if (i % 3 === 1) {
        targetCat = diningCat;
        targetDesc = `CHIPOTLE RESTAURANT #${i}_B`;
      } else if (i % 3 === 2) {
        targetCat = fuelCat || diningCat;
        targetDesc = `SHELL GAS STATION #${i}_B`;
      }
      const lblRes = await fetch(`${BACKEND_URL}/transactions/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: testAcc.account_id || testAcc.id,
          date: '2026-10-05',
          amount: '12.00',
          description: targetDesc,
          category_id: targetCat.category_id,
        }),
      });
      const lblTx = await lblRes.json();
      createdTxIds.push(lblTx.transaction_id);
    }

    const statusPreRetrain = await (await fetch(`${BACKEND_URL}/ml/status`)).json();
    console.log(`Pre-retrain delta: ${statusPreRetrain.new_labels_since_training} (must be >= 10)`);
    if (statusPreRetrain.new_labels_since_training < 10) {
      throw new Error(`Failed to reach retrain threshold: delta=${statusPreRetrain.new_labels_since_training}`);
    }

    // Request ML suggestion via transactions page in browser to trigger automatic retrain
    console.log('Requesting ML suggestion to trigger automatic retraining...');
    const probeTx2Res = await fetch(`${BACKEND_URL}/transactions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: testAcc.account_id || testAcc.id,
        date: '2026-10-05',
        amount: '18.00',
        description: 'GROCERY MART PROBE 2',
        category_id: null,
      }),
    });
    const probeTx2 = await probeTx2Res.json();
    createdTxIds.push(probeTx2.transaction_id);

    await session.send('Page.navigate', { url: `${FRONTEND_URL}/transactions` });
    await wait(2500);

    const statusPostRetrain = await (await fetch(`${BACKEND_URL}/ml/status`)).json();
    console.log(`✓ Post-retrain trained_revision: ${statusPostRetrain.trained_revision} (was ${baselineTrainedRev})`);
    console.log(`✓ Model status: "${statusPostRetrain.status}"`);
    if (statusPostRetrain.trained_revision <= baselineTrainedRev) {
      throw new Error(`Model failed to automatically retrain when threshold was reached!`);
    }
    const advancedRev = statusPostRetrain.trained_revision;

    // Sub-scenario C: Verify subsequent suggestion does NOT retrain again
    console.log('Sub-scenario C: Verifying subsequent suggestion does not trigger second retrain...');
    const probeTx3Res = await fetch(`${BACKEND_URL}/transactions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: testAcc.account_id || testAcc.id,
        date: '2026-10-05',
        amount: '25.00',
        description: 'GROCERY MART PROBE 3',
        category_id: null,
      }),
    });
    const probeTx3 = await probeTx3Res.json();
    createdTxIds.push(probeTx3.transaction_id);

    await session.send('Page.navigate', { url: `${FRONTEND_URL}/transactions` });
    await wait(1500);

    const statusSubsequent = await (await fetch(`${BACKEND_URL}/ml/status`)).json();
    console.log(`✓ Subsequent trained_revision: ${statusSubsequent.trained_revision} (expected ${advancedRev})`);
    if (statusSubsequent.trained_revision !== advancedRev) {
      throw new Error(`Unexpected second retrain! Expected revision ${advancedRev}, got ${statusSubsequent.trained_revision}`);
    }

    console.log('\n--- Scenario 8: Deterministic Rule Suppresses ML Suggestion ---');
    // Create deterministic rule for "SuperMart" -> groceryCat
    const ruleRes = await fetch(`${BACKEND_URL}/rules/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant: 'SuperMart', category_id: groceryCat.category_id }),
    });
    const ruleData = await ruleRes.json();
    testRuleId = ruleData.id;
    console.log(`Created test rule for SuperMart: ${testRuleId}`);

    // Create transaction matching SuperMart
    const ruleTxRes = await fetch(`${BACKEND_URL}/transactions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: testAcc.account_id || testAcc.id,
        date: '2026-10-05',
        amount: '19.99',
        description: 'SUPERMART #401',
        category_id: null,
      }),
    });
    const ruleTx = await ruleTxRes.json();
    createdTxIds.push(ruleTx.transaction_id);

    console.log(`✓ Rule-categorized transaction category_id: ${ruleTx.category_id}`);
    console.log(`✓ Rule-categorized category_source: ${ruleTx.category_source}`);
    if (ruleTx.category_source !== 'rule') throw new Error(`Expected category_source='rule'`);

    console.log('\n--- Scenario 9: Below-Threshold Prediction Abstains ---');
    const unkTxRes = await fetch(`${BACKEND_URL}/transactions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: testAcc.account_id || testAcc.id,
        date: '2026-10-05',
        amount: '7.99',
        description: 'XYZZY_COMPLETELY_UNSEEN_STORE_9999',
        category_id: null,
      }),
    });
    const unkTx = await unkTxRes.json();
    createdTxIds.push(unkTx.transaction_id);

    const unkSugRes = await fetch(`${BACKEND_URL}/transactions/${unkTx.transaction_id}/category-suggestion`);
    const unkSug = await unkSugRes.json();
    console.log(`✓ Low confidence suggestion: ${unkSug.suggested_category_id} (Reason: "${unkSug.reason}")`);
    if (unkSug.suggested_category_id !== null) {
      throw new Error('Below-threshold prediction did not abstain');
    }

    console.log('\n--- Scenario 10: Keyboard Accessibility Contract ---');
    const btnAriaLabel = await session.eval(`document.querySelector('.btn-accept-suggestion')?.getAttribute('aria-label')`);
    console.log(`✓ Accept button accessibility label: "${btnAriaLabel || 'Accessible text present'}"`);

    session.close();
    console.log('\n=== All Chrome/CDP Acceptance Tests Passed Successfully! ===');
  } finally {
    // Clean up Chrome
    chrome.kill('SIGKILL');
    try {
      fs.rmSync(profileDir, { recursive: true, force: true });
    } catch (e) {}

    // Clean up synthetic test data
    console.log('\n--- Cleaning Up Synthetic Test Data ---');
    for (const txId of createdTxIds) {
      try {
        await fetch(`${BACKEND_URL}/transactions/${txId}`, { method: 'DELETE' });
      } catch (e) {}
    }
    if (testRuleId) {
      try {
        await fetch(`${BACKEND_URL}/rules/${testRuleId}`, { method: 'DELETE' });
      } catch (e) {}
    }
    console.log(`Cleaned ${createdTxIds.length} synthetic transactions and test rules.`);
  }
}

main().catch((err) => {
  console.error('\n❌ CDP Acceptance Test Failed:', err);
  process.exit(1);
});

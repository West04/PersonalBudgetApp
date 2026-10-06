<template>
  <div class="transactions-page">
    <!-- Header -->
    <PageHeader
      title="Transactions"
      subtitle="Browse and categorize bank transactions"
    >
      <template #controls>
        <MonthNavigator />
      </template>
      <template #actions>
        <button
          type="button"
          class="btn-transfer-matches"
          @click="toggleTransfersPanel"
          :disabled="candidatesLoading"
          aria-label="Find and review transfer matches"
        >
          🔍 Find Transfer Matches
          <span v-if="candidates.length > 0" class="cand-badge">({{ candidates.length }})</span>
        </button>
        <button
          type="button"
          class="btn-recurring-matches"
          @click="toggleRecurringPanel"
          :disabled="recurringLoading"
          aria-label="View and manage recurring activity"
        >
          Recurring
          <span v-if="activeRecurringCount > 0" class="cand-badge">({{ activeRecurringCount }})</span>
        </button>
      </template>
    </PageHeader>

    <!-- Error Banner -->
    <ErrorBanner
      v-if="displayError"
      :error="displayError"
      @dismiss="clearErrors"
    />

    <!-- Transfer Review Panel -->
    <section v-if="showTransfersPanel" class="transfer-panel card" aria-label="Transfer matches review">
      <div class="panel-header">
        <div class="panel-title-row">
          <div class="panel-title-with-badge">
            <h2 class="panel-title">Potential Transfers</h2>
            <span v-if="candidates.length > 0" class="panel-count-badge">{{ candidates.length }} {{ candidates.length === 1 ? 'match' : 'matches' }}</span>
          </div>
          <button type="button" class="btn-close-panel" @click="showTransfersPanel = false" aria-label="Close transfer matches panel">✕</button>
        </div>
        <p class="panel-sub">
          These look like transfers appearing on both accounts (credit card payments, savings moves, etc.). Confirm pairs to mark them as transfers.
        </p>
      </div>

      <LoadingState v-if="candidatesLoading" message="Finding transfer matches..." />

      <div v-else-if="transferError" class="panel-error">
        {{ transferError }}
      </div>

      <div v-else-if="candidates.length === 0" class="empty-candidates">
        <p>No potential transfer matches found.</p>
      </div>

      <div v-else class="candidate-list">
        <div v-for="(pair, idx) in candidates" :key="idx" class="candidate-row">
          <div class="candidate-side outflow">
            <div class="cand-account">{{ pair.outflow_account_name }}</div>
            <div class="cand-desc" :title="pair.outflow_side.description">{{ pair.outflow_side.description }}</div>
            <div class="cand-meta">{{ formatDate(pair.outflow_side.date) }}</div>
          </div>
          <div class="candidate-arrow">
            <span class="amount-badge">{{ formatCurrency(Math.abs(Number(pair.outflow_side.amount))) }}</span>
            <span class="arrow" aria-hidden="true">→</span>
          </div>
          <div class="candidate-side inflow">
            <div class="cand-account">{{ pair.inflow_account_name }}</div>
            <div class="cand-desc" :title="pair.inflow_side.description">{{ pair.inflow_side.description }}</div>
            <div class="cand-meta">{{ formatDate(pair.inflow_side.date) }}</div>
          </div>
          <div class="candidate-actions">
            <button
              type="button"
              class="confirm-btn"
              @click="confirmTransfer(pair, idx)"
              :disabled="confirmingPair"
              :aria-label="`Confirm transfer between ${pair.outflow_account_name} and ${pair.inflow_account_name}`"
            >
              ✓ Confirm
            </button>
            <button
              type="button"
              class="dismiss-btn"
              @click="dismissTransfer(idx)"
              :aria-label="`Dismiss candidate match between ${pair.outflow_account_name} and ${pair.inflow_account_name}`"
            >
              ✕ Dismiss
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- Recurring Activity Panel -->
    <section v-if="showRecurringPanel" class="recurring-panel card" aria-label="Recurring activity review">
      <div class="panel-header">
        <div class="panel-title-row">
          <div class="panel-title-with-badge">
            <h2 class="panel-title">Recurring Activity</h2>
            <span v-if="activeRecurringCount > 0" class="panel-count-badge">
              {{ activeRecurringCount }} {{ activeRecurringCount === 1 ? 'pattern' : 'patterns' }}
            </span>
          </div>
          <button type="button" class="btn-close-panel" @click="showRecurringPanel = false" aria-label="Close recurring panel">✕</button>
        </div>
        <p class="panel-sub">
          Automatically detected repeating bills, subscriptions, and income patterns. Confirm genuine items or dismiss non-recurring charges.
        </p>
        <div class="recurring-tabs" role="tablist" aria-label="Recurring pattern filter tabs">
          <button
            type="button"
            role="tab"
            :aria-selected="recurringTab === 'all'"
            class="tab-btn"
            :class="{ active: recurringTab === 'all' }"
            @click="recurringTab = 'all'"
          >
            All ({{ recurringItems.length }})
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="recurringTab === 'confirmed'"
            class="tab-btn"
            :class="{ active: recurringTab === 'confirmed' }"
            @click="recurringTab = 'confirmed'"
          >
            Confirmed ({{ recurringItems.filter(i => i.status === 'confirmed').length }})
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="recurringTab === 'detected'"
            class="tab-btn"
            :class="{ active: recurringTab === 'detected' }"
            @click="recurringTab = 'detected'"
          >
            Needs Review ({{ recurringItems.filter(i => i.status === 'detected').length }})
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="recurringTab === 'dismissed'"
            class="tab-btn"
            :class="{ active: recurringTab === 'dismissed' }"
            @click="recurringTab = 'dismissed'"
          >
            Dismissed ({{ recurringItems.filter(i => i.status === 'dismissed').length }})
          </button>
        </div>
      </div>

      <LoadingState v-if="recurringLoading" message="Analyzing recurring patterns..." />

      <div v-else-if="recurringError" class="panel-error">
        {{ recurringError }}
      </div>

      <div v-else-if="filteredRecurringItems.length === 0" class="empty-candidates">
        <p>No recurring patterns found in this view.</p>
      </div>

      <div v-else class="recurring-table-wrapper">
        <table class="recurring-table" aria-label="Recurring items table">
          <thead>
            <tr>
              <th scope="col">Merchant</th>
              <th scope="col">Cadence</th>
              <th scope="col">Typical Amount</th>
              <th scope="col">Next Expected</th>
              <th scope="col">History</th>
              <th scope="col">Status</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filteredRecurringItems" :key="item.id" class="recurring-row">
              <td class="rec-merchant-cell">
                <span class="rec-merchant-name">{{ item.merchant }}</span>
                <span class="rec-account-name font-mono">{{ item.account_name || 'Account' }}</span>
              </td>
              <td class="rec-cadence-cell">
                <span class="cadence-tag font-mono">{{ item.cadence }}</span>
              </td>
              <td class="rec-amount-cell font-mono">
                {{ formatCurrency(Number(item.expected_amount)) }}
                <span class="amount-type-hint">({{ item.amount_type }})</span>
              </td>
              <td class="rec-next-date-cell font-mono">
                {{ item.next_expected_date ? formatDate(item.next_expected_date) : 'N/A' }}
              </td>
              <td class="rec-count-cell">
                {{ item.occurrence_count }} occurrences
              </td>
              <td class="rec-status-cell">
                <span class="status-pill" :class="item.status">{{ item.status }}</span>
              </td>
              <td class="rec-actions-cell">
                <button
                  v-if="item.status !== 'confirmed'"
                  type="button"
                  class="confirm-btn"
                  @click="confirmRecurring(item)"
                  :disabled="recurringActionId === item.id"
                  :aria-label="`Confirm recurring pattern for ${item.merchant}`"
                >
                  Confirm
                </button>
                <button
                  v-if="item.status !== 'dismissed'"
                  type="button"
                  class="dismiss-btn"
                  @click="dismissRecurring(item)"
                  :disabled="recurringActionId === item.id"
                  :aria-label="`Dismiss recurring pattern for ${item.merchant}`"
                >
                  Dismiss
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Filters Section -->
    <div class="filters-card card" aria-label="Transaction filters">
      <div class="filters-grid">
        <!-- Search Filter -->
        <div class="filter-group">
          <label for="tx-search-input">Search</label>
          <div class="search-input-wrapper">
            <input
              id="tx-search-input"
              type="text"
              v-model="searchQuery"
              placeholder="Search description or merchant..."
              class="filter-input"
              aria-label="Search transaction description or merchant"
            />
            <button
              v-if="searchQuery"
              type="button"
              class="search-clear-btn"
              @click="searchQuery = ''"
              aria-label="Clear search input"
              title="Clear search"
            >
              ✕
            </button>
          </div>
        </div>

        <!-- Account Filter (Route-backed) -->
        <div class="filter-group">
          <label for="tx-account-select">Account</label>
          <select
            id="tx-account-select"
            v-model="selectedAccount"
            class="filter-input"
            aria-label="Filter by account"
          >
            <option value="">All Accounts</option>
            <option
              v-for="acc in accounts"
              :key="acc.account_id"
              :value="acc.account_id"
            >
              {{ acc.name }}
            </option>
          </select>
        </div>

        <!-- Category Filter -->
        <div class="filter-group">
          <label for="tx-category-select">Category</label>
          <select
            id="tx-category-select"
            v-model="selectedCategory"
            class="filter-input"
            aria-label="Filter by category"
          >
            <option value="">All Categories</option>
            <optgroup
              v-for="group in categoryGroups"
              :key="group.category_group_id"
              :label="group.name"
            >
              <option
                v-for="cat in group.categories"
                :key="cat.category_id"
                :value="cat.category_id"
              >
                {{ cat.name }}
              </option>
            </optgroup>
          </select>
        </div>

        <!-- Review Status Filter -->
        <div class="filter-group">
          <label for="tx-review-select">Review Status</label>
          <select
            id="tx-review-select"
            v-model="reviewFilter"
            class="filter-input"
            aria-label="Filter by review status"
          >
            <option value="all">All</option>
            <option value="needs_review">Needs Review</option>
            <option value="reviewed">Reviewed</option>
          </select>
        </div>
      </div>

      <!-- Filters Meta Row: Uncategorized toggle, active indicators, and reset -->
      <div class="filters-meta-row">
        <div class="filter-meta-left">
          <label class="checkbox-label" for="tx-uncategorized-checkbox">
            <input
              type="checkbox"
              id="tx-uncategorized-checkbox"
              v-model="uncategorizedOnly"
              class="filter-checkbox"
            />
            <span>Uncategorized Only</span>
          </label>
        </div>

        <div class="filter-meta-right">
          <span class="filter-summary-text" aria-live="polite">
            {{ transactionCountLabel }}
            <template v-if="filterSummaryParts.length > 0">
              · <span class="summary-chips">{{ filterSummaryParts.join(' · ') }}</span>
            </template>
          </span>

          <button
            type="button"
            class="btn-clear-filters"
            :disabled="!hasActiveSecondaryFilters"
            @click="clearSecondaryFilters"
            aria-label="Clear active secondary filters"
          >
            Clear filters
          </button>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <LoadingState
      v-if="pending && !transactionsData"
      message="Loading transactions..."
    />

    <!-- Transactions Table Container -->
    <div v-else class="transactions-container">
      <div class="card table-card">
        <div class="table-responsive">
          <table class="transactions-table" aria-label="Transactions ledger">
            <thead>
              <tr>
                <th scope="col" class="date-col">Date</th>
                <th scope="col" class="desc-col">Merchant / Description</th>
                <th scope="col" class="account-col">Account</th>
                <th scope="col" class="category-col">Category</th>
                <th scope="col" class="amount-col">Amount</th>
                <th scope="col" class="status-col">Review</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="tx in transactionsData?.items"
                :key="tx.transaction_id"
                :data-tx-id="tx.transaction_id"
              >
                <td class="date-cell font-mono">{{ formatDate(tx.date) }}</td>
                <td class="desc-cell" :class="{ 'is-editing': editingMerchantId === tx.transaction_id }">
                  <template v-if="editingMerchantId === tx.transaction_id">
                    <form @submit.prevent="saveMerchant(tx)" class="merchant-edit-form">
                      <input
                        ref="merchantInputRef"
                        type="text"
                        v-model="editMerchantValue"
                        class="merchant-edit-input"
                        :aria-label="`Edit merchant for ${tx.description}`"
                        @keydown.esc="cancelEditingMerchant"
                        :disabled="savingMerchant"
                      />
                      <div class="merchant-edit-actions">
                        <button
                          type="submit"
                          class="btn-save-merchant"
                          :disabled="savingMerchant"
                          aria-label="Save merchant"
                          title="Save"
                        >
                          ✓
                        </button>
                        <button
                          type="button"
                          class="btn-cancel-merchant"
                          @click="cancelEditingMerchant"
                          :disabled="savingMerchant"
                          aria-label="Cancel editing merchant"
                          title="Cancel"
                        >
                          ✕
                        </button>
                      </div>
                    </form>
                  </template>
                  <template v-else>
                    <div class="merchant-row">
                      <span class="merchant-name" :class="{ 'is-overridden': tx.is_merchant_overridden }">
                        {{ tx.merchant || tx.description }}
                      </span>
                      <button
                        type="button"
                        class="btn-edit-merchant"
                        @click="startEditingMerchant(tx)"
                        :aria-label="`Edit merchant for ${tx.merchant || tx.description}`"
                        title="Edit merchant"
                      >
                        ✎
                      </button>
                      <span v-if="tx.is_transfer" class="transfer-tag">transfer</span>
                      <span v-if="getRecurringCadenceForTx(tx)" class="recurring-tag font-mono">Recurring · {{ getRecurringCadenceForTx(tx) }}</span>
                    </div>
                  </template>
                  <div
                    v-if="tx.merchant && tx.merchant.toLowerCase() !== tx.description.toLowerCase()"
                    class="raw-desc-text"
                    :title="`Original description: ${tx.description}`"
                  >
                    {{ tx.description }}
                  </div>
                </td>
                <td class="account-cell">
                  <span class="account-tag">{{ tx.account?.name || 'Unknown' }}</span>
                </td>
                <td class="category-cell">
                  <div v-if="tx.is_split" class="split-cell-content">
                    <button
                      type="button"
                      class="btn-split-badge"
                      @click="openSplitDialog(tx)"
                      :title="`Split across ${tx.split_count} categories. Click to view or edit.`"
                      :aria-label="`Split across ${tx.split_count} categories for transaction ${tx.merchant || tx.description}`"
                    >
                      <span class="split-badge-label">Split · {{ tx.split_count }}</span>
                    </button>
                  </div>
                  <div v-else class="unsplit-cell-content">
                    <div
                      v-if="!tx.category_id && suggestions[tx.transaction_id]?.suggested_category_id"
                      class="ml-suggestion-box"
                      role="status"
                      :aria-label="`Suggested category: ${suggestions[tx.transaction_id].suggested_category_name} (${suggestions[tx.transaction_id].score_label})`"
                    >
                      <span class="ml-suggestion-text" :title="`Suggested: ${suggestions[tx.transaction_id].suggested_category_name} · ${suggestions[tx.transaction_id].score_label}`">
                        Suggested: <strong>{{ suggestions[tx.transaction_id].suggested_category_name }}</strong>
                        <span class="ml-suggestion-score">· {{ suggestions[tx.transaction_id].score_label }}</span>
                      </span>
                      <button
                        type="button"
                        class="btn-accept-suggestion"
                        @click="acceptSuggestion(tx, suggestions[tx.transaction_id])"
                        :disabled="updatingId === tx.transaction_id"
                        :aria-label="`Accept suggested category ${suggestions[tx.transaction_id].suggested_category_name} for ${tx.merchant || tx.description}`"
                      >
                        Accept
                      </button>
                    </div>

                    <div class="category-select-row">
                      <select
                        :value="tx.category_id || ''"
                        @change="updateTransactionCategory(tx.transaction_id, ($event.target as HTMLSelectElement).value)"
                        class="category-select"
                        :class="{ 'uncategorized': !tx.category_id, 'has-suggestion': !tx.category_id && suggestions[tx.transaction_id]?.suggested_category_id }"
                        :disabled="updatingId === tx.transaction_id"
                        :aria-label="!tx.category_id && suggestions[tx.transaction_id]?.suggested_category_id ? 'Or choose another category' : 'Assign category'"
                      >
                        <option value="">{{ !tx.category_id && suggestions[tx.transaction_id]?.suggested_category_id ? 'Choose category...' : 'Uncategorized' }}</option>
                        <optgroup
                          v-for="group in categoryGroups"
                          :key="group.category_group_id"
                          :label="group.name"
                        >
                          <option
                            v-for="cat in group.categories"
                            :key="cat.category_id"
                            :value="cat.category_id"
                          >
                            {{ cat.name }}
                          </option>
                        </optgroup>
                      </select>

                      <button
                        v-if="!tx.is_transfer && !tx.pending"
                        type="button"
                        class="btn-split-trigger"
                        @click="openSplitDialog(tx)"
                        title="Split into multiple categories"
                        :aria-label="`Split transaction ${tx.merchant || tx.description} into multiple categories`"
                      >
                        Split
                      </button>
                    </div>
                  </div>
                </td>
                <td
                  class="amount-cell font-mono"
                  :class="{ 'inflow': tx.amount < 0 }"
                >
                  {{ tx.amount < 0 ? '+' : '' }}{{ formatCurrency(Math.abs(Number(tx.amount))) }}
                </td>
                <td class="status-cell">
                  <button
                    type="button"
                    class="review-toggle-btn"
                    :class="tx.is_reviewed ? 'is-reviewed' : 'needs-review'"
                    @click="toggleReviewStatus(tx)"
                    :disabled="updatingReviewId === tx.transaction_id"
                    :aria-label="tx.is_reviewed ? `Mark transaction ${tx.description} as needs review` : `Mark transaction ${tx.description} as reviewed`"
                  >
                    <span v-if="tx.is_reviewed" class="status-label">
                      <span class="check-icon" aria-hidden="true">✓</span> Reviewed
                    </span>
                    <span v-else class="status-label">
                      Needs Review
                    </span>
                  </button>
                </td>
              </tr>
              <tr v-if="transactionsData?.items.length === 0">
                <td colspan="6" class="empty-row">
                  No transactions found matching current filters.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div class="pagination" v-if="transactionsData?.total > limit">
          <button
            type="button"
            :disabled="offset === 0"
            @click="offset = Math.max(0, offset - limit)"
            class="page-btn"
            aria-label="Previous page"
          >
            Previous
          </button>
          <span class="page-info">
            Showing {{ offset + 1 }} - {{ Math.min(offset + limit, transactionsData.total) }} of {{ transactionsData.total }}
          </span>
          <button
            type="button"
            :disabled="offset + limit >= transactionsData.total"
            @click="offset += limit"
            class="page-btn"
            aria-label="Next page"
          >
            Next
          </button>
        </div>
      </div>
    </div>

    <!-- Split Transaction Dialog -->
    <AppDialog
      :open="splitDialogOpen"
      :title="splitDialogTitle"
      max-width="660px"
      @close="closeSplitDialog"
    >
      <div v-if="splitTx" class="split-dialog-body">
        <!-- Parent Details Header -->
        <div class="split-parent-summary">
          <div class="summary-col">
            <span class="summary-label">Date</span>
            <span class="summary-val font-mono">{{ formatDate(splitTx.date) }}</span>
          </div>
          <div class="summary-col">
            <span class="summary-label">Merchant / Description</span>
            <span class="summary-val font-semibold">{{ splitTx.merchant || splitTx.description }}</span>
          </div>
          <div class="summary-col">
            <span class="summary-label">Account</span>
            <span class="summary-val">{{ splitTx.account?.name || 'Unknown' }}</span>
          </div>
          <div class="summary-col text-right">
            <span class="summary-label">Transaction Total</span>
            <span class="summary-val font-mono font-bold" :class="{ 'inflow': Number(splitTx.amount) < 0 }">
              {{ Number(splitTx.amount) < 0 ? '+' : '' }}{{ formatCurrency(Math.abs(Number(splitTx.amount))) }}
            </span>
          </div>
        </div>

        <!-- Error Banner inside dialog -->
        <div v-if="splitDialogError" class="split-error-alert" role="alert">
          <span>{{ splitDialogError }}</span>
          <button type="button" class="alert-dismiss" @click="splitDialogError = null">✕</button>
        </div>

        <!-- Allocations Table -->
        <div class="split-allocations-section">
          <div class="split-allocations-header">
            <span class="section-title">Category Allocations</span>
            <span class="split-rule-hint">
              {{ Number(splitTx.amount) < 0 ? 'Inflow transaction: split amounts are applied as credits.' : 'Outflow transaction: split lines must exactly total the transaction amount.' }}
            </span>
          </div>

          <div class="split-lines-list">
            <div
              v-for="(line, idx) in splitLines"
              :key="idx"
              class="split-line-row"
            >
              <div class="line-category-col">
                <label :for="`split-cat-${idx}`" class="sr-only">Category line {{ idx + 1 }}</label>
                <select
                  :id="`split-cat-${idx}`"
                  v-model="line.category_id"
                  class="split-select"
                  :aria-label="`Category for split line ${idx + 1}`"
                >
                  <option value="" disabled>Select category...</option>
                  <optgroup
                    v-for="group in categoryGroups"
                    :key="group.category_group_id"
                    :label="group.name"
                  >
                    <option
                      v-for="cat in group.categories"
                      :key="cat.category_id"
                      :value="cat.category_id"
                    >
                      {{ cat.name }}
                    </option>
                  </optgroup>
                </select>
              </div>

              <div class="line-amount-col">
                <label :for="`split-amount-${idx}`" class="sr-only">Amount line {{ idx + 1 }}</label>
                <div class="amount-input-wrapper">
                  <span class="currency-prefix">{{ Number(splitTx.amount) < 0 ? '-$' : '$' }}</span>
                  <input
                    :id="`split-amount-${idx}`"
                    v-model="line.amountStr"
                    type="number"
                    step="0.01"
                    min="0.01"
                    placeholder="0.00"
                    class="split-amount-input font-mono"
                    :aria-label="`Amount for split line ${idx + 1}`"
                  />
                </div>
              </div>

              <div class="line-actions-col">
                <button
                  type="button"
                  class="btn-remove-line"
                  :disabled="splitLines.length <= 2"
                  @click="removeSplitLine(idx)"
                  :title="splitLines.length <= 2 ? 'Splits require at least 2 allocations' : 'Remove allocation'"
                  :aria-label="`Remove allocation line ${idx + 1}`"
                >
                  Remove
                </button>
              </div>
            </div>
          </div>

          <div class="split-add-line-row">
            <button
              type="button"
              class="btn-add-split-line"
              @click="addSplitLine"
            >
              + Add Category Line
            </button>
          </div>
        </div>

        <!-- Allocation Reconciliation Math Bar -->
        <div class="split-math-bar" :class="mathStatusClass">
          <div class="math-item">
            <span class="math-label">Transaction Total</span>
            <span class="math-val font-mono">{{ formatCurrency(parentAbsTotal) }}</span>
          </div>
          <div class="math-operator">−</div>
          <div class="math-item">
            <span class="math-label">Allocated</span>
            <span class="math-val font-mono">{{ formatCurrency(allocatedAbsTotal) }}</span>
          </div>
          <div class="math-operator">=</div>
          <div class="math-item">
            <span class="math-label">Remaining</span>
            <span class="math-val font-mono font-bold">{{ formatCurrency(remainingAbsTotal) }}</span>
          </div>
          <div class="math-status-badge">
            <span v-if="isBalanced" class="badge-balanced">Balanced</span>
            <span v-else-if="remainingCents > 0" class="badge-remaining">
              ${{ (remainingCents / 100).toFixed(2) }} unallocated
            </span>
            <span v-else class="badge-over">
              ${{ (Math.abs(remainingCents) / 100).toFixed(2) }} overallocated
            </span>
          </div>
        </div>

        <div v-if="hasDuplicateCategories" class="split-warning-msg">
          Each split line must be assigned to a different category.
        </div>

        <!-- Unsplit Section if currently split -->
        <div v-if="splitTx.is_split" class="unsplit-collapse-box">
          <div class="unsplit-header">
            <span class="unsplit-title">Convert back to single category</span>
            <span class="unsplit-subtitle">Removes all split allocations and restores a single category.</span>
          </div>
          <div class="unsplit-controls">
            <select
              v-model="unsplitTargetCategoryId"
              class="unsplit-category-select"
              aria-label="Select target category for unsplit"
            >
              <option value="">Leave Uncategorized</option>
              <optgroup
                v-for="group in categoryGroups"
                :key="group.category_group_id"
                :label="group.name"
              >
                <option
                  v-for="cat in group.categories"
                  :key="cat.category_id"
                  :value="cat.category_id"
                >
                  {{ cat.name }}
                </option>
              </optgroup>
            </select>
            <button
              type="button"
              class="btn-unsplit-action"
              :disabled="unsplitInProgress"
              @click="handleUnsplit"
            >
              {{ unsplitInProgress ? 'Restoring...' : 'Unsplit' }}
            </button>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="split-dialog-footer">
          <button
            type="button"
            class="btn-dialog-cancel"
            @click="closeSplitDialog"
            :disabled="savingSplit || unsplitInProgress"
          >
            Cancel
          </button>
          <button
            type="button"
            class="btn-dialog-save"
            :disabled="!canSaveSplit || savingSplit"
            @click="handleSaveSplit"
          >
            {{ savingSplit ? 'Saving...' : 'Save Splits' }}
          </button>
        </div>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBudgetMonth } from '~/composables/useBudgetMonth'
import { useTransactionFilters } from '~/composables/useTransactionFilters'
import { formatDateOnly } from '~/utils/formatDate'
import { buildTransactionQuery } from '~/utils/transactionQuery'

const API_BASE = '/api'

const route = useRoute()
const router = useRouter()
const { selectedMonth } = useBudgetMonth()

// Session-persisted secondary filters
const {
  searchQuery,
  selectedCategory,
  uncategorizedOnly,
  reviewFilter,
  offset,
  hasActiveSecondaryFilters,
  clearSecondaryFilters,
} = useTransactionFilters()

const limit = ref(50)

// Transfer Reconciliation
interface TransferCandidate {
  inflow_side: any
  inflow_account_name: string
  outflow_side: any
  outflow_account_name: string
}

const showTransfersPanel = ref(false)
const candidates = ref<TransferCandidate[]>([])
const candidatesLoading = ref(false)
const confirmingPair = ref(false)
const transferError = ref<string | null>(null)

const loadTransferCandidates = async () => {
  candidatesLoading.value = true
  transferError.value = null
  try {
    candidates.value = await $fetch<TransferCandidate[]>(`${API_BASE}/transactions/transfer-candidates`)
    showTransfersPanel.value = true
  } catch (err: any) {
    transferError.value = err.message || 'Failed to load transfer candidates'
    showTransfersPanel.value = true
  } finally {
    candidatesLoading.value = false
  }
}

const toggleTransfersPanel = () => {
  if (!showTransfersPanel.value && candidates.value.length === 0) {
    loadTransferCandidates()
  } else {
    showTransfersPanel.value = !showTransfersPanel.value
  }
}

const confirmTransfer = async (pair: TransferCandidate, idx: number) => {
  confirmingPair.value = true
  transferError.value = null
  try {
    await $fetch(`${API_BASE}/transactions/mark-transfers`, {
      method: 'POST',
      body: {
        transaction_ids: [
          pair.inflow_side.transaction_id,
          pair.outflow_side.transaction_id,
        ],
      },
    })
    candidates.value.splice(idx, 1)
    await refresh()
  } catch (err: any) {
    transferError.value = 'Failed to mark transfers'
  } finally {
    confirmingPair.value = false
  }
}

const dismissTransfer = (idx: number) => {
  candidates.value.splice(idx, 1)
}

// Recurring Transactions
interface RecurringItem {
  id: string
  account_id: string
  account_name?: string
  merchant: string
  direction: 'outflow' | 'inflow'
  cadence: 'weekly' | 'biweekly' | 'monthly' | 'annual'
  amount_type: 'fixed' | 'variable'
  expected_amount: string | number
  status: 'detected' | 'confirmed' | 'dismissed'
  last_date: string
  next_expected_date?: string
  occurrence_count: number
  explanation?: string
  transaction_ids: string[]
}

const showRecurringPanel = ref(false)
const recurringItems = ref<RecurringItem[]>([])
const recurringLoading = ref(false)
const recurringActionId = ref<string | null>(null)
const recurringError = ref<string | null>(null)
const recurringTab = ref<'all' | 'confirmed' | 'detected' | 'dismissed'>('all')

const loadRecurringItems = async () => {
  recurringLoading.value = true
  recurringError.value = null
  try {
    recurringItems.value = await $fetch<RecurringItem[]>(`${API_BASE}/recurring/`)
  } catch (err: any) {
    recurringError.value = err.message || 'Failed to load recurring items'
  } finally {
    recurringLoading.value = false
  }
}

const txRecurringMap = computed(() => {
  const map = new Map<string, string>()
  for (const item of recurringItems.value) {
    if (item.status === 'dismissed') continue
    const formattedCadence = item.cadence.charAt(0).toUpperCase() + item.cadence.slice(1)
    for (const txId of item.transaction_ids || []) {
      map.set(txId, formattedCadence)
    }
  }
  return map
})

const getRecurringCadenceForTx = (tx: any): string | null => {
  return txRecurringMap.value.get(tx.transaction_id) || null
}

const activeRecurringCount = computed(() => {
  return recurringItems.value.filter(i => i.status !== 'dismissed').length
})

const filteredRecurringItems = computed(() => {
  if (recurringTab.value === 'all') return recurringItems.value
  return recurringItems.value.filter(i => i.status === recurringTab.value)
})

const toggleRecurringPanel = () => {
  if (!showRecurringPanel.value && recurringItems.value.length === 0) {
    loadRecurringItems()
    showRecurringPanel.value = true
  } else {
    showRecurringPanel.value = !showRecurringPanel.value
  }
}

const confirmRecurring = async (item: RecurringItem) => {
  recurringActionId.value = item.id
  recurringError.value = null
  try {
    const updated = await $fetch<RecurringItem>(`${API_BASE}/recurring/${item.id}/confirm`, {
      method: 'POST',
    })
    const idx = recurringItems.value.findIndex(i => i.id === item.id)
    if (idx !== -1) {
      recurringItems.value[idx] = updated
    }
  } catch (err: any) {
    recurringError.value = 'Failed to confirm recurring pattern'
  } finally {
    recurringActionId.value = null
  }
}

const dismissRecurring = async (item: RecurringItem) => {
  recurringActionId.value = item.id
  recurringError.value = null
  try {
    const updated = await $fetch<RecurringItem>(`${API_BASE}/recurring/${item.id}/dismiss`, {
      method: 'POST',
    })
    const idx = recurringItems.value.findIndex(i => i.id === item.id)
    if (idx !== -1) {
      recurringItems.value[idx] = updated
    }
  } catch (err: any) {
    recurringError.value = 'Failed to dismiss recurring pattern'
  } finally {
    recurringActionId.value = null
  }
}

onMounted(() => {
  loadRecurringItems()
})


// Route-backed Account Filter
const getRouteAccountId = () => {
  return typeof route.query.account_id === 'string' && route.query.account_id
    ? route.query.account_id
    : ''
}

const selectedAccount = ref(getRouteAccountId())

// Route query -> selectedAccount
watch(
  () => route.query.account_id,
  (newAccount) => {
    const accountId = typeof newAccount === 'string' ? newAccount : ''
    if (selectedAccount.value !== accountId) {
      selectedAccount.value = accountId
    }
  }
)

// selectedAccount -> Route query
watch(selectedAccount, (newAcc) => {
  const currentQueryAcc = typeof route.query.account_id === 'string' ? route.query.account_id : ''
  if (newAcc !== currentQueryAcc) {
    const nextQuery: Record<string, string> = { ...route.query, month: selectedMonth.value }
    if (newAcc) {
      nextQuery.account_id = newAcc
    } else {
      delete nextQuery.account_id
    }
    router.replace({ query: nextQuery })
  }
})

// Metadata fetching
const { data: accounts } = await useFetch<any[]>(`${API_BASE}/accounts/`)
const { data: categoryGroups } = await useFetch<any[]>(`${API_BASE}/category-groups`)

// Computed Query Parameters using pure builder
const queryParams = computed(() => {
  return buildTransactionQuery({
    month: selectedMonth.value,
    accountId: selectedAccount.value,
    categoryId: selectedCategory.value,
    search: searchQuery.value,
    uncategorized: uncategorizedOnly.value,
    reviewFilter: reviewFilter.value,
    limit: limit.value,
    offset: offset.value,
  })
})

const {
  data: transactionsData,
  pending,
  error: fetchError,
  refresh,
} = await useFetch<any>(`${API_BASE}/transactions/`, {
  query: queryParams,
  server: false,
})

// Reset offset to 0 when any filter or month changes
watch(
  [searchQuery, selectedAccount, selectedCategory, uncategorizedOnly, reviewFilter, selectedMonth],
  () => {
    offset.value = 0
  }
)

// Active filter summary text
const filterSummaryParts = computed(() => {
  const parts: string[] = []
  if (selectedAccount.value) {
    const acc = accounts.value?.find((a: any) => a.account_id === selectedAccount.value)
    if (acc) parts.push(acc.name)
  }
  if (selectedCategory.value) {
    let catName = ''
    for (const group of categoryGroups.value || []) {
      const c = group.categories?.find((cat: any) => cat.category_id === selectedCategory.value)
      if (c) {
        catName = c.name
        break
      }
    }
    if (catName) parts.push(catName)
  }
  if (searchQuery.value.trim()) {
    parts.push(`"${searchQuery.value.trim()}"`)
  }
  if (uncategorizedOnly.value) {
    parts.push('Uncategorized')
  }
  if (reviewFilter.value === 'needs_review') {
    parts.push('Needs Review')
  } else if (reviewFilter.value === 'reviewed') {
    parts.push('Reviewed')
  }
  return parts
})

const transactionCountLabel = computed(() => {
  const count = transactionsData.value?.total ?? 0
  return `${count} ${count === 1 ? 'transaction' : 'transactions'}`
})

// Inline Merchant Editing
const editingMerchantId = ref<string | null>(null)
const editMerchantValue = ref('')
const savingMerchant = ref(false)
const merchantInputRef = ref<HTMLInputElement | null>(null)

const startEditingMerchant = (tx: any) => {
  editingMerchantId.value = tx.transaction_id
  editMerchantValue.value = tx.merchant || tx.description || ''
  nextTick(() => {
    if (merchantInputRef.value) {
      merchantInputRef.value.focus()
      merchantInputRef.value.select()
    }
  })
}

const cancelEditingMerchant = () => {
  editingMerchantId.value = null
  editMerchantValue.value = ''
}

const saveMerchant = async (tx: any) => {
  if (savingMerchant.value) return
  savingMerchant.value = true
  updateError.value = null
  const trimmed = editMerchantValue.value.trim()
  try {
    const response = await fetch(`${API_BASE}/transactions/${tx.transaction_id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant: trimmed }),
    })
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}))
      throw new Error(errData.detail || 'Failed to update merchant')
    }
    const updated = await response.json()
    tx.merchant = updated.merchant
    tx.is_merchant_overridden = updated.is_merchant_overridden
    editingMerchantId.value = null
  } catch (err: any) {
    updateError.value = err.message || 'Failed to update merchant. Please try again.'
    console.error(err)
  } finally {
    savingMerchant.value = false
  }
}

// Inline Category Editing
const updateError = ref<string | null>(null)
const updatingId = ref<string | null>(null)

// ML Category Suggestions
const suggestions = ref<Record<string, any>>({})
const suggestionsLoading = ref(false)

const loadSuggestions = async () => {
  const items = transactionsData.value?.items || []
  const uncatIds = items
    .filter((tx: any) => !tx.category_id && !tx.is_transfer)
    .map((tx: any) => tx.transaction_id)

  if (uncatIds.length === 0) {
    suggestions.value = {}
    return
  }

  suggestionsLoading.value = true
  try {
    const res = await $fetch<any>(`${API_BASE}/transactions/category-suggestions`, {
      method: 'POST',
      body: { transaction_ids: uncatIds },
    })
    suggestions.value = res.suggestions || {}
  } catch (err) {
    console.error('Failed to load category suggestions:', err)
  } finally {
    suggestionsLoading.value = false
  }
}

watch(transactionsData, () => {
  loadSuggestions()
}, { immediate: true })

const acceptSuggestion = async (tx: any, suggestion: any) => {
  updateError.value = null
  updatingId.value = tx.transaction_id
  try {
    const response = await fetch(`${API_BASE}/transactions/${tx.transaction_id}/accept-suggestion`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category_id: suggestion.suggested_category_id }),
    })
    if (!response.ok) throw new Error('Failed to accept suggestion')
    const updated = await response.json()
    tx.category_id = updated.category_id
    tx.category_source = updated.category_source
    delete suggestions.value[tx.transaction_id]
    await refresh()
  } catch (err: any) {
    updateError.value = err.message || 'Failed to accept suggestion. Please try again.'
    console.error(err)
  } finally {
    updatingId.value = null
  }
}

const updateTransactionCategory = async (transactionId: string, categoryId: string) => {
  updateError.value = null
  updatingId.value = transactionId
  try {
    const response = await fetch(`${API_BASE}/transactions/${transactionId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category_id: categoryId || null }),
    })

    if (!response.ok) throw new Error('Failed to update category')

    delete suggestions.value[transactionId]

    if (transactionsData.value?.items) {
      const item = transactionsData.value.items.find((t: any) => t.transaction_id === transactionId)
      if (item) {
        item.category_id = categoryId || null
      }
    }

    await refresh()
  } catch (err: any) {
    updateError.value = err.message || 'Failed to update category. Please try again.'
    console.error(err)
  } finally {
    updatingId.value = null
  }
}

// Inline Review Status Toggle
const updatingReviewId = ref<string | null>(null)

const toggleReviewStatus = async (tx: any) => {
  updateError.value = null
  updatingReviewId.value = tx.transaction_id
  const targetState = !tx.is_reviewed
  try {
    const response = await fetch(`${API_BASE}/transactions/${tx.transaction_id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_reviewed: targetState }),
    })

    if (!response.ok) throw new Error('Failed to update review status')

    tx.is_reviewed = targetState
    await refresh()
  } catch (err: any) {
    updateError.value = err.message || 'Failed to update review status. Please try again.'
    console.error(err)
  } finally {
    updatingReviewId.value = null
  }
}

// Helpers
const formatCurrency = (amount: number | string, currency = 'USD') => {
  const val = Number(amount)
  if (isNaN(val)) return '$0.00'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val)
}

const formatDate = (dateStr: string) => formatDateOnly(dateStr, { includeYear: true })

const displayError = computed(() => {
  if (updateError.value) return updateError.value
  if (fetchError.value) return fetchError.value.message || 'Failed to load transactions.'
  return null
})

const clearErrors = () => {
  updateError.value = null
}

// Split Transactions Dialog State & Handlers
interface SplitLineForm {
  category_id: string
  amountStr: string
}

const splitDialogOpen = ref(false)
const splitTx = ref<any>(null)
const splitLines = ref<SplitLineForm[]>([])
const splitDialogError = ref<string | null>(null)
const savingSplit = ref(false)
const unsplitInProgress = ref(false)
const unsplitTargetCategoryId = ref<string>('')

const splitDialogTitle = computed(() => {
  if (!splitTx.value) return 'Split Transaction'
  return splitTx.value.is_split ? 'Edit Split Transaction' : 'Split Transaction'
})

const parentAbsTotal = computed(() => {
  if (!splitTx.value) return 0
  return Math.abs(Number(splitTx.value.amount))
})

const parentTotalCents = computed(() => {
  return Math.round(parentAbsTotal.value * 100)
})

const allocatedTotalCents = computed(() => {
  return splitLines.value.reduce((sum, line) => {
    const val = parseFloat(line.amountStr)
    if (isNaN(val) || val <= 0) return sum
    return sum + Math.round(val * 100)
  }, 0)
})

const allocatedAbsTotal = computed(() => {
  return allocatedTotalCents.value / 100
})

const remainingCents = computed(() => {
  return parentTotalCents.value - allocatedTotalCents.value
})

const remainingAbsTotal = computed(() => {
  return Math.max(0, remainingCents.value) / 100
})

const isBalanced = computed(() => {
  return remainingCents.value === 0
})

const hasDuplicateCategories = computed(() => {
  const chosen = splitLines.value.map(l => l.category_id).filter(Boolean)
  return chosen.length !== new Set(chosen).size
})

const canSaveSplit = computed(() => {
  if (splitLines.value.length < 2) return false
  if (!isBalanced.value) return false
  if (hasDuplicateCategories.value) return false
  for (const line of splitLines.value) {
    if (!line.category_id) return false
    const val = parseFloat(line.amountStr)
    if (isNaN(val) || val <= 0) return false
  }
  return true
})

const mathStatusClass = computed(() => {
  if (isBalanced.value) return 'status-balanced'
  if (remainingCents.value > 0) return 'status-remaining'
  return 'status-over'
})

const openSplitDialog = async (tx: any) => {
  splitTx.value = tx
  splitDialogError.value = null
  unsplitTargetCategoryId.value = ''
  savingSplit.value = false
  unsplitInProgress.value = false

  if (tx.is_split) {
    if (tx.splits && tx.splits.length > 0) {
      splitLines.value = tx.splits.map((s: any) => ({
        category_id: s.category_id,
        amountStr: Math.abs(Number(s.amount)).toFixed(2),
      }))
    } else {
      try {
        const data = await $fetch<any[]>(`${API_BASE}/transactions/${tx.transaction_id}/splits`)
        splitLines.value = data.map((s: any) => ({
          category_id: s.category_id,
          amountStr: Math.abs(Number(s.amount)).toFixed(2),
        }))
      } catch (err: any) {
        splitLines.value = [
          { category_id: '', amountStr: '' },
          { category_id: '', amountStr: '' },
        ]
      }
    }
  } else {
    // New split: initialize with 2 lines
    splitLines.value = [
      {
        category_id: tx.category_id || '',
        amountStr: '',
      },
      {
        category_id: '',
        amountStr: '',
      },
    ]
  }

  splitDialogOpen.value = true
}

const closeSplitDialog = () => {
  splitDialogOpen.value = false
  splitTx.value = null
  splitLines.value = []
  splitDialogError.value = null
}

const addSplitLine = () => {
  let defaultAmountStr = ''
  if (remainingCents.value > 0) {
    defaultAmountStr = (remainingCents.value / 100).toFixed(2)
  }
  splitLines.value.push({
    category_id: '',
    amountStr: defaultAmountStr,
  })
}

const removeSplitLine = (idx: number) => {
  if (splitLines.value.length <= 2) return
  splitLines.value.splice(idx, 1)
}

const handleSaveSplit = async () => {
  if (!canSaveSplit.value || !splitTx.value) return
  savingSplit.value = true
  splitDialogError.value = null

  const isParentNegative = Number(splitTx.value.amount) < 0
  const payloadLines = splitLines.value.map(line => {
    const absVal = Math.abs(Number(line.amountStr))
    return {
      category_id: line.category_id,
      amount: isParentNegative ? -absVal : absVal,
    }
  })

  try {
    const res = await fetch(`${API_BASE}/transactions/${splitTx.value.transaction_id}/splits`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ splits: payloadLines }),
    })

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      throw new Error(errData.detail || 'Failed to save splits')
    }

    const updated = await res.json()
    if (transactionsData.value?.items) {
      const idx = transactionsData.value.items.findIndex(
        (t: any) => t.transaction_id === splitTx.value.transaction_id
      )
      if (idx !== -1) {
        transactionsData.value.items[idx] = updated
      }
    }

    delete suggestions.value[splitTx.value.transaction_id]
    closeSplitDialog()
    await refresh()
  } catch (err: any) {
    splitDialogError.value = err.message || 'Failed to save splits. Please check inputs.'
  } finally {
    savingSplit.value = false
  }
}

const handleUnsplit = async () => {
  if (!splitTx.value) return
  unsplitInProgress.value = true
  splitDialogError.value = null

  try {
    const res = await fetch(`${API_BASE}/transactions/${splitTx.value.transaction_id}/unsplit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        category_id: unsplitTargetCategoryId.value || null,
      }),
    })

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      throw new Error(errData.detail || 'Failed to unsplit transaction')
    }

    const updated = await res.json()
    if (transactionsData.value?.items) {
      const idx = transactionsData.value.items.findIndex(
        (t: any) => t.transaction_id === splitTx.value.transaction_id
      )
      if (idx !== -1) {
        transactionsData.value.items[idx] = updated
      }
    }

    closeSplitDialog()
    await refresh()
  } catch (err: any) {
    splitDialogError.value = err.message || 'Failed to unsplit transaction.'
  } finally {
    unsplitInProgress.value = false
  }
}
</script>

<style scoped>
.transactions-page {
  padding: var(--space-lg);
  max-width: var(--page-max-width);
  margin: 0 auto;
}

.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

/* Filters Card */
.filters-card {
  padding: var(--space-lg);
  margin-bottom: var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.filters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-md);
  align-items: flex-end;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.filter-group label {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.search-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.search-clear-btn {
  position: absolute;
  right: 8px;
  background: transparent;
  border: none;
  color: var(--color-text-light);
  cursor: pointer;
  padding: 4px;
  font-size: 0.75rem;
  line-height: 1;
  border-radius: var(--radius-xs);
}

.search-clear-btn:hover {
  color: var(--color-text);
}

.filter-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-family: inherit;
  color: var(--color-text);
  background: var(--color-surface);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  box-sizing: border-box;
}

.filter-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus);
}

/* Filters Meta Row */
.filters-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-sm);
  padding-top: var(--space-sm);
  border-top: 1px solid var(--color-border-subtle);
}

.filter-meta-left {
  display: flex;
  align-items: center;
}

.checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text);
  user-select: none;
}

.filter-checkbox {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
  cursor: pointer;
}

.filter-meta-right {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.filter-summary-text {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.summary-chips {
  color: var(--color-text);
  font-weight: var(--font-weight-medium);
}

.btn-clear-filters {
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-clear-filters:hover:not(:disabled) {
  background: var(--color-surface-hover);
  color: var(--color-text);
  border-color: var(--color-border-hover);
}

.btn-clear-filters:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 1px;
}

.btn-clear-filters:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Table Card & Responsive Wrapper */
.table-card {
  overflow: hidden;
}

.table-responsive {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.transactions-table {
  width: 100%;
  min-width: 640px;
  border-collapse: collapse;
  text-align: left;
}

.transactions-table th {
  padding: 12px 16px;
  background: #f8fafc;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.transactions-table td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-subtle);
  font-size: var(--font-size-base);
  color: var(--color-text);
}

.transactions-table tr:last-child td {
  border-bottom: none;
}

.transactions-table tbody tr:hover td {
  background-color: #fafbfc;
}

.date-col {
  width: 110px;
}

.date-cell {
  color: var(--color-text-muted);
  white-space: nowrap;
  font-size: var(--font-size-sm);
}

.desc-col {
  min-width: 220px;
}

.desc-cell {
  max-width: 340px;
}

.desc-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: var(--font-weight-medium);
}

.merchant-row {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  flex-wrap: wrap;
}

.merchant-name {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-base);
}

.merchant-name.is-overridden {
  color: var(--color-text-emphasis, #0f172a);
}

.btn-edit-merchant {
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  opacity: 0.6;
  transition: opacity 0.15s ease, background 0.15s ease;
  line-height: 1;
}

.btn-edit-merchant:hover {
  opacity: 1;
  background: var(--color-surface-hover);
  color: var(--color-primary);
}

.btn-edit-merchant:focus-visible {
  outline: 2px solid var(--color-primary);
  opacity: 1;
}

.raw-desc-text {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}

.merchant-edit-form {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  width: 100%;
}

.merchant-edit-input {
  padding: 3px 6px;
  font-size: var(--font-size-sm);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  width: 100%;
  max-width: 180px;
}

.merchant-edit-input:focus {
  outline: none;
  box-shadow: 0 0 0 2px var(--color-primary-focus);
}

.merchant-edit-actions {
  display: inline-flex;
  gap: 2px;
}

.btn-save-merchant,
.btn-cancel-merchant {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  font-size: var(--font-size-xs);
  cursor: pointer;
  line-height: 1.2;
}

.btn-save-merchant {
  color: var(--color-success);
  border-color: var(--color-success-border, #86efac);
}

.btn-save-merchant:hover:not(:disabled) {
  background: var(--color-success-bg, #f0fdf4);
}

.btn-cancel-merchant {
  color: var(--color-text-muted);
}

.btn-cancel-merchant:hover:not(:disabled) {
  background: var(--color-surface-hover);
}

.account-col {
  width: 140px;
}

.account-tag {
  background: var(--color-surface-hover);
  border: 1px solid var(--color-border-subtle);
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-muted);
  white-space: nowrap;
}

.category-col {
  width: 250px;
}

.ml-suggestion-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 6px;
  padding: 4px 8px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: var(--radius-sm);
  font-size: 11px;
  line-height: 1.2;
}

.ml-suggestion-text {
  color: #166534;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ml-suggestion-score {
  color: #15803d;
  font-size: 10px;
}

.btn-accept-suggestion {
  flex-shrink: 0;
  padding: 2px 7px;
  background: #16a34a;
  color: #ffffff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease;
}

.btn-accept-suggestion:hover:not(:disabled) {
  background: #15803d;
}

.btn-accept-suggestion:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.category-select {
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  width: 100%;
  max-width: 210px;
  background: var(--color-surface);
  color: var(--color-text);
  transition: border-color 0.15s ease;
  font-family: inherit;
}

.category-select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-focus);
}

.category-select.uncategorized {
  border-color: var(--color-danger-border);
  background-color: var(--color-danger-bg);
  color: var(--color-danger-hover);
  font-weight: var(--font-weight-medium);
}

.amount-col {
  text-align: right;
  width: 120px;
}

.amount-cell {
  text-align: right;
  font-weight: var(--font-weight-semibold);
}

.amount-cell.inflow {
  color: var(--color-success);
}

.empty-row {
  text-align: center;
  padding: 48px !important;
  color: var(--color-text-muted);
  font-style: italic;
}

/* Pagination */
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md) var(--space-lg);
  background: #f8fafc;
  border-top: 1px solid var(--color-border);
}

.page-btn {
  padding: 6px 14px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  transition: all 0.15s ease;
}

.page-btn:hover:not(:disabled) {
  background: var(--color-surface-hover);
  border-color: var(--color-border-hover);
}

.page-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 1px;
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

/* Header Transfer Button */
.btn-transfer-matches {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  padding: 8px 16px;
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-transfer-matches:hover:not(:disabled) {
  background: var(--color-surface-hover);
  border-color: var(--color-border-hover);
}

.btn-transfer-matches:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cand-badge {
  background: var(--color-primary);
  color: white;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
}

/* Transfer Panel */
.transfer-panel {
  padding: var(--space-lg);
  margin-bottom: var(--space-lg);
  background: #f8fafc;
  border: 1px solid #bfdbfe;
  border-radius: var(--radius-lg);
}

.panel-header {
  margin-bottom: var(--space-md);
}

.panel-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title-with-badge {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.panel-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  margin: 0;
}

.panel-count-badge {
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
}

.panel-sub {
  margin: var(--space-xs) 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.btn-close-panel {
  background: transparent;
  border: none;
  font-size: 1.1rem;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
}

.btn-close-panel:hover {
  background: var(--color-surface-hover);
  color: var(--color-text);
}

.empty-candidates {
  padding: var(--space-md);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  font-style: italic;
  text-align: center;
}

.panel-error {
  background: #fee2e2;
  color: #dc2626;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-md);
}

.candidate-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.candidate-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  padding: var(--space-md);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  flex-wrap: wrap;
}

.candidate-side {
  flex: 1;
  min-width: 140px;
}

.cand-account {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-sm);
  color: var(--color-text);
}

.cand-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
}

.cand-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.candidate-arrow {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.amount-badge {
  background: #f1f5f9;
  border: 1px solid var(--color-border);
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-sm);
  font-family: var(--font-mono);
  color: var(--color-text);
}

.arrow {
  color: var(--color-text-muted);
  font-weight: bold;
}

.candidate-actions {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.confirm-btn {
  background: var(--color-primary);
  color: white;
  border: none;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: background 0.15s ease;
}

.confirm-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.confirm-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.dismiss-btn {
  background: transparent;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.15s ease;
}

.dismiss-btn:hover {
  background: var(--color-surface-hover);
  color: var(--color-text);
}

/* Review Status Column & Button */
.status-col {
  width: 140px;
  text-align: center;
}

.status-cell {
  text-align: center;
  white-space: nowrap;
}

.review-toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s ease;
  user-select: none;
}

.review-toggle-btn.is-reviewed {
  background: #ecfdf5;
  color: #065f46;
  border-color: #a7f3d0;
}

.review-toggle-btn.is-reviewed:hover:not(:disabled) {
  background: #d1fae5;
  border-color: #6ee7b7;
}

.review-toggle-btn.needs-review {
  background: #fffbeb;
  color: #92400e;
  border-color: #fde68a;
}

.review-toggle-btn.needs-review:hover:not(:disabled) {
  background: #fef3c7;
  border-color: #fcd34d;
}

.review-toggle-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 1px;
}

.review-toggle-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.check-icon {
  font-weight: bold;
}

.status-label {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.transfer-tag {
  display: inline-block;
  margin-left: var(--space-xs);
  padding: 1px 6px;
  background: #f1f5f9;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: 10px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

/* Header Recurring Button */
.btn-recurring-matches {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  padding: 8px 16px;
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-recurring-matches:hover:not(:disabled) {
  background: var(--color-surface-hover);
  border-color: var(--color-border-hover);
}

.btn-recurring-matches:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Recurring Panel */
.recurring-panel {
  padding: var(--space-lg);
  margin-bottom: var(--space-lg);
  background: #f8fafc;
  border: 1px solid #cbd5e1;
  border-radius: var(--radius-lg);
}

.recurring-tabs {
  display: flex;
  gap: var(--space-xs);
  margin-top: var(--space-md);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-xs);
  flex-wrap: wrap;
}

.tab-btn {
  padding: 6px 12px;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}

.tab-btn:hover {
  background: var(--color-surface-hover);
  color: var(--color-text);
}

.tab-btn.active {
  background: var(--color-primary);
  color: #ffffff;
  font-weight: var(--font-weight-semibold);
}

.recurring-table-wrapper {
  overflow-x: auto;
  margin-top: var(--space-md);
}

.recurring-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.recurring-table th {
  text-align: left;
  padding: 8px 12px;
  border-bottom: 2px solid var(--color-border);
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.recurring-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border-subtle);
  vertical-align: middle;
}

.rec-merchant-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rec-merchant-name {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
}

.rec-account-name {
  font-size: 11px;
  color: var(--color-text-muted);
}

.cadence-tag {
  display: inline-block;
  padding: 2px 8px;
  background: #e0f2fe;
  color: #0369a1;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: var(--font-weight-semibold);
  text-transform: capitalize;
}

.amount-type-hint {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-left: 4px;
}

.status-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: var(--font-weight-semibold);
  text-transform: capitalize;
}

.status-pill.confirmed {
  background: #dcfce7;
  color: #15803d;
  border: 1px solid #86efac;
}

.status-pill.detected {
  background: #fef9c3;
  color: #a16207;
  border: 1px solid #fde047;
}

.status-pill.dismissed {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #cbd5e1;
}

.rec-actions-cell {
  white-space: nowrap;
}

.rec-actions-cell .confirm-btn,
.rec-actions-cell .dismiss-btn {
  margin-right: 6px;
}

/* Transaction Ledger Recurring Tag */
.recurring-tag {
  display: inline-block;
  margin-left: var(--space-xs);
  padding: 1px 6px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: var(--radius-sm);
  font-size: 10px;
  font-weight: var(--font-weight-semibold);
  color: #166534;
  letter-spacing: 0.02em;
}

/* Split Transactions Ledger Elements */
.split-cell-content {
  display: flex;
  align-items: center;
}

.btn-split-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: #f0fdf4;
  border: 1px solid #86efac;
  border-radius: var(--radius-full);
  color: #166534;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-split-badge:hover {
  background: #dcfce7;
  border-color: #4ade80;
  box-shadow: var(--shadow-sm);
}

.split-badge-icon {
  font-size: 13px;
  line-height: 1;
}

.category-select-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-split-trigger {
  padding: 5px 8px;
  background: transparent;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: 11px;
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.btn-split-trigger:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-bg, #f0f7ff);
}

/* Split Transaction Modal */
.split-dialog-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.split-parent-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-sm);
  background: #f8fafc;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-md);
}

.summary-col {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-label {
  font-size: 11px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.summary-val {
  font-size: var(--font-size-sm);
  color: var(--color-text);
}

.summary-val.inflow {
  color: var(--color-success);
}

.split-error-alert {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: var(--radius-sm);
  color: #dc2626;
  font-size: var(--font-size-sm);
}

.split-error-alert .alert-dismiss {
  background: none;
  border: none;
  color: #dc2626;
  font-size: 14px;
  cursor: pointer;
  padding: 0 4px;
}

.split-allocations-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.split-allocations-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.section-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
}

.split-rule-hint {
  font-size: 11px;
  color: var(--color-text-muted);
}

.split-lines-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.split-line-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.line-category-col {
  flex: 1;
}

.split-select {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  background: var(--color-surface);
  color: var(--color-text);
}

.split-select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-focus);
}

.line-amount-col {
  width: 150px;
}

.amount-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.currency-prefix {
  position: absolute;
  left: 10px;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  pointer-events: none;
}

.split-amount-input {
  width: 100%;
  padding: 7px 10px 7px 24px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  text-align: right;
  background: var(--color-surface);
  color: var(--color-text);
}

.split-amount-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-focus);
}

.line-actions-col {
  width: 68px;
  display: flex;
  justify-content: flex-end;
}

.btn-remove-line {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  font-size: 11px;
  font-weight: var(--font-weight-medium);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-remove-line:hover:not(:disabled) {
  background: #fef2f2;
  border-color: #fecaca;
  color: #dc2626;
}

.btn-remove-line:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.split-add-line-row {
  margin-top: 4px;
}

.btn-add-split-line {
  background: none;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-sm);
  padding: 6px 12px;
  color: var(--color-primary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-add-split-line:hover {
  background: var(--color-primary-bg, #f0f7ff);
  border-color: var(--color-primary);
}

/* Allocation Math Bar */
.split-math-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  border: 1px solid var(--color-border);
  background: #f8fafc;
}

.split-math-bar.status-balanced {
  background: #f0fdf4;
  border-color: #bbf7d0;
}

.split-math-bar.status-remaining {
  background: #fffbeb;
  border-color: #fde68a;
}

.split-math-bar.status-over {
  background: #fef2f2;
  border-color: #fecaca;
}

.math-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.math-label {
  font-size: 11px;
  color: var(--color-text-muted);
}

.math-val {
  font-weight: var(--font-weight-semibold);
}

.math-operator {
  color: var(--color-text-muted);
  font-weight: bold;
}

.math-status-badge {
  margin-left: auto;
}

.badge-balanced {
  font-size: 11px;
  font-weight: var(--font-weight-bold);
  color: #15803d;
  background: #dcfce7;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.badge-remaining {
  font-size: 11px;
  font-weight: var(--font-weight-semibold);
  color: #b45309;
  background: #fef3c7;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.badge-over {
  font-size: 11px;
  font-weight: var(--font-weight-semibold);
  color: #b91c1c;
  background: #fee2e2;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.split-warning-msg {
  padding: 6px 12px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: #92400e;
}

/* Unsplit Section */
.unsplit-collapse-box {
  margin-top: var(--space-xs);
  padding: 12px;
  background: #f8fafc;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.unsplit-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.unsplit-title {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
}

.unsplit-subtitle {
  font-size: 11px;
  color: var(--color-text-muted);
}

.unsplit-controls {
  display: flex;
  gap: 8px;
}

.unsplit-category-select {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  background: var(--color-surface);
  color: var(--color-text);
}

.btn-unsplit-action {
  padding: 6px 12px;
  border: 1px solid #cbd5e1;
  border-radius: var(--radius-sm);
  background: #fff;
  color: #475569;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-unsplit-action:hover:not(:disabled) {
  background: #f1f5f9;
  border-color: #94a3b8;
  color: #1e293b;
}

/* Dialog Footer */
.split-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  width: 100%;
}

.btn-dialog-cancel {
  padding: 8px 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--color-text);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-dialog-cancel:hover:not(:disabled) {
  background: #f8fafc;
}

.btn-dialog-save {
  padding: 8px 18px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: #fff;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-dialog-save:hover:not(:disabled) {
  background: var(--color-primary-hover, #2563eb);
}

.btn-dialog-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
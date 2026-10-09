<template>
  <div class="transactions-page page-container page-container--wide">
    <PageHeader
      title="Transactions"
      subtitle="Browse and categorize bank transactions"
    >
      <template #controls>
        <MonthNavigator />
      </template>
      <template #actions>
        <!-- Secondary workflows: quiet buttons so they do not compete with the title -->
        <button
          type="button"
          class="btn btn-ghost btn-sm btn-transfer-matches"
          :class="{ 'is-open': showTransfersPanel }"
          @click="toggleTransfersPanel"
          :disabled="candidatesLoading"
          :aria-expanded="showTransfersPanel"
          aria-label="Find and review transfer matches"
        >
          <AppIcon name="transactions" :size="16" />
          Find transfer matches
          <span v-if="candidates.length > 0" class="cand-badge num">{{ candidates.length }}</span>
        </button>
        <button
          type="button"
          class="btn btn-ghost btn-sm btn-recurring-matches"
          :class="{ 'is-open': showRecurringPanel }"
          @click="toggleRecurringPanel"
          :disabled="recurringLoading"
          :aria-expanded="showRecurringPanel"
          aria-label="View and manage recurring activity"
        >
          <AppIcon name="repeat" :size="16" />
          Recurring
          <span v-if="activeRecurringCount > 0" class="cand-badge num">{{ activeRecurringCount }}</span>
        </button>
      </template>
    </PageHeader>

    <ErrorBanner
      v-if="displayError"
      :error="displayError"
      @dismiss="clearErrors"
    />

    <!-- Transfer review panel -->
    <section v-if="showTransfersPanel" class="tx-panel transfer-panel" aria-label="Transfer matches review">
      <div class="panel-header">
        <div class="panel-titles">
          <h2 class="panel-title">Potential transfers</h2>
          <span v-if="candidates.length > 0" class="panel-count">
            {{ candidates.length }} {{ candidates.length === 1 ? 'match' : 'matches' }}
          </span>
        </div>
        <button type="button" class="btn-icon btn-close-panel" @click="showTransfersPanel = false" aria-label="Close transfer matches panel">
          <AppIcon name="close" :size="16" />
        </button>
        <p class="panel-sub">
          These look like transfers appearing on both accounts (credit card payments, savings moves, etc.). Confirm pairs to mark them as transfers.
        </p>
      </div>

      <LoadingState v-if="candidatesLoading" message="Finding transfer matches..." />

      <div v-else-if="transferError" class="panel-error" role="alert">
        {{ transferError }}
      </div>

      <div v-else-if="candidates.length === 0" class="panel-empty">
        <p>No potential transfer matches found.</p>
      </div>

      <ul v-else class="candidate-list panel-scroll" tabindex="0" aria-label="Transfer match candidates">
        <li v-for="(pair, idx) in candidates" :key="idx" class="candidate-row">
          <div class="candidate-side outflow">
            <span class="sr-only">From</span>
            <span class="cand-account">{{ pair.outflow_account_name }}</span>
            <span class="cand-desc" :title="pair.outflow_side.description">{{ pair.outflow_side.description }}</span>
            <span class="cand-meta num">{{ formatDate(pair.outflow_side.date) }}</span>
          </div>
          <div class="candidate-arrow">
            <span class="amount-badge money num">{{ formatCurrency(Math.abs(Number(pair.outflow_side.amount))) }}</span>
            <AppIcon name="arrow" :size="16" class="cand-arrow-icon" />
          </div>
          <div class="candidate-side inflow">
            <span class="sr-only">To</span>
            <span class="cand-account">{{ pair.inflow_account_name }}</span>
            <span class="cand-desc" :title="pair.inflow_side.description">{{ pair.inflow_side.description }}</span>
            <span class="cand-meta num">{{ formatDate(pair.inflow_side.date) }}</span>
          </div>
          <div class="candidate-actions">
            <button
              type="button"
              class="btn btn-secondary btn-sm confirm-btn"
              @click="confirmTransfer(pair, idx)"
              :disabled="confirmingPair"
              :aria-label="`Confirm transfer between ${pair.outflow_account_name} and ${pair.inflow_account_name}`"
            >
              Confirm
            </button>
            <button
              type="button"
              class="btn btn-ghost btn-sm dismiss-btn"
              @click="dismissTransfer(idx)"
              :aria-label="`Dismiss candidate match between ${pair.outflow_account_name} and ${pair.inflow_account_name}`"
            >
              Dismiss
            </button>
          </div>
        </li>
      </ul>
    </section>

    <!-- Recurring activity panel -->
    <section v-if="showRecurringPanel" class="tx-panel recurring-panel" aria-label="Recurring activity review">
      <div class="panel-header">
        <div class="panel-titles">
          <h2 class="panel-title">Recurring Activity</h2>
          <span v-if="activeRecurringCount > 0" class="panel-count">
            {{ activeRecurringCount }} {{ activeRecurringCount === 1 ? 'pattern' : 'patterns' }}
          </span>
        </div>
        <button type="button" class="btn-icon btn-close-panel" @click="showRecurringPanel = false" aria-label="Close recurring panel">
          <AppIcon name="close" :size="16" />
        </button>
        <p class="panel-sub">
          Automatically detected repeating bills, subscriptions, and income patterns. Confirm genuine items or dismiss non-recurring charges.
        </p>
      </div>

      <div class="recurring-tabs" role="tablist" aria-label="Recurring pattern filter tabs">
        <button
          v-for="tab in recurringTabs"
          :id="`recurring-tab-${tab.value}`"
          :key="tab.value"
          type="button"
          role="tab"
          :aria-selected="recurringTab === tab.value"
          aria-controls="recurring-tabpanel"
          class="tab-btn"
          :class="{ active: recurringTab === tab.value }"
          @click="recurringTab = tab.value"
        >
          {{ tab.label }} <span class="tab-count num">{{ tab.count }}</span>
        </button>
      </div>

      <div
        id="recurring-tabpanel"
        class="recurring-tabpanel"
        role="tabpanel"
        :aria-labelledby="`recurring-tab-${recurringTab}`"
      >
        <LoadingState v-if="recurringLoading" message="Analyzing recurring patterns..." />

        <div v-else-if="recurringError" class="panel-error" role="alert">
          {{ recurringError }}
        </div>

        <div v-else-if="filteredRecurringItems.length === 0" class="panel-empty">
          <p>No recurring patterns found in this view.</p>
        </div>

        <div v-else class="recurring-table-wrapper panel-scroll" tabindex="0" aria-label="Recurring items, scrollable">
          <table class="recurring-table" aria-label="Recurring items table">
            <thead>
              <tr>
                <th scope="col">Merchant</th>
                <th scope="col">Cadence</th>
                <th scope="col" class="col-num">Typical amount</th>
                <th scope="col">Next expected</th>
                <th scope="col">History</th>
                <th scope="col">Status</th>
                <th scope="col" class="col-actions"><span class="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredRecurringItems" :key="item.id" class="recurring-row">
                <td class="rec-merchant-cell">
                  <span class="rec-merchant-name">{{ item.merchant }}</span>
                  <span class="rec-account-name">{{ item.account_name || 'Account' }}</span>
                </td>
                <td class="rec-cadence-cell">
                  <span class="cadence-tag">{{ item.cadence }}</span>
                </td>
                <td class="rec-amount-cell col-num">
                  <span class="money num">{{ formatCurrency(Number(item.expected_amount)) }}</span>
                  <span class="amount-type-hint">{{ item.amount_type }}</span>
                </td>
                <td class="rec-next-date-cell num">
                  {{ item.next_expected_date ? formatDate(item.next_expected_date) : 'N/A' }}
                </td>
                <td class="rec-count-cell num">
                  {{ item.occurrence_count }} occurrences
                </td>
                <td class="rec-status-cell">
                  <span class="rec-status" :class="`rec-status--${item.status}`">
                    <AppIcon
                      :name="item.status === 'confirmed' ? 'check-circle' : item.status === 'detected' ? 'clock' : 'circle'"
                      :size="14"
                    />
                    <span class="status-pill">{{ item.status }}</span>
                  </span>
                </td>
                <td class="rec-actions-cell">
                  <button
                    v-if="item.status !== 'confirmed'"
                    type="button"
                    class="btn btn-secondary btn-sm confirm-btn"
                    @click="confirmRecurring(item)"
                    :disabled="recurringActionId === item.id"
                    :aria-label="`Confirm recurring pattern for ${item.merchant}`"
                  >
                    Confirm
                  </button>
                  <button
                    v-if="item.status !== 'dismissed'"
                    type="button"
                    class="btn btn-ghost btn-sm dismiss-btn"
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
      </div>
    </section>

    <!-- Filter toolbar -->
    <section class="tx-toolbar" aria-label="Transaction filters">
      <div class="toolbar-controls">
        <div class="filter-group filter-group--search">
          <label for="tx-search-input" class="filter-label">Search</label>
          <div class="search-input-wrapper">
            <AppIcon name="search" :size="16" class="search-icon" />
            <input
              id="tx-search-input"
              type="text"
              v-model="searchQuery"
              placeholder="Search description or merchant..."
              class="filter-input search-input"
              aria-label="Search transaction description or merchant"
            />
            <button
              v-if="searchQuery"
              type="button"
              class="btn-icon search-clear-btn"
              @click="searchQuery = ''"
              aria-label="Clear search input"
              title="Clear search"
            >
              <AppIcon name="close" :size="14" />
            </button>
          </div>
        </div>

        <!-- Narrow screens: the remaining filters sit behind this disclosure -->
        <button
          type="button"
          class="btn btn-ghost filters-toggle"
          :class="{ 'is-open': filtersOpen }"
          :aria-expanded="filtersOpen"
          aria-controls="tx-filter-fields"
          @click="filtersOpen = !filtersOpen"
        >
          <AppIcon name="filter" :size="16" />
          Filters
          <span v-if="activeFilterCount > 0" class="filters-toggle-count num">
            {{ activeFilterCount }}<span class="sr-only"> active</span>
          </span>
          <AppIcon name="chevron" :size="14" class="filters-toggle-chevron" />
        </button>

        <div id="tx-filter-fields" class="filter-fields" :class="{ 'is-open': filtersOpen }">
          <!-- Account filter (route-backed) -->
          <div class="filter-group">
            <label for="tx-account-select" class="filter-label">Account</label>
            <select
              id="tx-account-select"
              v-model="selectedAccount"
              class="filter-input"
              :class="{ 'is-active': selectedAccount }"
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

          <div class="filter-group">
            <label for="tx-category-select" class="filter-label">Category</label>
            <select
              id="tx-category-select"
              v-model="selectedCategory"
              class="filter-input"
              :class="{ 'is-active': selectedCategory }"
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

          <div class="filter-group">
            <label for="tx-review-select" class="filter-label">Review status</label>
            <select
              id="tx-review-select"
              v-model="reviewFilter"
              class="filter-input"
              :class="{ 'is-active': reviewFilter !== 'all' }"
              aria-label="Filter by review status"
            >
              <option value="all">All</option>
              <option value="needs_review">Needs Review</option>
              <option value="reviewed">Reviewed</option>
            </select>
          </div>

          <div class="filter-group filter-group--check">
            <label class="checkbox-label" for="tx-uncategorized-checkbox">
              <input
                type="checkbox"
                id="tx-uncategorized-checkbox"
                v-model="uncategorizedOnly"
                class="form-checkbox filter-checkbox"
              />
              <span>Uncategorized only</span>
            </label>
          </div>
        </div>
      </div>

      <div class="toolbar-summary">
        <span class="filter-summary-text" aria-live="polite">
          <span class="summary-count num">{{ transactionCountLabel }}</span>
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
    </section>

    <LoadingState
      v-if="pending && !transactionsData"
      message="Loading transactions..."
    />

    <!-- Ledger -->
    <div v-else class="transactions-container">
      <div class="ledger surface-card">
        <div class="table-responsive">
          <table class="transactions-table" aria-label="Transactions ledger" role="table">
            <thead role="rowgroup">
              <tr role="row">
                <th scope="col" class="date-col" role="columnheader">Date</th>
                <th scope="col" class="desc-col" role="columnheader">Merchant / Description</th>
                <th scope="col" class="account-col" role="columnheader">Account</th>
                <th scope="col" class="category-col" role="columnheader">Category</th>
                <th scope="col" class="amount-col" role="columnheader">Amount</th>
                <th scope="col" class="status-col" role="columnheader">Review</th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              <tr
                v-for="tx in transactionsData?.items"
                :key="tx.transaction_id"
                :data-tx-id="tx.transaction_id"
                class="tx-row"
                role="row"
                :class="{
                  'is-unreviewed': !tx.is_reviewed,
                  'is-pending': tx.pending,
                }"
              >
                <td class="date-cell num" role="cell">{{ formatDate(tx.date) }}</td>
                <td class="desc-cell" role="cell" :class="{ 'is-editing': editingMerchantId === tx.transaction_id }">
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
                      <button
                        type="submit"
                        class="btn-icon btn-save-merchant"
                        :disabled="savingMerchant"
                        aria-label="Save merchant"
                        title="Save"
                      >
                        <AppIcon name="check" :size="16" />
                      </button>
                      <button
                        type="button"
                        class="btn-icon btn-cancel-merchant"
                        @click="cancelEditingMerchant"
                        :disabled="savingMerchant"
                        aria-label="Cancel editing merchant"
                        title="Cancel"
                      >
                        <AppIcon name="close" :size="16" />
                      </button>
                    </form>
                  </template>
                  <template v-else>
                    <div class="merchant-row">
                      <span
                        class="merchant-name"
                        :class="{ 'is-overridden': tx.is_merchant_overridden }"
                        :title="tx.merchant || tx.description"
                      >
                        {{ tx.merchant || tx.description }}
                      </span>
                      <button
                        type="button"
                        class="btn-icon btn-edit-merchant"
                        @click="startEditingMerchant(tx)"
                        :aria-label="`Edit merchant for ${tx.merchant || tx.description}`"
                        title="Edit merchant"
                      >
                        <AppIcon name="edit" :size="14" />
                      </button>
                    </div>
                  </template>
                  <div class="tx-meta">
                    <!-- Shown only when the Account column is folded away -->
                    <span class="account-inline">{{ tx.account?.name || 'Unknown' }}</span>
                    <span
                      v-if="tx.pending"
                      class="tx-flag tx-flag--pending"
                      title="Not yet posted by the bank"
                    ><AppIcon name="clock" :size="12" />Pending</span>
                    <span v-if="tx.is_transfer" class="tx-flag transfer-tag"><AppIcon name="transactions" :size="12" />Transfer</span>
                    <span v-if="getRecurringCadenceForTx(tx)" class="tx-flag recurring-tag"><AppIcon name="repeat" :size="12" />Recurring · {{ getRecurringCadenceForTx(tx) }}</span>
                    <span
                      v-if="tx.merchant && tx.merchant.toLowerCase() !== tx.description.toLowerCase()"
                      class="raw-desc-text"
                      :title="`Original description: ${tx.description}`"
                    >
                      {{ tx.description }}
                    </span>
                  </div>
                </td>
                <td class="account-cell" role="cell">
                  <span class="account-name" :title="tx.account?.name || 'Unknown'">{{ tx.account?.name || 'Unknown' }}</span>
                </td>
                <td class="category-cell" role="cell">
                  <div v-if="tx.is_split" class="split-cell-content">
                    <button
                      type="button"
                      class="btn-split-badge"
                      @click="openSplitDialog(tx)"
                      :title="`Split across ${tx.split_count} categories. Click to view or edit.`"
                      :aria-label="`Split across ${tx.split_count} categories for transaction ${tx.merchant || tx.description}`"
                    >
                      <AppIcon name="split" :size="14" />
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
                        <AppIcon name="split" :size="14" />
                        <span class="split-trigger-text">Split</span>
                      </button>
                    </div>
                  </div>
                </td>
                <td
                  class="amount-cell"
                  role="cell"
                  :class="{ 'inflow': tx.amount < 0 }"
                >
                  <!-- Existing sign convention: inflows (negative) display with an explicit + -->
                  <span class="money" :class="tx.amount < 0 ? 'money--inflow' : 'money--outflow'">{{ tx.amount < 0 ? '+' : '' }}{{ formatCurrency(Math.abs(Number(tx.amount))) }}</span>
                </td>
                <td class="status-cell" role="cell">
                  <button
                    type="button"
                    class="review-toggle-btn"
                    :class="tx.is_reviewed ? 'is-reviewed' : 'needs-review'"
                    @click="toggleReviewStatus(tx)"
                    :disabled="updatingReviewId === tx.transaction_id"
                    :title="tx.is_reviewed ? 'Reviewed' : 'Needs review'"
                    :aria-label="tx.is_reviewed ? `Mark transaction ${tx.description} as needs review` : `Mark transaction ${tx.description} as reviewed`"
                  >
                    <AppIcon :name="tx.is_reviewed ? 'check-circle' : 'circle'" :size="16" class="review-icon" />
                    <span class="status-label">{{ tx.is_reviewed ? 'Reviewed' : 'Needs review' }}</span>
                  </button>
                </td>
              </tr>
              <tr v-if="transactionsData?.items.length === 0" class="empty-tr" role="row">
                <td colspan="6" class="empty-row" role="cell">
                  <template v-if="hasAnyFilter">
                    <p>No transactions found matching current filters.</p>
                    <button
                      v-if="hasActiveSecondaryFilters"
                      type="button"
                      class="btn btn-ghost btn-sm"
                      @click="clearSecondaryFilters"
                    >
                      Clear filters
                    </button>
                  </template>
                  <p v-else>No transactions for this month.</p>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <nav v-if="transactionsData?.total > limit" class="pagination" aria-label="Transaction pages">
          <span class="page-info num">
            Showing {{ offset + 1 }}–{{ Math.min(offset + limit, transactionsData.total) }} of {{ transactionsData.total }}
          </span>
          <div class="page-buttons">
            <button
              type="button"
              :disabled="offset === 0"
              @click="offset = Math.max(0, offset - limit)"
              class="btn btn-ghost btn-sm page-btn"
              aria-label="Previous page"
            >
              Previous
            </button>
            <button
              type="button"
              :disabled="offset + limit >= transactionsData.total"
              @click="offset += limit"
              class="btn btn-ghost btn-sm page-btn"
              aria-label="Next page"
            >
              Next
            </button>
          </div>
        </nav>
      </div>
    </div>

    <!-- Split transaction dialog -->
    <AppDialog
      :open="splitDialogOpen"
      :title="splitDialogTitle"
      max-width="660px"
      @close="closeSplitDialog"
    >
      <div v-if="splitTx" class="split-dialog-body">
        <dl class="split-parent-summary">
          <div class="summary-col">
            <dt class="summary-label">Date</dt>
            <dd class="summary-val num">{{ formatDate(splitTx.date) }}</dd>
          </div>
          <div class="summary-col summary-col--wide">
            <dt class="summary-label">Merchant / Description</dt>
            <dd class="summary-val summary-val--strong">{{ splitTx.merchant || splitTx.description }}</dd>
          </div>
          <div class="summary-col">
            <dt class="summary-label">Account</dt>
            <dd class="summary-val">{{ splitTx.account?.name || 'Unknown' }}</dd>
          </div>
          <div class="summary-col summary-col--num">
            <dt class="summary-label">Transaction total</dt>
            <dd class="summary-val summary-val--strong">
              <span class="money" :class="Number(splitTx.amount) < 0 ? 'money--inflow' : 'money--outflow'">{{ Number(splitTx.amount) < 0 ? '+' : '' }}{{ formatCurrency(Math.abs(Number(splitTx.amount))) }}</span>
            </dd>
          </div>
        </dl>

        <div v-if="splitDialogError" class="split-error-alert" role="alert">
          <span>{{ splitDialogError }}</span>
          <button type="button" class="btn-icon alert-dismiss" @click="splitDialogError = null" aria-label="Dismiss error">
            <AppIcon name="close" :size="14" />
          </button>
        </div>

        <div class="split-allocations-section">
          <div class="split-allocations-header">
            <h3 class="split-section-title">Category allocations</h3>
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
                  class="form-select split-select"
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
                  <span class="currency-prefix num" aria-hidden="true">{{ Number(splitTx.amount) < 0 ? '-$' : '$' }}</span>
                  <input
                    :id="`split-amount-${idx}`"
                    v-model="line.amountStr"
                    type="number"
                    step="0.01"
                    min="0.01"
                    placeholder="0.00"
                    class="form-input split-amount-input num"
                    :aria-label="`Amount for split line ${idx + 1}`"
                  />
                </div>
              </div>

              <div class="line-actions-col">
                <button
                  type="button"
                  class="btn btn-ghost btn-sm btn-remove-line"
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
              class="btn btn-ghost btn-sm btn-add-split-line"
              @click="addSplitLine"
            >
              + Add Category Line
            </button>
          </div>
        </div>

        <!-- Allocation reconciliation: Total − Allocated = Remaining -->
        <div class="split-math-bar" :class="mathStatusClass">
          <div class="math-item">
            <span class="math-label">Transaction total</span>
            <span class="math-val num">{{ formatCurrency(parentAbsTotal) }}</span>
          </div>
          <div class="math-operator" aria-hidden="true">−</div>
          <div class="math-item">
            <span class="math-label">Allocated</span>
            <span class="math-val num">{{ formatCurrency(allocatedAbsTotal) }}</span>
          </div>
          <div class="math-operator" aria-hidden="true">=</div>
          <div class="math-item">
            <span class="math-label">Remaining</span>
            <span class="math-val math-val--strong num">{{ formatCurrency(remainingAbsTotal) }}</span>
          </div>
          <div class="math-status-badge">
            <span v-if="isBalanced" class="badge-balanced"><AppIcon name="check" :size="14" />Balanced</span>
            <span v-else-if="remainingCents > 0" class="badge-remaining num">
              ${{ (remainingCents / 100).toFixed(2) }} unallocated
            </span>
            <span v-else class="badge-over num">
              ${{ (Math.abs(remainingCents) / 100).toFixed(2) }} overallocated
            </span>
          </div>
        </div>

        <div v-if="hasDuplicateCategories" class="split-warning-msg" role="alert">
          Each split line must be assigned to a different category.
        </div>

        <div v-if="splitTx.is_split" class="unsplit-collapse-box">
          <div class="unsplit-header">
            <span class="unsplit-title">Convert back to single category</span>
            <span class="unsplit-subtitle">Removes all split allocations and restores a single category.</span>
          </div>
          <div class="unsplit-controls">
            <select
              v-model="unsplitTargetCategoryId"
              class="form-select unsplit-category-select"
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
              class="btn btn-secondary btn-sm btn-unsplit-action"
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
            class="btn btn-ghost btn-dialog-cancel"
            @click="closeSplitDialog"
            :disabled="savingSplit || unsplitInProgress"
          >
            Cancel
          </button>
          <button
            type="button"
            class="btn btn-primary btn-dialog-save"
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

const recurringTabs = computed(() => {
  const countOf = (status: RecurringItem['status']) => recurringItems.value.filter(i => i.status === status).length
  return [
    { value: 'all', label: 'All', count: recurringItems.value.length },
    { value: 'confirmed', label: 'Confirmed', count: countOf('confirmed') },
    { value: 'detected', label: 'Needs review', count: countOf('detected') },
    { value: 'dismissed', label: 'Dismissed', count: countOf('dismissed') },
  ] as const
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

// Presentation-only UI state: none of this feeds the query or filter state
const filtersOpen = ref(false)

// Filters hidden behind the narrow-screen disclosure (search stays visible)
const activeFilterCount = computed(() => {
  let count = 0
  if (selectedAccount.value) count++
  if (selectedCategory.value) count++
  if (uncategorizedOnly.value) count++
  if (reviewFilter.value !== 'all') count++
  return count
})

const hasAnyFilter = computed(() => Boolean(selectedAccount.value) || hasActiveSecondaryFilters.value)

// Inline Merchant Editing
const editingMerchantId = ref<string | null>(null)
const editMerchantValue = ref('')
const savingMerchant = ref(false)
// Template ref inside v-for: Vue fills it as an array (only one editor is open at a time)
const merchantInputRef = ref<HTMLInputElement | HTMLInputElement[] | null>(null)

const startEditingMerchant = (tx: any) => {
  editingMerchantId.value = tx.transaction_id
  editMerchantValue.value = tx.merchant || tx.description || ''
  nextTick(() => {
    const input = Array.isArray(merchantInputRef.value) ? merchantInputRef.value[0] : merchantInputRef.value
    if (input) {
      input.focus()
      input.select()
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
/* Header actions ---------------------------------------------------------- */

.btn-transfer-matches,
.btn-recurring-matches {
  color: var(--text-secondary);
}

.btn-transfer-matches.is-open,
.btn-recurring-matches.is-open {
  background-color: var(--accent-subtle);
  border-color: var(--accent-primary);
  color: var(--accent-text);
}

.cand-badge {
  min-width: 1.25rem;
  padding: 0 5px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  line-height: 1.5;
  text-align: center;
  color: var(--text-primary);
  background: var(--bg-subtle);
  border-radius: var(--radius-xs);
}

/* Secondary panels (transfers, recurring) ---------------------------------- */
/* User-opened and bounded, so they get a quiet surface; their lists scroll   */
/* internally so the ledger stays near the fold.                              */

.tx-panel {
  margin-bottom: var(--space-md);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.panel-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  column-gap: var(--space-sm);
  padding: 10px 8px 10px var(--space-md);
}

.panel-titles {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 2px var(--space-sm);
  min-width: 0;
}

.panel-title {
  margin: 0;
  font-size: var(--type-subheading-size);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.panel-count {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
  font-variant-numeric: var(--font-numeric-features);
}

.panel-sub {
  grid-column: 1 / -1;
  margin: 2px 0 0;
  max-width: 80ch;
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.panel-error {
  margin: 0 var(--space-md) var(--space-md);
  padding: var(--space-sm) var(--space-md);
  font-size: var(--type-meta-size);
  color: var(--status-error);
  background: var(--status-error-bg);
  border-left: 3px solid var(--status-error);
}

.panel-empty {
  padding: var(--space-md);
  border-top: 1px solid var(--border-subtle);
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.panel-empty p {
  margin: 0;
}

.panel-scroll {
  max-height: 296px;
  overflow: auto;
  border-top: 1px solid var(--border-subtle);
  overscroll-behavior: contain;
}

.panel-scroll:focus-visible {
  outline-offset: -2px;
}

.tx-panel :deep(.loading-state) {
  min-height: 0;
  padding: var(--space-lg) var(--space-md);
}

/* Transfer candidates */

.candidate-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.candidate-row {
  display: grid;
  /* fixed amount/action tracks so every pair lines up with the next */
  grid-template-columns: minmax(0, 1fr) 8.5rem minmax(0, 1fr) 10.5rem;
  align-items: center;
  gap: var(--space-xs) var(--space-md);
  padding: 8px var(--space-md);
}

.candidate-row + .candidate-row {
  border-top: 1px solid var(--border-subtle);
}

.candidate-side {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.35;
}

.cand-account {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cand-desc,
.cand-meta {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.candidate-arrow {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-sm);
  color: var(--text-muted);
}

.amount-badge {
  font-weight: var(--font-weight-semibold);
  color: var(--financial-neutral);
}

.candidate-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-xs);
}

@media (max-width: 767px) {
  .candidate-row {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    grid-template-areas:
      "amount amount"
      "out in"
      "actions actions";
    align-items: start;
  }

  .candidate-side.outflow { grid-area: out; }
  .candidate-side.inflow { grid-area: in; }
  .candidate-arrow { grid-area: amount; }
  .candidate-actions { grid-area: actions; }

  .candidate-arrow {
    flex-direction: row-reverse;
    justify-content: flex-end;
  }
}

/* Recurring tabs + table */

.recurring-tabs {
  display: flex;
  gap: var(--space-md);
  padding: 0 var(--space-md);
  overflow-x: auto;
  border-bottom: 1px solid var(--border-subtle);
}

.tab-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 0 2px;
  font: inherit;
  font-size: var(--type-meta-size);
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
  white-space: nowrap;
  background: none;
  border: 0;
  cursor: pointer;
}

.tab-btn:hover {
  color: var(--text-primary);
}

.tab-btn.active {
  color: var(--accent-text);
}

/* Selected tab: an underline (not only a color change) */
.tab-btn.active::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 2px;
  background: var(--accent-primary);
}

.tab-count {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.recurring-tabpanel .panel-scroll {
  border-top: 0;
}

.recurring-table {
  width: 100%;
  min-width: 680px;
  border-collapse: collapse;
  font-size: var(--type-meta-size);
}

.recurring-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 7px 12px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  text-align: left;
  color: var(--table-header-text);
  background: var(--table-header);
  border-bottom: 1px solid var(--border-default);
  white-space: nowrap;
}

.recurring-table td {
  padding: 6px 12px;
  vertical-align: middle;
  border-bottom: 1px solid var(--table-border);
  color: var(--text-secondary);
}

.recurring-row:last-child td {
  border-bottom: 0;
}

.recurring-row:hover td {
  background: var(--table-hover);
}

.recurring-table .col-num {
  text-align: right;
}

.recurring-table .col-actions {
  width: 1%;
}

.rec-merchant-cell {
  max-width: 260px;
}

.rec-merchant-name,
.rec-account-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rec-merchant-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.rec-account-name {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.cadence-tag {
  text-transform: capitalize;
}

.rec-amount-cell {
  white-space: nowrap;
}

.rec-amount-cell .money {
  color: var(--financial-neutral);
  font-weight: var(--font-weight-medium);
}

.amount-type-hint {
  display: block;
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.rec-next-date-cell,
.rec-count-cell {
  white-space: nowrap;
}

.rec-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
}

/* Raw status text kept; capitalized for display */
.status-pill {
  text-transform: capitalize;
}

.rec-status--confirmed { color: var(--status-success); }
.rec-status--detected { color: var(--status-warning); }
.rec-status--dismissed { color: var(--text-muted); }

.rec-actions-cell {
  white-space: nowrap;
  text-align: right;
}

.rec-actions-cell .btn + .btn {
  margin-left: var(--space-xs);
}

/* Filter toolbar ----------------------------------------------------------- */

.tx-toolbar {
  margin-bottom: var(--space-sm);
}

.toolbar-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--space-sm) var(--space-sm);
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.filter-group--search {
  flex: 1 1 260px;
}

.filter-fields {
  flex: 3 1 600px;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--space-sm);
  min-width: 0;
}

.filter-fields > .filter-group {
  flex: 1 1 150px;
}

.filter-fields > .filter-group--check {
  flex: 0 0 auto;
}

.filter-label {
  font-size: var(--font-size-xs);
  font-weight: var(--type-label-weight);
  color: var(--text-secondary);
}

.filter-input {
  width: 100%;
  height: 34px;
  padding: 0 10px;
  font: inherit;
  font-size: var(--font-size-sm);
  color: var(--input-text);
  background-color: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--radius-sm);
  transition: border-color 0.15s ease;
}

.filter-input:hover:not(:disabled) {
  border-color: var(--input-border-hover);
}

.filter-input::placeholder {
  color: var(--input-placeholder);
}

/* A narrowed filter reads as selected (summary text names it too) */
.filter-input.is-active {
  border-color: var(--accent-primary);
  background-color: var(--accent-subtle);
}

.search-input-wrapper {
  position: relative;
}

.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  pointer-events: none;
}

.search-input {
  padding-left: 32px;
  padding-right: 34px;
}

.search-clear-btn {
  position: absolute;
  right: 3px;
  top: 50%;
  transform: translateY(-50%);
  width: 28px;
  height: 28px;
  padding: 0;
}

.filter-group--check .checkbox-label {
  height: 34px;
  gap: 6px;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  white-space: nowrap;
}

.filters-toggle {
  display: none;
}

.toolbar-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-2xs) var(--space-md);
  min-height: 32px;
  margin-top: 6px;
}

.filter-summary-text {
  min-width: 0;
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.summary-count {
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
}

.summary-chips {
  color: var(--text-secondary);
}

.btn-clear-filters {
  min-height: 28px;
  padding: 0 6px;
  font: inherit;
  font-size: var(--type-meta-size);
  font-weight: var(--font-weight-medium);
  color: var(--accent-text);
  background: none;
  border: 0;
  border-radius: var(--radius-xs);
  cursor: pointer;
}

.btn-clear-filters:hover:not(:disabled) {
  text-decoration: underline;
  text-underline-offset: 2px;
}

.btn-clear-filters:disabled {
  color: var(--text-disabled);
  cursor: default;
}

/* Narrow screens: search + Filters disclosure; the fields stack when opened */
@media (max-width: 767px) {
  .toolbar-controls {
    flex-wrap: wrap;
  }

  .filter-group--search {
    flex: 1 1 0;
  }

  .filter-group--search .filter-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  .filters-toggle {
    display: inline-flex;
    height: 34px;
    min-height: 34px;
    padding: 0 10px;
    font-size: var(--font-size-sm);
  }

  .filters-toggle.is-open {
    background: var(--bg-subtle);
    color: var(--text-primary);
  }

  .filters-toggle-count {
    min-width: 1.25rem;
    padding: 0 4px;
    font-size: var(--font-size-xs);
    font-weight: var(--font-weight-semibold);
    color: var(--text-on-accent);
    background: var(--accent-primary);
    border-radius: var(--radius-xs);
  }

  .filters-toggle-chevron {
    transition: transform 0.15s ease;
  }

  .filters-toggle.is-open .filters-toggle-chevron {
    transform: rotate(180deg);
  }

  .filter-fields {
    display: none;
    flex: 1 1 100%;
    flex-direction: column;
    align-items: stretch;
    padding: var(--space-sm) 0 var(--space-xs);
  }

  .filter-fields.is-open {
    display: flex;
  }

  .filter-fields > .filter-group {
    flex: 0 0 auto;
  }

  .filter-input {
    height: 40px;
    font-size: 1rem; /* avoids iOS zoom on focus */
  }

  .filter-group--check .checkbox-label {
    height: 36px;
  }
}

/* Ledger ------------------------------------------------------------------- */

.transactions-container {
  container: ledger / inline-size;
}

.ledger {
  overflow: hidden;
}

.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.transactions-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: var(--font-size-sm);
  text-align: left;
}

.transactions-table th {
  height: 34px;
  padding: 0 12px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--table-header-text);
  background: var(--table-header);
  border-bottom: 1px solid var(--border-default);
  white-space: nowrap;
}

.date-col { width: 108px; }
.account-col { width: 15%; }
.category-col { width: 248px; }
.amount-col { width: 128px; text-align: right; }
.status-col { width: 132px; }

.transactions-table td {
  padding: 5px 12px;
  vertical-align: middle;
  border-bottom: 1px solid var(--table-border);
}

.tx-row:last-child td {
  border-bottom: 0;
}

.tx-row:hover td,
.tx-row:focus-within td {
  background: var(--table-hover);
}

.date-cell {
  color: var(--text-secondary);
  white-space: nowrap;
}

/* Merchant / description */

.desc-cell {
  min-width: 0;
}

.merchant-row {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
}

.merchant-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.btn-edit-merchant {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  padding: 0;
  color: var(--text-muted);
}

.merchant-edit-form {
  display: flex;
  align-items: center;
  gap: 2px;
}

.merchant-edit-input {
  flex: 1 1 auto;
  min-width: 0;
  height: 28px;
  padding: 0 8px;
  font: inherit;
  font-weight: var(--font-weight-medium);
  color: var(--input-text);
  background: var(--input-bg);
  border: 1px solid var(--accent-primary);
  border-radius: var(--radius-xs);
}

.btn-save-merchant,
.btn-cancel-merchant {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  padding: 0;
}

.btn-save-merchant {
  color: var(--accent-text);
}

.tx-meta {
  display: flex;
  align-items: baseline;
  gap: 0 var(--space-sm);
  min-width: 0;
  overflow: hidden;
  font-size: var(--font-size-xs);
  line-height: 1.4;
  color: var(--text-muted);
}

.account-inline {
  display: none;
  flex-shrink: 1;
  min-width: 0;
  max-width: 50%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
}

.tx-flag {
  /* State flags hold their width; the original description and inline account
     truncate first. Block-level (as a flex item) so a flag wider than the whole
     line ends in an ellipsis rather than a clipped word. */
  display: inline-block;
  flex-shrink: 0;
  max-width: 100%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
}

.tx-flag .app-icon {
  display: inline-block;
  margin-right: 3px;
  vertical-align: -2px;
}

.raw-desc-text {
  /* gives way first: description, then inline account, then state flags */
  flex-shrink: 100;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-cell {
  color: var(--text-secondary);
}

.account-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Category */

.unsplit-cell-content {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.category-select-row {
  display: grid;
  /* fixed Split track keeps selects aligned on rows that cannot be split */
  grid-template-columns: minmax(0, 1fr) 62px;
  align-items: center;
  gap: var(--space-xs);
}

.category-select {
  flex: 1 1 auto;
  min-width: 0;
  height: 30px;
  padding: 0 6px;
  font: inherit;
  font-size: var(--type-meta-size);
  color: var(--text-primary);
  background-color: var(--input-bg);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  cursor: pointer;
  text-overflow: ellipsis;
}

.category-select:hover:not(:disabled) {
  border-color: var(--input-border-hover);
}

.category-select:disabled {
  background-color: var(--input-disabled-bg);
  cursor: progress;
}

/* Missing category = incomplete work, not an error: dashed edge + warning-toned
   label. The word "Uncategorized" carries the state; color only reinforces it. */
.category-select.uncategorized {
  border-style: dashed;
  border-color: var(--border-strong);
  color: var(--status-warning);
  font-weight: var(--font-weight-medium);
}

.category-select.uncategorized:hover:not(:disabled) {
  border-color: var(--status-warning);
  background-color: var(--status-warning-bg);
}

/* Option text stays neutral inside the native menu */
.category-select option,
.category-select optgroup {
  color: var(--text-primary);
  font-weight: var(--font-weight-regular);
}

.btn-split-trigger,
.btn-split-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  font: inherit;
  font-size: var(--type-meta-size);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.btn-split-trigger {
  justify-content: center;
  padding: 0 6px;
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid transparent;
}

.btn-split-trigger:hover {
  color: var(--text-primary);
  background: var(--bg-subtle);
  border-color: var(--border-default);
}

.btn-split-badge {
  width: 100%;
  padding: 0 8px;
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  background: var(--bg-sunken);
  border: 1px solid var(--border-default);
  text-align: left;
}

.btn-split-badge .app-icon {
  color: var(--text-muted);
}

.btn-split-badge:hover {
  border-color: var(--input-border-hover);
  background: var(--bg-subtle);
}

/* ML suggestion: one quiet line above the selector */
.ml-suggestion-box {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
}

.ml-suggestion-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ml-suggestion-text strong {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.ml-suggestion-score {
  color: var(--text-muted);
}

.btn-accept-suggestion {
  flex-shrink: 0;
  min-height: 24px;
  padding: 0 8px;
  font: inherit;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--accent-text);
  background: var(--bg-surface);
  border: 1px solid var(--accent-primary);
  border-radius: var(--radius-xs);
  cursor: pointer;
}

.btn-accept-suggestion:hover:not(:disabled) {
  background: var(--accent-subtle);
}

.btn-accept-suggestion:disabled {
  opacity: 0.5;
  cursor: progress;
}

/* Amount */

.amount-col,
.amount-cell {
  text-align: right;
}

.amount-cell {
  white-space: nowrap;
  font-weight: var(--font-weight-semibold);
}

/* Right-aligned figures only need room on the left; this keeps 7-figure
   amounts inside the cell without widening the column further */
.transactions-table td.amount-cell {
  padding-left: 4px;
}

/* Review toggle: shape + word carry the state, color only reinforces it */

.review-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  min-height: 28px;
  padding: 0 8px 0 6px;
  font: inherit;
  font-size: var(--type-meta-size);
  white-space: nowrap;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.review-toggle-btn:hover:not(:disabled) {
  background: var(--bg-surface);
  border-color: var(--border-default);
}

.review-toggle-btn:disabled {
  opacity: 0.55;
  cursor: progress;
}

.review-toggle-btn.needs-review {
  color: var(--text-primary);
  font-weight: var(--font-weight-medium);
}

.review-toggle-btn.needs-review .review-icon {
  color: var(--border-strong);
}

.review-toggle-btn.is-reviewed {
  color: var(--text-muted);
}

.review-toggle-btn.is-reviewed .review-icon {
  color: var(--status-success);
}

/* Empty + pagination */

.empty-row {
  padding: var(--space-xl) var(--space-md) !important;
  text-align: center;
  color: var(--text-muted);
}

.empty-row p {
  margin: 0 0 var(--space-sm);
}

.empty-row p:last-child {
  margin-bottom: 0;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-sm);
  padding: 8px 12px;
  border-top: 1px solid var(--border-default);
  background: var(--bg-sunken);
}

.page-info {
  font-size: var(--type-meta-size);
  color: var(--text-secondary);
}

.page-buttons {
  display: flex;
  gap: var(--space-xs);
}

/* Medium ledger: Account folds under the merchant; review shows icon only */
@container ledger (max-width: 999px) {
  .date-col { width: 96px; }
  .category-col { width: 220px; }
  /* Same track as desktop and stable through the whole medium range, so every
     figure (up to +$1,234,567.89) keeps the same right edge */
  .amount-col { width: 128px; min-width: 128px; }
  .status-col { width: 64px; padding: 0 8px !important; text-align: center; }

  /* Collapsed to zero width rather than removed, so column counts (and the
     empty row's colspan) stay intact; the name shows under the merchant. */
  .transactions-table .account-col,
  .transactions-table .account-cell {
    width: 0;
    padding: 0;
    overflow: hidden;
    visibility: hidden;
  }

  .account-inline {
    display: block;
  }

  .status-cell {
    text-align: center;
  }

  .review-toggle-btn {
    width: 32px;
    height: 32px;
    padding: 0;
    justify-content: center;
  }

  .review-toggle-btn .status-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  .review-toggle-btn .review-icon {
    width: 18px;
    height: 18px;
  }
}

@container ledger (max-width: 760px) {
  /* Room for the 128px amount track comes from Category and the icon-only
     Review column, not Merchant; the select still shows "Uncategorized" */
  .category-col { width: 188px; }
  .status-col { width: 56px; padding: 0 4px !important; }

  /* Split keeps its icon, tooltip and accessible name; the word is hidden */
  .category-select-row { grid-template-columns: minmax(0, 1fr) 30px; }
  .btn-split-trigger { padding: 0; }
  .split-trigger-text {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }
}

/* Narrow ledger: each row becomes a compact stacked record.
   Explicit ARIA roles in the markup keep table semantics when display changes. */
@container ledger (max-width: 619px) {
  .transactions-table,
  .transactions-table tbody {
    display: block;
  }

  .transactions-table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  .tx-row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas:
      "desc desc amount"
      "date account review"
      "cat cat cat";
    align-items: center;
    column-gap: var(--space-sm);
    padding: 10px var(--space-md) 12px;
    border-bottom: 1px solid var(--table-border);
  }

  .tx-row:last-child {
    border-bottom: 0;
  }

  .transactions-table .tx-row td {
    padding: 0;
    border: 0;
    background: none;
  }

  .tx-row:hover,
  .tx-row:focus-within {
    background: var(--table-hover);
  }

  .date-cell { grid-area: date; font-size: var(--font-size-xs); }
  .desc-cell { grid-area: desc; align-self: start; }
  .transactions-table .account-col {
    visibility: visible;
  }

  .transactions-table .account-cell {
    display: block;
    visibility: visible;
    width: auto;
    overflow: visible;
    grid-area: account;
    min-width: 0;
    font-size: var(--font-size-xs);
  }
  .category-cell { grid-area: cat; padding-top: 6px !important; }
  .amount-cell { grid-area: amount; align-self: start; font-size: var(--type-body-size); }
  .status-cell { grid-area: review; text-align: right; }

  .account-inline {
    display: none;
  }

  .merchant-name {
    font-size: var(--type-body-size);
  }

  .review-toggle-btn {
    width: auto;
    height: 32px;
    padding: 0 8px 0 6px;
    margin-right: -6px;
  }

  .review-toggle-btn .status-label {
    position: static;
    width: auto;
    height: auto;
    overflow: visible;
    clip: auto;
  }

  .category-select,
  .btn-split-trigger,
  .btn-split-badge {
    height: 36px;
  }

  .category-select-row { grid-template-columns: minmax(0, 1fr) 68px; }
  .btn-split-trigger { padding: 0 6px; }
  .split-trigger-text {
    position: static;
    width: auto;
    height: auto;
    overflow: visible;
    clip: auto;
  }

  .category-select {
    font-size: 1rem; /* avoids iOS zoom on focus */
  }

  .btn-edit-merchant {
    width: 32px;
    height: 32px;
  }

  .empty-tr {
    display: block;
  }

  .empty-tr .empty-row {
    display: block;
  }

  .pagination {
    padding: 8px var(--space-md);
  }

  .page-buttons .btn {
    min-height: 36px;
  }
}

/* Split dialog --------------------------------------------------------------- */

.split-dialog-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.split-parent-summary {
  margin: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1.6fr) minmax(0, 1fr) auto;
  gap: var(--space-sm) var(--space-md);
  padding: 10px var(--space-md);
  background: var(--bg-sunken);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
}

.summary-col {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.summary-col--num {
  text-align: right;
}

.summary-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.summary-val {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.summary-val--strong {
  font-weight: var(--font-weight-semibold);
}

@media (max-width: 560px) {
  .split-parent-summary {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .summary-col--wide {
    grid-column: 1 / -1;
    order: -1;
  }
}

.split-error-alert {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  padding: 6px 6px 6px var(--space-md);
  font-size: var(--font-size-sm);
  color: var(--status-error);
  background: var(--status-error-bg);
  border-left: 3px solid var(--status-error);
}

.alert-dismiss {
  flex-shrink: 0;
  color: var(--status-error);
}

.split-allocations-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: var(--space-sm);
}

.split-section-title {
  margin: 0;
  font-size: var(--type-subheading-size);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.split-rule-hint {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.split-lines-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.split-line-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px auto;
  align-items: center;
  gap: var(--space-sm);
}

.split-select,
.split-amount-input {
  height: 36px;
  padding-top: 0;
  padding-bottom: 0;
}

.amount-input-wrapper {
  position: relative;
}

.currency-prefix {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  pointer-events: none;
}

.split-amount-input {
  padding-left: 28px;
  text-align: right;
}

.btn-remove-line {
  color: var(--text-secondary);
}

.split-add-line-row {
  margin-top: var(--space-sm);
}

.btn-add-split-line {
  color: var(--accent-text);
}

@media (max-width: 480px) {
  .split-line-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .line-category-col {
    grid-column: 1 / -1;
  }
}

.split-math-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-md);
  padding: 10px var(--space-md);
  background: var(--bg-sunken);
  border: 1px solid var(--border-subtle);
  border-left-width: 3px;
  border-radius: var(--radius-sm);
}

.split-math-bar.status-balanced { border-left-color: var(--status-success); }
.split-math-bar.status-remaining { border-left-color: var(--status-warning); }
.split-math-bar.status-over { border-left-color: var(--status-error); }

.math-item {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.math-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.math-val {
  font-size: var(--font-size-base);
  color: var(--text-primary);
}

.math-val--strong {
  font-weight: var(--font-weight-semibold);
}

.math-operator {
  font-size: var(--font-size-lg);
  color: var(--text-muted);
}

.math-status-badge {
  margin-left: auto;
  font-size: var(--type-meta-size);
  font-weight: var(--font-weight-semibold);
}

.badge-balanced {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--status-success);
}

.badge-remaining {
  color: var(--status-warning);
}

.badge-over {
  color: var(--status-error);
}

.split-warning-msg {
  padding: 6px var(--space-md);
  font-size: var(--type-meta-size);
  color: var(--text-primary);
  background: var(--status-warning-bg);
  border-left: 3px solid var(--status-warning);
}

.unsplit-collapse-box {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding-top: var(--space-md);
  border-top: 1px solid var(--border-subtle);
}

.unsplit-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.unsplit-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.unsplit-subtitle {
  font-size: var(--type-meta-size);
  color: var(--text-muted);
}

.unsplit-controls {
  display: flex;
  gap: var(--space-sm);
}

.unsplit-category-select {
  flex: 1 1 auto;
  min-width: 0;
  height: 34px;
  padding-top: 0;
  padding-bottom: 0;
}

.split-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
}
</style>

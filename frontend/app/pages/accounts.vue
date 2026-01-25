<template>
  <div class="accounts-page">
    <header class="page-header">
      <h1 class="page-title">Accounts</h1>
      <button class="primary-btn" @click="openLink" :disabled="loadingLink">
        {{ loadingLink ? 'Starting Plaid...' : 'Connect Account' }}
      </button>
    </header>

    <!-- Error Banner -->
    <div v-if="error" class="error-banner">
      {{ error }}
    </div>

    <!-- Loading State -->
    <div v-if="pending" class="loading-state">
      <div class="spinner"></div>
      <p>Loading accounts...</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="!accounts.length" class="empty-state">
      <div class="empty-icon">🏦</div>
      <h2>No accounts connected</h2>
      <p>Connect your bank to start tracking your budget.</p>
    </div>

    <!-- Accounts List -->
    <div v-else class="accounts-grid">
      <!-- Group by Plaid Item (Institution) -->
      <div v-for="(group, itemId) in groupedAccounts" :key="itemId" class="institution-card">
        <div class="institution-header">
          <h3 class="institution-name">Connected Institution</h3>
          <button 
            class="sync-btn" 
            @click="syncItem(itemId)" 
            :disabled="syncingItems[itemId]"
            title="Sync Transactions"
          >
            <span v-if="syncingItems[itemId]" class="spinner-sm"></span>
            <span v-else>↻ Sync</span>
          </button>
        </div>

        <div class="account-list">
          <div v-for="account in group" :key="account.account_id" class="account-row">
            <div class="account-details">
              <div class="account-name">{{ account.name }}</div>
              <div class="account-meta">
                <span class="account-type">{{ account.subtype || account.type }}</span>
                <span v-if="account.mask" class="account-mask">•••• {{ account.mask }}</span>
              </div>
            </div>
            <div class="account-balance">
              <div class="current-balance">{{ formatCurrency(account.current_balance, account.currency) }}</div>
              <div v-if="account.available_balance" class="available-balance">
                Available: {{ formatCurrency(account.available_balance, account.currency) }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

const API_BASE = 'http://localhost:12344'

interface Account {
  account_id: string
  item_id: string
  name: string
  mask: string
  type: string
  subtype: string
  current_balance: number
  available_balance: number | null
  currency: string
  balance_last_updated: string | null
  is_active: boolean
}

// --- State ---
const accounts = ref<Account[]>([])
const pending = ref(true)
const error = ref<string | null>(null)
const loadingLink = ref(false)
const syncingItems = ref<Record<string, boolean>>({})

// --- Data Fetching ---
const fetchAccounts = async () => {
  pending.value = true
  error.value = null
  try {
    const res = await fetch(`${API_BASE}/accounts/`)
    if (!res.ok) throw new Error('Failed to fetch accounts')
    accounts.value = await res.json()
  } catch (err: any) {
    error.value = err.message
  } finally {
    pending.value = false
  }
}

// Group accounts by item_id
const groupedAccounts = computed(() => {
  const groups: Record<string, Account[]> = {}
  accounts.value.forEach(acc => {
    if (!groups[acc.item_id]) {
      groups[acc.item_id] = []
    }
    groups[acc.item_id].push(acc)
  })
  return groups
})

// --- Plaid Integration ---
const loadPlaidScript = () => {
  if ((window as any).Plaid) return Promise.resolve()
  
  return new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://cdn.plaid.com/link/v2/stable/link-initialize.js'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Plaid script'))
    document.head.appendChild(script)
  })
}

const openLink = async () => {
  loadingLink.value = true
  error.value = null
  
  try {
    await loadPlaidScript()

    // 1. Create Link Token
    const tokenRes = await fetch(`${API_BASE}/plaid/create_link_token`, {
      method: 'POST'
    })
    if (!tokenRes.ok) throw new Error('Failed to create link token')
    const { link_token } = await tokenRes.json()

    // 2. Initialize Plaid
    const handler = (window as any).Plaid.create({
      token: link_token,
      onSuccess: async (public_token: string) => {
        // 3. Exchange Token
        try {
          const exchangeRes = await fetch(`${API_BASE}/plaid/exchange_public_token`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ public_token })
          })
          if (!exchangeRes.ok) throw new Error('Failed to connect account')
          
          await fetchAccounts() // Refresh list
        } catch (err: any) {
          error.value = `Connection failed: ${err.message}`
        }
      },
      onExit: (err: any) => {
        if (err) console.error('Plaid Exit:', err)
        loadingLink.value = false
      },
      onLoad: () => {
        loadingLink.value = false
        handler.open()
      }
    })

  } catch (err: any) {
    error.value = err.message
    loadingLink.value = false
  }
}

// --- Actions ---
const syncItem = async (itemId: string) => {
  if (syncingItems.value[itemId]) return
  
  syncingItems.value[itemId] = true
  try {
    const res = await fetch(`${API_BASE}/plaid/sync_transactions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: itemId })
    })
    if (!res.ok) throw new Error('Sync failed')
    
    // Refresh balances
    await fetchAccounts()
  } catch (err: any) {
    error.value = `Sync failed: ${err.message}`
  } finally {
    syncingItems.value[itemId] = false
  }
}

// --- Helpers ---
const formatCurrency = (amount: number | string, currency = 'USD') => {
  const val = Number(amount)
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 2
  }).format(val)
}

onMounted(() => {
  fetchAccounts()
})
</script>

<style scoped>
.accounts-page {
  padding: 24px;
  max-width: 900px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.page-title {
  font-size: 1.8rem;
  font-weight: 700;
  margin: 0;
}

.primary-btn {
  background: var(--accent-color);
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.primary-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.error-banner {
  background: #fee2e2;
  color: #dc2626;
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 24px;
}

.loading-state, .empty-state {
  text-align: center;
  padding: 60px;
  color: var(--text-muted);
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 16px;
}

.spinner {
  border: 3px solid #f3f3f3;
  border-top: 3px solid var(--accent-color);
  border-radius: 50%;
  width: 30px;
  height: 30px;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

.institution-card {
  background: white;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  overflow: hidden;
  margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.institution-header {
  background: #f8fafc;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.institution-name {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sync-btn {
  background: none;
  border: 1px solid var(--border-color);
  background: white;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--text-color);
  display: flex;
  align-items: center;
  gap: 6px;
}

.sync-btn:hover {
  background: #f1f5f9;
}

.account-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #f1f5f9;
}

.account-row:last-child {
  border-bottom: none;
}

.account-details {
  display: flex;
  flex-direction: column;
}

.account-name {
  font-weight: 600;
  font-size: 1.05rem;
}

.account-meta {
  font-size: 0.85rem;
  color: var(--text-muted);
  display: flex;
  gap: 8px;
}

.account-type {
  text-transform: capitalize;
}

.account-balance {
  text-align: right;
}

.current-balance {
  font-weight: 700;
  font-size: 1.05rem;
}

.available-balance {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.spinner-sm {
  border: 2px solid #e2e8f0;
  border-top: 2px solid var(--text-muted);
  border-radius: 50%;
  width: 14px;
  height: 14px;
  animation: spin 1s linear infinite;
  display: inline-block;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
<template>
  <div
    class="app-shell"
    :class="{ 'is-collapsed': navCollapsed, 'is-drawer-open': drawerOpen }"
  >
    <a href="#main-content" class="skip-link">Skip to content</a>

    <!-- Mobile application bar (<= 767px) -->
    <header class="mobile-bar" :inert="drawerOpen || undefined">
      <button
        ref="menuButtonRef"
        type="button"
        class="shell-icon-btn"
        aria-label="Open navigation"
        aria-controls="app-nav"
        :aria-expanded="drawerOpen ? 'true' : 'false'"
        @click="openDrawer"
      >
        <AppIcon name="menu" :size="20" />
      </button>
      <span class="brand">
        <AppIcon name="mark" :size="20" class="brand-mark" />
        <span class="brand-text">BudgetApp</span>
      </span>
    </header>

    <div
      v-if="drawerOpen"
      class="nav-scrim"
      aria-hidden="true"
      @click="closeDrawer()"
    ></div>

    <!-- Navigation: left rail on desktop, drawer on mobile -->
    <aside
      id="app-nav"
      ref="navRef"
      class="sidebar"
      :role="drawerOpen ? 'dialog' : undefined"
      :aria-modal="drawerOpen ? 'true' : undefined"
      :aria-label="drawerOpen ? 'Navigation' : undefined"
      @keydown="onNavKeydown"
    >
      <div class="sidebar-header">
        <span class="brand">
          <AppIcon name="mark" :size="20" class="brand-mark" />
          <span class="brand-text">BudgetApp</span>
        </span>
        <button
          type="button"
          class="shell-icon-btn drawer-close-btn"
          aria-label="Close navigation"
          @click="closeDrawer()"
        >
          <AppIcon name="close" :size="20" />
        </button>
      </div>

      <nav class="nav" aria-label="Primary">
        <ul class="nav-list" role="list">
          <li v-for="item in primaryItems" :key="item.label">
            <NuxtLink
              :to="item.to"
              class="nav-link"
              :title="labelsHidden ? item.label : undefined"
            >
              <AppIcon :name="item.icon" class="nav-icon" />
              <span class="nav-label">{{ item.label }}</span>
            </NuxtLink>
          </li>
        </ul>

        <ul class="nav-list nav-list-secondary" role="list">
          <li>
            <NuxtLink
              to="/settings"
              class="nav-link"
              :title="labelsHidden ? 'Settings' : undefined"
            >
              <AppIcon name="settings" class="nav-icon" />
              <span class="nav-label">Settings</span>
            </NuxtLink>
          </li>
        </ul>
      </nav>

      <div class="sidebar-footer">
        <button
          type="button"
          class="collapse-btn"
          aria-controls="app-nav"
          :aria-expanded="navCollapsed ? 'false' : 'true'"
          :title="navCollapsed ? 'Expand navigation' : 'Collapse navigation'"
          @click="navCollapsed = !navCollapsed"
        >
          <AppIcon name="collapse" class="collapse-icon" />
          <span class="nav-label">{{ navCollapsed ? 'Expand navigation' : 'Collapse navigation' }}</span>
        </button>
      </div>
    </aside>

    <main
      id="main-content"
      class="content"
      tabindex="-1"
      :inert="drawerOpen || undefined"
    >
      <NuxtPage />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useBudgetMonth } from '~/composables/useBudgetMonth'
import type { RouteLocationRaw } from 'vue-router'
import type { AppIconName } from '~/components/AppIcon.vue'

interface NavItem {
  label: string
  icon: AppIconName
  to: RouteLocationRaw
}

const { selectedMonth } = useBudgetMonth()
const route = useRoute()

// Month-scoped pages carry the selected month, as before.
const primaryItems = computed<NavItem[]>(() => [
  { label: 'Dashboard', icon: 'dashboard', to: { path: '/dashboard', query: { month: selectedMonth.value } } },
  { label: 'Budget', icon: 'budget', to: { path: '/categories', query: { month: selectedMonth.value } } },
  { label: 'Transactions', icon: 'transactions', to: { path: '/transactions', query: { month: selectedMonth.value } } },
  { label: 'Accounts', icon: 'accounts', to: '/accounts' },
  { label: 'Credit Cards', icon: 'card', to: { path: '/credit-cards', query: { month: selectedMonth.value } } },
  { label: 'Import', icon: 'import', to: '/upload' },
])

// --- Desktop collapse (persisted in a cookie so SSR renders the right width) ---
const navCollapsedCookie = useCookie<boolean>('nav_collapsed', {
  default: () => false,
  maxAge: 60 * 60 * 24 * 365,
  sameSite: 'lax',
})
const navCollapsed = computed({
  get: () => Boolean(navCollapsedCookie.value),
  set: (value: boolean) => {
    navCollapsedCookie.value = value
  },
})

// --- Viewport tracking: compact widths always show the icon rail ---
const MOBILE_QUERY = '(max-width: 767px)'
const COMPACT_QUERY = '(min-width: 768px) and (max-width: 1023px)'
const isMobile = ref(false)
const isCompact = ref(false)
let mobileMql: MediaQueryList | null = null
let compactMql: MediaQueryList | null = null

// Labels are visually hidden on the icon rail; links then expose a tooltip.
const labelsHidden = computed(() => !isMobile.value && (isCompact.value || navCollapsed.value))

// --- Mobile drawer ---
const drawerOpen = ref(false)
const navRef = ref<HTMLElement | null>(null)
const menuButtonRef = ref<HTMLButtonElement | null>(null)

const openDrawer = async () => {
  drawerOpen.value = true
  await nextTick()
  navRef.value?.querySelector<HTMLElement>('.nav-link')?.focus()
}

const closeDrawer = (restoreFocus = true) => {
  if (!drawerOpen.value) return
  drawerOpen.value = false
  if (restoreFocus) {
    nextTick(() => menuButtonRef.value?.focus())
  }
}

// Escape is handled at document level while the drawer is open, so it works
// even if focus is not inside the drawer.
const onDocumentKeydown = (event: KeyboardEvent) => {
  if (event.key !== 'Escape' || !drawerOpen.value) return
  event.preventDefault()
  closeDrawer()
}

const onNavKeydown = (event: KeyboardEvent) => {
  if (!drawerOpen.value || !navRef.value) return
  if (event.key !== 'Tab') return
  const focusable = Array.from(
    navRef.value.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')
  ).filter((el) => el.getClientRects().length > 0)
  if (focusable.length === 0) return

  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

// Navigating closes the drawer; focus moves with the new page, not back to the menu button.
watch(
  () => route.fullPath,
  () => closeDrawer(false)
)

// Lock page scroll and listen for Escape only while the drawer is open.
watch(drawerOpen, (open) => {
  if (typeof document === 'undefined') return
  document.documentElement.style.overflow = open ? 'hidden' : ''
  if (open) {
    document.addEventListener('keydown', onDocumentKeydown)
  } else {
    document.removeEventListener('keydown', onDocumentKeydown)
  }
})

const syncViewport = () => {
  isMobile.value = Boolean(mobileMql?.matches)
  isCompact.value = Boolean(compactMql?.matches)
  if (!isMobile.value) closeDrawer(false)
}

onMounted(() => {
  mobileMql = window.matchMedia(MOBILE_QUERY)
  compactMql = window.matchMedia(COMPACT_QUERY)
  mobileMql.addEventListener('change', syncViewport)
  compactMql.addEventListener('change', syncViewport)
  syncViewport()
})

onBeforeUnmount(() => {
  mobileMql?.removeEventListener('change', syncViewport)
  compactMql?.removeEventListener('change', syncViewport)
  if (typeof document !== 'undefined') {
    document.removeEventListener('keydown', onDocumentKeydown)
    document.documentElement.style.overflow = ''
  }
})
</script>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
  min-height: 100dvh;
}

/* -------------------------------------------------------------------------- */
/* Skip link                                                                  */
/* -------------------------------------------------------------------------- */

.skip-link {
  position: absolute;
  top: var(--space-sm);
  left: var(--space-sm);
  z-index: 1000;
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-elevated);
  color: var(--accent-text);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-medium);
  text-decoration: none;
  transform: translateY(-200%);
}

.skip-link:focus {
  transform: none;
}

/* -------------------------------------------------------------------------- */
/* Rail                                                                       */
/* -------------------------------------------------------------------------- */

.sidebar {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: var(--rail-width);
  height: 100vh;
  height: 100dvh;
  background: var(--nav-bg);
  border-right: 1px solid var(--nav-border);
  transition: width 0.2s ease;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  height: 56px;
  padding: 0 var(--space-md);
  flex-shrink: 0;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  color: var(--text-primary);
  font-weight: var(--font-weight-semibold);
  font-size: 0.9375rem;
  letter-spacing: -0.01em;
  white-space: nowrap;
}

.brand-mark {
  color: var(--accent-primary);
}

.nav {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: var(--space-xs) var(--space-sm) var(--space-sm);
  overflow-y: auto;
  overflow-x: hidden;
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.nav-list-secondary {
  margin-top: auto;
  padding-top: var(--space-sm);
}

.nav-link {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 38px;
  padding: 0 12px;
  border-radius: var(--radius-sm);
  color: var(--nav-text);
  font-size: 0.875rem;
  font-weight: var(--font-weight-medium);
  text-decoration: none;
  white-space: nowrap;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.nav-link:hover {
  background: var(--nav-item-hover);
  color: var(--nav-text-hover);
}

.nav-link:focus-visible {
  outline-offset: -2px;
}

/* Active route: tinted fill + leading indicator bar + weight, not color alone */
.nav-link.router-link-active {
  background: var(--nav-item-active);
  color: var(--nav-text-active);
  font-weight: var(--font-weight-semibold);
}

.nav-link.router-link-active::before {
  content: '';
  position: absolute;
  left: -8px;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 2px 2px 0;
  background: var(--nav-indicator);
}

.sidebar-footer {
  flex-shrink: 0;
  padding: var(--space-sm);
  border-top: 1px solid var(--nav-border);
}

.collapse-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 36px;
  padding: 0 12px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: var(--type-meta-size);
  cursor: pointer;
  white-space: nowrap;
}

.collapse-btn:hover {
  background: var(--nav-item-hover);
  color: var(--nav-text-hover);
}

.collapse-btn:focus-visible {
  outline-offset: -2px;
}

.collapse-icon {
  transition: transform 0.2s ease;
}

.shell-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}

.shell-icon-btn:hover {
  background: var(--nav-item-hover);
  color: var(--text-primary);
}

.drawer-close-btn,
.mobile-bar,
.nav-scrim {
  display: none;
}

/* -------------------------------------------------------------------------- */
/* Content                                                                    */
/* -------------------------------------------------------------------------- */

.content {
  flex: 1;
  min-width: 0;
}

.content:focus {
  outline: none;
}

/* -------------------------------------------------------------------------- */
/* Icon rail: user-collapsed (wide) or forced (compact 768-1023px)            */
/* Labels stay in the DOM, visually hidden, so links keep accessible names.   */
/* -------------------------------------------------------------------------- */

@media (min-width: 1024px) {
  .is-collapsed .sidebar {
    width: var(--rail-collapsed-width);
  }

  .is-collapsed .collapse-icon {
    transform: rotate(180deg);
  }

  .is-collapsed .sidebar-header {
    justify-content: center;
    padding: 0;
  }

  .is-collapsed .brand-text,
  .is-collapsed .nav-label {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  .is-collapsed .nav-link,
  .is-collapsed .collapse-btn {
    justify-content: center;
    padding: 0;
  }
}

@media (min-width: 768px) and (max-width: 1023px) {
  .sidebar {
    width: var(--rail-collapsed-width);
  }

  .sidebar-header {
    justify-content: center;
    padding: 0;
  }

  .brand-text,
  .nav-label {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  .nav-link {
    justify-content: center;
    padding: 0;
  }

  /* Collapse preference only applies on wide screens */
  .sidebar-footer {
    display: none;
  }
}

/* -------------------------------------------------------------------------- */
/* Mobile: top bar + navigation drawer                                        */
/* -------------------------------------------------------------------------- */

@media (max-width: 767px) {
  .app-shell {
    flex-direction: column;
  }

  .mobile-bar {
    position: sticky;
    top: 0;
    z-index: 90;
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    height: var(--mobile-bar-height);
    padding: 0 var(--space-sm);
    background: var(--nav-bg);
    border-bottom: 1px solid var(--nav-border);
  }

  .nav-scrim {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 190;
    background: var(--overlay-scrim);
  }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 200;
    width: min(300px, 86vw);
    height: auto;
    border-right: none;
    background: var(--bg-elevated);
    box-shadow: var(--shadow-modal);
    transform: translateX(-100%);
    visibility: hidden;
    transition: transform 0.2s ease, visibility 0s linear 0.2s;
  }

  .is-drawer-open .sidebar {
    transform: none;
    visibility: visible;
    transition: transform 0.2s ease, visibility 0s;
  }

  .drawer-close-btn {
    display: inline-flex;
  }

  .sidebar-header {
    padding: 0 var(--space-sm) 0 var(--space-md);
  }

  .nav-link {
    min-height: 44px;
    font-size: 0.9375rem;
  }

  .sidebar-footer {
    display: none;
  }
}

/* -------------------------------------------------------------------------- */
/* Reduced motion: no drawer/rail transition. A transitioned `visibility`     */
/* would keep the drawer hidden at the moment focus moves into it.            */
/* -------------------------------------------------------------------------- */

@media (prefers-reduced-motion: reduce) {
  .sidebar,
  .is-drawer-open .sidebar {
    transition: none !important;
  }
}
</style>

<template>
  <div class="layout">
    <aside :class="['sidebar', { 'collapsed': isCollapsed }]">
      <div class="sidebar-header">
        <div v-if="!isCollapsed" class="brand">
          <span class="logo-icon">💰</span>
          <span class="logo-text">BudgetApp</span>
        </div>
        <button class="toggle-btn" @click="isCollapsed = !isCollapsed" :title="isCollapsed ? 'Expand' : 'Collapse'">
          <div class="toggle-icon" :class="{ 'rotated': isCollapsed }">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="15 18 9 12 15 6"></polyline>
            </svg>
          </div>
        </button>
      </div>

      <nav class="nav">
        <NuxtLink to="/dashboard" class="nav-item">
          <span class="icon" title="Dashboard">📊</span>
          <span v-if="!isCollapsed" class="label">Dashboard</span>
        </NuxtLink>

        <div class="nav-group">
          <NuxtLink to="/budget" class="nav-item">
            <span class="icon" title="Budget">💰</span>
            <span v-if="!isCollapsed" class="label">Budget</span>
          </NuxtLink>
          <NuxtLink v-if="!isCollapsed" to="/budget/planning" class="nav-item sub-item">
            <span class="icon" title="Planning">📝</span>
            <span class="label">Planning</span>
          </NuxtLink>
        </div>

        <NuxtLink to="/transactions" class="nav-item">
          <span class="icon" title="Transactions">💸</span>
          <span v-if="!isCollapsed" class="label">Transactions</span>
        </NuxtLink>

        <NuxtLink to="/categories" class="nav-item">
          <span class="icon" title="Categories">🏷️</span>
          <span v-if="!isCollapsed" class="label">Categories</span>
        </NuxtLink>

        <NuxtLink to="/accounts" class="nav-item">
          <span class="icon" title="Accounts">🏦</span>
          <span v-if="!isCollapsed" class="label">Accounts</span>
        </NuxtLink>

        <div class="spacer"></div>

        <NuxtLink to="/settings" class="nav-item">
          <span class="icon" title="Settings">⚙️</span>
          <span v-if="!isCollapsed" class="label">Settings</span>
        </NuxtLink>
      </nav>
    </aside>

    <main class="content">
      <NuxtPage />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const isCollapsed = ref(false)
</script>

<style>
:root {
  --sidebar-width: 260px;
  --sidebar-collapsed-width: 68px;
  --bg-color: #f8fafc;
  --sidebar-bg: #ffffff;
  --text-color: #1e293b;
  --text-muted: #64748b;
  --accent-color: #2563eb;
  --border-color: #e2e8f0;
  --nav-hover-bg: #f1f5f9;
  --nav-active-bg: #eff6ff;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  color: var(--text-color);
  background-color: var(--bg-color);
}

.layout {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: var(--sidebar-width);
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: sticky;
  top: 0;
  height: 100vh;
  z-index: 100;
  flex-shrink: 0;
}

.sidebar.collapsed {
  width: var(--sidebar-collapsed-width);
}

.sidebar-header {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid var(--border-color);
  overflow: hidden;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 700;
  font-size: 1.1rem;
  white-space: nowrap;
}

.toggle-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 8px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.toggle-btn:hover {
  background: var(--nav-hover-bg);
  color: var(--text-color);
}

.toggle-icon {
  transition: transform 0.3s;
  display: flex;
}

.toggle-icon.rotated {
  transform: rotate(180deg);
}

.nav {
  padding: 16px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  text-decoration: none;
  color: var(--text-muted);
  border-radius: 8px;
  transition: all 0.2s;
  white-space: nowrap;
}

.nav-item:hover {
  background: var(--nav-hover-bg);
  color: var(--text-color);
}

.router-link-active {
  background: var(--nav-active-bg);
  color: var(--accent-color);
  font-weight: 500;
}

.icon {
  font-size: 1.2rem;
  width: 24px;
  display: flex;
  justify-content: center;
  flex-shrink: 0;
}

.label {
  font-size: 0.95rem;
}

.sub-item {
  margin-left: 8px;
  padding-left: 36px;
  font-size: 0.9rem;
}

.spacer {
  flex: 1;
}

.content {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}

/* Custom Scrollbar */
.nav::-webkit-scrollbar {
  width: 4px;
}
.nav::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 2px;
}
.sidebar:hover .nav::-webkit-scrollbar-thumb {
  background: var(--border-color);
}
</style>
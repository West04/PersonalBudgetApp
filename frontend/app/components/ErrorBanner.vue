<template>
  <div v-if="error" class="error-banner" role="alert" aria-live="assertive">
    <div class="error-body">
      <span class="error-icon" aria-hidden="true">⚠️</span>
      <span class="error-text">{{ error }}</span>
    </div>
    <button
      v-if="dismissible"
      type="button"
      class="dismiss-btn"
      @click="$emit('dismiss')"
      aria-label="Dismiss error notification"
      title="Dismiss"
    >
      ✕
    </button>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    error?: string | null
    dismissible?: boolean
  }>(),
  {
    error: null,
    dismissible: true,
  }
)

defineEmits<{
  (e: 'dismiss'): void
}>()
</script>

<style scoped>
.error-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-md);
  padding: 12px 16px;
  background-color: var(--color-danger-bg);
  border: 1px solid var(--color-danger-border);
  color: var(--color-danger);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-lg);
  font-size: var(--font-size-base);
}

.error-body {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex: 1;
}

.error-icon {
  font-size: 1.1rem;
  line-height: 1;
  flex-shrink: 0;
}

.error-text {
  font-weight: var(--font-weight-medium);
  line-height: 1.4;
}

.dismiss-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  color: inherit;
  font-size: 0.95rem;
  padding: var(--space-xs);
  border-radius: var(--radius-xs);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  opacity: 0.8;
  transition: opacity 0.15s ease, background-color 0.15s ease;
  flex-shrink: 0;
}

.dismiss-btn:hover {
  opacity: 1;
  background-color: rgba(220, 38, 38, 0.1);
}

.dismiss-btn:focus-visible {
  outline: 2px solid var(--color-danger);
  outline-offset: 1px;
}
</style>

<template>
  <div class="loading-state" role="status" aria-live="polite">
    <div class="spinner" aria-hidden="true"></div>
    <p class="loading-text">{{ message }}</p>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    message?: string
  }>(),
  {
    message: 'Loading...',
  }
)
</script>

<style scoped>
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-2xl) var(--space-lg);
  color: var(--color-text-muted);
  min-height: 200px;
}

.spinner {
  border: 3px solid var(--color-border);
  border-top: 3px solid var(--color-primary);
  border-radius: var(--radius-full);
  width: 32px;
  height: 32px;
  animation: spin 0.8s linear infinite;
  margin-bottom: var(--space-md);
}

.loading-text {
  margin: 0;
  font-size: var(--font-size-base);
  color: var(--color-text-muted);
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>

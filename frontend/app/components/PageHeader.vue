<template>
  <header class="page-header">
    <div class="header-titles">
      <h1 class="page-title">{{ title }}</h1>
      <p v-if="subtitle" class="page-subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.controls || $slots.actions || $slots.default" class="header-actions">
      <div v-if="$slots.controls" class="header-controls">
        <slot name="controls" />
      </div>
      <div v-if="$slots.actions || $slots.default" class="header-buttons">
        <slot name="actions"><slot /></slot>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
}>()
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.header-titles {
  display: flex;
  flex-direction: column;
  gap: var(--space-2xs);
}

.page-title {
  margin: 0;
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text);
  line-height: 1.2;
}

.page-subtitle {
  margin: 0;
  font-size: var(--font-size-base);
  color: var(--color-text-muted);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.header-controls,
.header-buttons {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
</style>

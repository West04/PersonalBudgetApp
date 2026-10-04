<template>
  <div class="empty-state">
    <div v-if="$slots.visual" class="empty-visual" aria-hidden="true">
      <slot name="visual" />
    </div>
    <h2 class="empty-title">{{ title }}</h2>
    <p v-if="description" class="empty-description">{{ description }}</p>
    <div v-if="$slots.actions || $slots.default" class="empty-actions">
      <slot name="actions"><slot /></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--space-2xl) var(--space-lg);
  color: var(--color-text-muted);
}

.empty-visual {
  font-size: 2.5rem;
  line-height: 1;
  margin-bottom: var(--space-md);
  color: var(--color-text-light);
}

.empty-title {
  margin: 0 0 var(--space-xs) 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
}

.empty-description {
  margin: 0 0 var(--space-lg) 0;
  font-size: var(--font-size-base);
  color: var(--color-text-muted);
  max-width: 440px;
}

.empty-actions {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex-wrap: wrap;
  justify-content: center;
}
</style>

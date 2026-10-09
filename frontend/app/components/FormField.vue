<template>
  <div class="form-field" :class="{ 'has-error': Boolean(error) }">
    <label v-if="label" :for="fieldId" class="field-label">
      <span class="label-text">{{ label }}</span>
      <span v-if="required" class="required-marker" aria-hidden="true">*</span>
    </label>

    <div class="field-control">
      <slot :id="fieldId" />
    </div>

    <p v-if="hint && !error" class="field-hint">{{ hint }}</p>
    <p v-if="error" class="field-error" role="alert">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue'

const props = withDefaults(
  defineProps<{
    label?: string
    required?: boolean
    hint?: string
    error?: string
    id?: string
  }>(),
  {
    required: false,
  }
)

const autoId = useId()
const fieldId = computed(() => props.id || autoId)
</script>

<style scoped>
.form-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin-bottom: var(--space-md);
}

.field-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2xs);
  font-size: var(--type-label-size);
  font-weight: var(--type-label-weight);
  color: var(--text-secondary);
  user-select: none;
}

.required-marker {
  color: var(--color-danger);
  font-weight: var(--font-weight-bold);
}

.field-control {
  width: 100%;
}

.field-hint {
  margin: var(--space-2xs) 0 0 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-light);
  line-height: 1.3;
}

.field-error {
  margin: var(--space-2xs) 0 0 0;
  font-size: var(--font-size-xs);
  color: var(--color-danger);
  font-weight: var(--font-weight-medium);
  line-height: 1.3;
}

.form-field.has-error :deep(.form-input),
.form-field.has-error :deep(.form-select) {
  border-color: var(--color-danger);
}
</style>

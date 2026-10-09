<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="dialog-backdrop"
      @click="handleBackdropClick"
    >
      <div
        ref="dialogRef"
        class="dialog-panel"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        :style="{ maxWidth }"
        tabindex="-1"
        @click.stop
      >
        <div class="dialog-header">
          <h2 :id="titleId" class="dialog-title">{{ title }}</h2>
          <button
            type="button"
            class="dialog-close-btn"
            @click="handleClose"
            aria-label="Close dialog"
            title="Close dialog"
          >
            ✕
          </button>
        </div>

        <div class="dialog-body">
          <slot />
        </div>

        <div v-if="$slots.footer" class="dialog-footer">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    maxWidth?: string
    closeOnBackdrop?: boolean
  }>(),
  {
    maxWidth: '520px',
    closeOnBackdrop: true,
  }
)

const emit = defineEmits<{
  (e: 'close'): void
}>()

const titleId = `dialog-title-${Math.random().toString(36).substring(2, 9)}`
const dialogRef = ref<HTMLElement | null>(null)
let previouslyFocusedElement: HTMLElement | null = null

const handleClose = () => {
  emit('close')
}

const handleBackdropClick = (event: MouseEvent) => {
  if (props.closeOnBackdrop && event.target === event.currentTarget) {
    handleClose()
  }
}

const handleTabTrap = (event: KeyboardEvent) => {
  if (!dialogRef.value) return

  const focusable = dialogRef.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"]):not([disabled])'
  )
  const focusableList = Array.from(focusable).filter(
    (el) => el.offsetParent !== null || el.getClientRects().length > 0
  )

  if (focusableList.length === 0) {
    event.preventDefault()
    dialogRef.value.focus()
    return
  }

  const first = focusableList[0]
  const last = focusableList[focusableList.length - 1]

  if (event.shiftKey) {
    if (document.activeElement === first || !dialogRef.value.contains(document.activeElement)) {
      event.preventDefault()
      last.focus()
    }
  } else {
    if (document.activeElement === last || !dialogRef.value.contains(document.activeElement)) {
      event.preventDefault()
      first.focus()
    }
  }
}

const onGlobalKeydown = (event: KeyboardEvent) => {
  if (!props.open) return
  if (event.key === 'Escape') {
    handleClose()
  } else if (event.key === 'Tab') {
    handleTabTrap(event)
  }
}

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      if (typeof document !== 'undefined') {
        previouslyFocusedElement = document.activeElement as HTMLElement | null
        document.body.style.overflow = 'hidden'
      }
      await nextTick()
      if (dialogRef.value) {
        // Focus first input or the dialog panel itself
        const focusable = dialogRef.value.querySelector<HTMLElement>(
          'input, select, textarea, button:not(.dialog-close-btn), [tabindex]:not([tabindex="-1"])'
        )
        if (focusable) {
          focusable.focus()
        } else {
          dialogRef.value.focus()
        }
      }
    } else {
      if (typeof document !== 'undefined') {
        document.body.style.overflow = ''
      }
      if (previouslyFocusedElement && typeof previouslyFocusedElement.focus === 'function') {
        previouslyFocusedElement.focus()
      }
      previouslyFocusedElement = null
    }
  },
  { immediate: true }
)

onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', onGlobalKeydown)
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', onGlobalKeydown)
    document.body.style.overflow = ''
  }
})
</script>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  background-color: var(--overlay-scrim);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 500;
  padding: var(--space-md);
  box-sizing: border-box;
}

.dialog-panel {
  background-color: var(--bg-elevated);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-modal);
  width: 100%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  outline: none;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--color-border);
}

.dialog-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--color-text);
}

.dialog-close-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  padding: var(--space-xs);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: 1rem;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}

.dialog-close-btn:hover {
  background-color: var(--color-surface-hover);
  color: var(--color-text);
}

.dialog-close-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 1px;
}

.dialog-body {
  padding: var(--space-lg);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  padding: var(--space-md) var(--space-lg);
  border-top: 1px solid var(--color-border);
  background-color: var(--color-background);
}
</style>

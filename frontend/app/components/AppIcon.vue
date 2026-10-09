<template>
  <svg
    class="app-icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
    v-html="ICONS[name]"
  />
</template>

<script setup lang="ts">
/**
 * Decorative stroke icons for the application shell. Always aria-hidden:
 * the surrounding control must carry its own visible or accessible text.
 * Markup is static and local (no user content reaches v-html).
 */
const ICONS = {
  mark: '<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M8 9h8"/><path d="M8 12.5h8"/><path d="M8 16h5"/>',
  dashboard: '<rect x="3.5" y="3.5" width="7" height="9" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="5" rx="1.5"/><rect x="13.5" y="11.5" width="7" height="9" rx="1.5"/><rect x="3.5" y="15.5" width="7" height="5" rx="1.5"/>',
  budget: '<path d="M20.5 13A8.5 8.5 0 1 1 11 3.5V13z"/><path d="M14.5 3.8a8.5 8.5 0 0 1 5.7 5.7h-5.7z"/>',
  transactions: '<path d="M7 3.5 3.5 7 7 10.5"/><path d="M3.5 7h13"/><path d="m17 13.5 3.5 3.5-3.5 3.5"/><path d="M20.5 17h-13"/>',
  accounts: '<path d="M3.5 20.5h17"/><path d="M3.5 9.5h17L12 3.5z"/><path d="M6 9.5v11"/><path d="M10 9.5v11"/><path d="M14 9.5v11"/><path d="M18 9.5v11"/>',
  card: '<rect x="2.5" y="5" width="19" height="14" rx="2"/><path d="M2.5 9.5h19"/><path d="M6 15h4"/>',
  import: '<path d="M12 3.5v11"/><path d="m7.5 10 4.5 4.5 4.5-4.5"/><path d="M4 15.5v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  settings: '<path d="M4 6h10"/><path d="M18 6h2"/><circle cx="16" cy="6" r="2"/><path d="M4 12h2"/><path d="M10 12h10"/><circle cx="8" cy="12" r="2"/><path d="M4 18h12"/><circle cx="18" cy="18" r="2"/>',
  menu: '<path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/>',
  close: '<path d="M6 6l12 12"/><path d="M18 6 6 18"/>',
  collapse: '<path d="m11 17-5-5 5-5"/><path d="m18 17-5-5 5-5"/>',
} as const

export type AppIconName = keyof typeof ICONS

withDefaults(
  defineProps<{
    name: AppIconName
    size?: number | string
  }>(),
  {
    size: 18,
  }
)
</script>

<style scoped>
.app-icon {
  flex-shrink: 0;
  display: block;
}
</style>

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
 * Decorative stroke icons for the shell and page controls. Always aria-hidden:
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
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.4-4.4"/>',
  filter: '<path d="M4 6h16"/><path d="M7 12h10"/><path d="M10 18h4"/>',
  edit: '<path d="M14.5 5.5l4 4"/><path d="M4 20l1-4.5L15.8 4.7a1.4 1.4 0 0 1 2 0l1.5 1.5a1.4 1.4 0 0 1 0 2L8.5 19z"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  'check-circle': '<circle cx="12" cy="12" r="8.5"/><path d="m8.5 12.2 2.4 2.4 4.6-4.8"/>',
  circle: '<circle cx="12" cy="12" r="8.5"/>',
  split: '<path d="M4 12h6"/><path d="M10 12c3 0 4-5.5 8-5.5"/><path d="M10 12c3 0 4 5.5 8 5.5"/><path d="m16 4.5 2 2-2 2"/><path d="m16 15.5 2 2-2 2"/>',
  repeat: '<path d="M17 3.5 20 6.5 17 9.5"/><path d="M4 11.5v-1a4 4 0 0 1 4-4h12"/><path d="M7 20.5 4 17.5 7 14.5"/><path d="M20 12.5v1a4 4 0 0 1-4 4H4"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  arrow: '<path d="M4 12h15"/><path d="m14 7 5 5-5 5"/>',
  chevron: '<path d="m6.5 9.5 5.5 5.5 5.5-5.5"/>',
  plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
  trash: '<path d="M4 7h16"/><path d="M9.5 7V5a1.5 1.5 0 0 1 1.5-1.5h2A1.5 1.5 0 0 1 14.5 5v2"/><path d="M6.5 7l.8 11.6a2 2 0 0 0 2 1.9h5.4a2 2 0 0 0 2-1.9L17.5 7"/>',
  file: '<path d="M14 3.5H7a1.5 1.5 0 0 0-1.5 1.5v14A1.5 1.5 0 0 0 7 20.5h10a1.5 1.5 0 0 0 1.5-1.5V8z"/><path d="M14 3.5V8h4.5"/><path d="M9 12.5h6"/><path d="M9 16h6"/>',
  alert: '<path d="M10.6 4.3 3.2 17.5a1.6 1.6 0 0 0 1.4 2.4h14.8a1.6 1.6 0 0 0 1.4-2.4L13.4 4.3a1.6 1.6 0 0 0-2.8 0z"/><path d="M12 9.5v4"/><path d="M12 16.8v.2"/>',
  grip: '<circle cx="9" cy="6.5" r="1.1"/><circle cx="15" cy="6.5" r="1.1"/><circle cx="9" cy="12" r="1.1"/><circle cx="15" cy="12" r="1.1"/><circle cx="9" cy="17.5" r="1.1"/><circle cx="15" cy="17.5" r="1.1"/>',
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

// Theme preference contract. Pure: no Nuxt, no browser APIs.
//
// The preference is rendered as <html data-theme="..."> and resolved entirely
// in CSS (assets/css/themes.css). `system` follows prefers-color-scheme and
// only ever maps to Light or Dark.

export const THEME_PREFERENCES = ['system', 'light', 'dark', 'pink', 'tech'] as const

export type ThemePreference = (typeof THEME_PREFERENCES)[number]

export const DEFAULT_THEME_PREFERENCE: ThemePreference = 'system'

export const THEME_COOKIE = 'theme'

export const THEME_OPTIONS: ReadonlyArray<{ value: ThemePreference; label: string; description: string }> = [
  { value: 'system', label: 'System', description: "Match your device's light or dark setting" },
  { value: 'light', label: 'Light', description: 'Bright neutral surfaces' },
  { value: 'dark', label: 'Dark', description: 'Dark surfaces for low light' },
  { value: 'pink', label: 'Pink', description: 'Light surfaces with a rose accent' },
  { value: 'tech', label: 'Tech', description: 'Dark slate surfaces with a cyan accent' },
]

// Anything that is not one of the supported values (missing cookie, old or
// hand-edited value, wrong type) falls back to the default.
export function normalizeThemePreference(value: unknown): ThemePreference {
  return typeof value === 'string' && (THEME_PREFERENCES as readonly string[]).includes(value)
    ? (value as ThemePreference)
    : DEFAULT_THEME_PREFERENCE
}

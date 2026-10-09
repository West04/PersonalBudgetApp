import {
  THEME_COOKIE,
  THEME_OPTIONS,
  normalizeThemePreference,
  type ThemePreference,
} from '~/utils/theme'

/**
 * Theme preference, persisted in a cookie so the server renders the right
 * data-theme on <html> and the first paint already uses it (same convention as
 * the nav_collapsed cookie). Shared state keeps every caller in sync and is
 * serialized into the SSR payload, so hydration sees the server's value.
 */
export function useTheme() {
  const cookie = useCookie<string | null>(THEME_COOKIE, {
    maxAge: 60 * 60 * 24 * 365,
    sameSite: 'lax',
    path: '/',
  })
  const preference = useState<ThemePreference>('theme_preference', () =>
    normalizeThemePreference(cookie.value)
  )

  const setPreference = (value: unknown) => {
    const next = normalizeThemePreference(value)
    preference.value = next
    cookie.value = next
  }

  return { preference: readonly(preference), setPreference, options: THEME_OPTIONS }
}

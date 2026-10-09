// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  css: ['~/assets/css/tokens.css', '~/assets/css/themes.css', '~/assets/css/base.css'],
  routeRules: {
    '/api/**': { proxy: 'http://backend:8000/**' }
  }
})

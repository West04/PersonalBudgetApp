<script setup lang="ts">
definePageMeta({
  middleware: [
    function (to, from) {
      return navigateTo({ path: '/dashboard', query: to.query })
    },
  ],
})
</script>

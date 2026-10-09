<template>
  <span class="money" :class="`money--${tone}`">{{ text }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatMoney, type MoneySign, type MoneyTone } from '~/utils/money'

/**
 * Displays a financial value with tabular figures and a caller-chosen tone.
 * It formats only: no calculation, no sign-based judgement.
 */
const props = withDefaults(
  defineProps<{
    amount: number | string | null | undefined
    tone?: MoneyTone
    sign?: MoneySign
  }>(),
  {
    tone: 'neutral',
    sign: 'auto',
  }
)

const text = computed(() => formatMoney(props.amount, props.sign))
</script>

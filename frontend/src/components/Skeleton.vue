<script setup>
// 骨架屏：首屏用，避免请求期间整块空白
const props = defineProps({
  variant: { type: String, default: "cards" }, // cards | rows | lines | stats
  count: { type: Number, default: 12 },
});
</script>

<template>
  <div v-if="variant === 'cards'" class="grid-media">
    <div v-for="i in count" :key="i" class="stack" style="gap: 6px">
      <div class="sk sk-card"></div>
      <div class="sk sk-text" style="width: 72%"></div>
      <div class="sk sk-text" style="width: 44%"></div>
    </div>
  </div>
  <div v-else-if="variant === 'rows'" class="stack" style="gap: 0">
    <div
      v-for="i in count"
      :key="i"
      class="sk sk-row"
      style="margin-bottom: 1px; border-radius: 0"
    ></div>
  </div>
  <div v-else-if="variant === 'stats'" class="stat-grid">
    <div v-for="i in count" :key="i" class="stat">
      <div class="sk sk-text" style="width: 40%; height: 22px"></div>
      <div class="sk sk-text" style="width: 60%; margin-top: 8px"></div>
    </div>
  </div>
  <div v-else class="stack-3">
    <div v-for="i in count" :key="i" class="sk sk-text" :style="{ width: `${100 - i * 7}%` }"></div>
  </div>
</template>

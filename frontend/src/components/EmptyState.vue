<script setup>
import Icon from "./Icon.vue";

defineProps({
  title: { type: String, default: "" },
  hint: { type: String, default: "" },
  icon: { type: String, default: "" },
  compact: { type: Boolean, default: false },
});
</script>

<template>
  <div class="empty" :class="{ 'is-compact': compact }">
    <Icon :name="icon || 'image'" :size="compact ? 26 : 40" />
    <div v-if="title" class="title">{{ title }}</div>
    <div v-if="hint" class="hint">{{ hint }}</div>
    <div v-if="$slots.action" style="margin-top: 8px">
      <slot name="action" />
    </div>
    <slot />
  </div>
</template>

<style scoped>
.empty.is-compact {
  padding: 24px 8px;
}
</style>

<script setup>
import Icon from "./Icon.vue";

defineProps({
  value: { type: [Number, String], default: "—" },
  label: { type: String, required: true },
  footer: { type: String, default: "" },
  tone: { type: String, default: "" }, // '' | ok | warn | danger | accent
  icon: { type: String, default: "" },
  clickable: { type: Boolean, default: false },
});
</script>

<template>
  <component
    :is="clickable ? 'button' : 'div'"
    class="stat"
    :class="{ 'stat-click': clickable }"
    :type="clickable ? 'button' : undefined"
  >
    <div v-if="icon || $slots.action" class="row-between" style="align-items: flex-start">
      <Icon v-if="icon" :name="icon" :size="16" class="dim" />
      <div v-if="$slots.action"><slot name="action" /></div>
    </div>
    <div
      class="num"
      :style="
        tone === 'ok'
          ? { color: 'var(--ok)' }
          : tone === 'warn'
            ? { color: 'var(--warn)' }
            : tone === 'danger'
              ? { color: 'var(--danger)' }
              : tone === 'accent'
                ? { color: 'var(--accent-text)' }
                : {}
      "
    >
      {{ value }}
    </div>
    <div class="label">{{ label }}</div>
    <div v-if="footer" class="foot">{{ footer }}</div>
  </component>
</template>

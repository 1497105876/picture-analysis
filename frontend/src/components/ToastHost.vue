<script setup>
import { computed } from "vue";

import Icon from "./Icon.vue";
import { toasts, dismiss } from "../app/toast.js";

const TONE = {
  info: { icon: "info", cls: "" },
  ok: { icon: "check", cls: "toast-ok" },
  warn: { icon: "warning", cls: "toast-warn" },
  error: { icon: "warning", cls: "toast-error" },
};
const items = computed(() =>
  toasts.items.map((t) => ({ ...t, meta: TONE[t.level] || TONE.info })),
);
</script>

<template>
  <div class="toasts" role="status" aria-live="polite">
    <div v-for="t in items" :key="t.id" class="toast" :class="t.meta.cls">
      <Icon :name="t.meta.icon" :size="15" style="margin-top: 2px; flex: none" />
      <span class="wrap-anywhere">{{ t.message }}</span>
      <button class="close" aria-label="关闭" @click="dismiss(t.id)">
        <Icon name="close" :size="13" />
      </button>
    </div>
  </div>
</template>

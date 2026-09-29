<script setup>
// 通用区块容器：标题 + 副标题 + 右侧操作 + 可折叠
import { ref } from "vue";

import Icon from "./Icon.vue";

const props = defineProps({
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  count: { type: [Number, String], default: "" },
  collapsible: { type: Boolean, default: false },
  defaultOpen: { type: Boolean, default: true },
  danger: { type: Boolean, default: false },
  flush: { type: Boolean, default: false },
  inset: { type: Boolean, default: false },
});
const open = ref(props.defaultOpen);
</script>

<template>
  <section class="panel" :class="{ 'panel-danger': danger, 'panel-flush': flush, 'panel-inset': inset }">
    <div v-if="title || $slots.actions" class="panel-head">
      <div class="grow" style="min-width: 0">
        <h3 @click="collapsible && (open = !open)" :style="collapsible ? { cursor: 'pointer' } : {}">
          <Icon v-if="collapsible" :name="open ? 'chevronDown' : 'chevronRight'" :size="14" />
          {{ title }}
          <span v-if="count !== ''" class="tag tag-outline">{{ count }}</span>
          <slot name="title-extra" />
        </h3>
        <div v-if="subtitle" class="panel-sub">{{ subtitle }}</div>
        <slot name="sub" />
      </div>
      <div v-if="$slots.actions" class="head-actions"><slot name="actions" /></div>
    </div>
    <slot v-if="!collapsible || open" />
  </section>
</template>

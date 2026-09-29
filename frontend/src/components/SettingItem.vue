<script setup>
// schema 驱动的配置控件：新增配置项前端零改动的关键。
// int/float/bool/select/text/tags/csv 七种类型；select 支持 free（绑定书签等允许写列表外的值）。
import { computed } from "vue";

import TagInput from "./TagInput.vue";

const props = defineProps({
  item: { type: Object, required: true },
  modelValue: { type: [String, Number, Boolean, Array], default: "" },
});
const emit = defineEmits(["update:modelValue"]);

const listId = computed(() => `dl-${props.item.key}`);
const asArray = computed(() => {
  const v = props.modelValue;
  if (Array.isArray(v)) return v;
  if (typeof v === "string") return v.split(",").map((s) => s.trim()).filter(Boolean);
  return [];
});
const isCompact = computed(() => ["bool"].includes(props.item.type));

function set(v) {
  emit("update:modelValue", v);
}
</script>

<template>
  <!-- 开关 -->
  <label v-if="item.type === 'bool'" class="field bool-field">
    <span class="bool-head">
      <span class="lab">{{ item.label }}</span>
      <span class="switch">
        <input type="checkbox" :checked="Boolean(modelValue)" @change="set(!modelValue)" />
        <span class="track"></span>
        <span class="knob"></span>
      </span>
    </span>
    <span v-if="item.help" class="hint">{{ item.help }}</span>
  </label>

  <!-- 枚举 -->
  <label v-else-if="item.type === 'select' && !item.free" class="field">
    <span class="lab">{{ item.label }}</span>
    <select class="select" :value="modelValue" @change="set($event.target.value)">
      <option v-for="o in item.options" :key="o" :value="o">{{ o }}</option>
    </select>
    <span v-if="item.help" class="hint">{{ item.help }}</span>
  </label>

  <!-- 枚举但可自由输入（档案绑定） -->
  <label v-else-if="item.type === 'select' && item.free" class="field">
    <span class="lab">{{ item.label }}</span>
    <input class="input" :list="listId" :value="modelValue" @input="set($event.target.value)" />
    <datalist :id="listId">
      <option v-for="o in item.options" :key="o" :value="o" />
    </datalist>
    <span v-if="item.help" class="hint">{{ item.help }}</span>
  </label>

  <!-- 数字 -->
  <label v-else-if="item.type === 'int' || item.type === 'float'" class="field">
    <span class="lab">{{ item.label }}</span>
    <input
      class="input"
      type="number"
      :value="modelValue"
      :step="item.type === 'float' ? 0.1 : 1"
      :min="item.min ?? undefined"
      :max="item.max ?? undefined"
      @input="set($event.target.value === '' ? '' : Number($event.target.value))"
    />
    <span v-if="item.help" class="hint">{{ item.help }}</span>
  </label>

  <!-- 标签 / 逗号列表 -->
  <div v-else-if="item.type === 'csv'" class="field">
    <span class="lab">{{ item.label }}</span>
    <TagInput :model-value="asArray" @update:model-value="set" />
    <span v-if="item.help" class="hint">{{ item.help }}</span>
  </div>

  <!-- 文本 / tags -->
  <label v-else class="field">
    <span class="lab">
      {{ item.label }}
      <span class="tiny dim">{{ item.type }}</span>
    </span>
    <input class="input" :value="modelValue" @input="set($event.target.value)" />
    <span v-if="item.help" class="hint">{{ item.help }}</span>
  </label>
</template>

<style scoped>
.bool-field {
  min-width: 220px;
}
.bool-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  height: 28px;
}
</style>

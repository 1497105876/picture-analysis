<script setup>
// 标签输入：回车 / 逗号 / 中英文逗号都分隔，退格删末尾
import { computed, ref } from "vue";

import Icon from "./Icon.vue";

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  placeholder: { type: String, default: "输入后回车" },
  suggestions: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);

const draft = ref("");

const candidates = computed(() => {
  const q = draft.value.trim().toLowerCase();
  if (!q) return [];
  return props.suggestions.filter((s) => s.toLowerCase().includes(q) && !props.modelValue.includes(s)).slice(0, 6);
});

function add(text) {
  const v = String(text || "").trim();
  if (!v) return;
  const next = [...props.modelValue];
  if (!next.includes(v)) next.push(v);
  emit("update:modelValue", next);
  draft.value = "";
}

function remove(v) {
  emit(
    "update:modelValue",
    props.modelValue.filter((x) => x !== v),
  );
}

function onKey(e) {
  if (e.key === "Enter" || e.key === "," || e.key === "，") {
    e.preventDefault();
    add(draft.value);
  } else if (e.key === "Backspace" && !draft.value && props.modelValue.length) {
    remove(props.modelValue[props.modelValue.length - 1]);
  }
}
</script>

<template>
  <div class="stack" style="gap: 6px">
    <div class="taginput" @click="$refs.input?.focus()">
      <span v-for="t in modelValue" :key="t" class="tag tag-accent">
        {{ t }}
        <span class="x" @click.stop="remove(t)">×</span>
      </span>
      <input
        ref="input"
        v-model="draft"
        :placeholder="modelValue.length ? '' : placeholder"
        @keyup="onKey"
        @blur="add(draft)"
      />
    </div>
    <div v-if="candidates.length" class="row" style="gap: 4px">
      <span
        v-for="s in candidates"
        :key="s"
        class="tag tag-outline tag-click"
        @mousedown.prevent="add(s)"
      >
        + {{ s }}
      </span>
      <Icon name="info" :size="12" class="dim" />
    </div>
  </div>
</template>

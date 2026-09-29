<script setup>
// 统一确认弹窗：替代 window.confirm / window.prompt。
// 三种模式：
//   默认           —— 点确认即通过
//   confirmWord    —— 必须输入指定字符串（服务端要求的确认词，如「清空回收站」、文件名）
//   prompt         —— 输入一段文本（初值可预填），返回输入值
import { computed, ref, watch } from "vue";

import Modal from "./Modal.vue";
import Icon from "./Icon.vue";

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: "请确认" },
  message: { type: String, default: "" },
  details: { type: Array, default: () => [] },
  confirmText: { type: String, default: "确定" },
  cancelText: { type: String, default: "取消" },
  danger: { type: Boolean, default: false },
  confirmWord: { type: String, default: "" },
  promptLabel: { type: String, default: "" },
  promptValue: { type: String, default: "" },
  promptPlaceholder: { type: String, default: "" },
  busy: { type: Boolean, default: false },
  icon: { type: String, default: "" },
});
const emit = defineEmits(["confirm", "close"]);

const input = ref("");

watch(
  () => props.open,
  (v) => {
    input.value = v ? props.promptValue || "" : "";
  },
);

const isPrompt = computed(() => Boolean(props.promptLabel));
const canConfirm = computed(() => {
  if (props.busy) return false;
  if (props.confirmWord) return input.value === props.confirmWord;
  return true;
});

function confirm() {
  if (!canConfirm.value) return;
  emit("confirm", props.confirmWord ? props.confirmWord : input.value);
}
</script>

<template>
  <Modal
    :open="open"
    size="sm"
    :title="title"
    @close="!busy && emit('close')"
  >
    <div class="stack-3">
      <div class="row" style="align-items: flex-start; gap: 10px">
        <Icon
          v-if="danger"
          name="warning"
          :size="18"
          style="color: var(--danger); flex: none; margin-top: 2px"
        />
        <Icon
          v-else-if="icon"
          :name="icon"
          :size="18"
          style="color: var(--accent-text); flex: none; margin-top: 2px"
        />
        <div class="grow stack" style="gap: 6px">
          <div v-if="message">{{ message }}</div>
          <ul v-if="details.length" class="bullets small muted">
            <li v-for="(d, i) in details" :key="i">{{ d }}</li>
          </ul>
          <slot />
        </div>
      </div>

      <div v-if="confirmWord || isPrompt" class="field">
        <span class="lab">
          {{ confirmWord ? `请输入「${confirmWord}」以继续` : promptLabel }}
        </span>
        <input
          v-model="input"
          class="input mono"
          :placeholder="confirmWord ? confirmWord : promptPlaceholder"
          autofocus
          @keyup.enter="confirm"
        />
      </div>
    </div>

    <template #foot>
      <button class="btn" :disabled="busy" @click="emit('close')">{{ cancelText }}</button>
      <button
        class="btn"
        :class="danger ? 'btn-danger' : 'btn-primary'"
        :disabled="!canConfirm"
        @click="confirm"
      >
        <span v-if="busy" class="spin"></span>
        {{ confirmText }}
      </button>
    </template>
  </Modal>
</template>

<style scoped>
.bullets {
  margin: 0;
  padding-left: 18px;
}
.bullets li {
  margin: 2px 0;
}
</style>

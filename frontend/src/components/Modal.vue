<script setup>
// 基础浮层：遮罩点击关闭、Esc 关闭、body 滚动锁定
import { onBeforeUnmount, watch } from "vue";

const props = defineProps({
  open: { type: Boolean, default: false },
  size: { type: String, default: "" }, // sm | lg | ''
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  width: { type: String, default: "" },
  dismissable: { type: Boolean, default: true },
});
const emit = defineEmits(["close"]);

function onKey(e) {
  if (e.key === "Escape" && props.open && props.dismissable) {
    stop();
    emit("close");
  }
}
function stop() {
  window.removeEventListener("keydown", onKey);
  document.body.style.overflow = "";
}
watch(
  () => props.open,
  (v) => {
    if (v) {
      window.addEventListener("keydown", onKey);
      document.body.style.overflow = "hidden";
    } else {
      stop();
    }
  },
);
onBeforeUnmount(stop);
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="mask" @click="dismissable && emit('close')"></div>
    <div v-if="open" class="modal" @click.self="dismissable && emit('close')">
      <div
        class="modal-box"
        :class="{ 'modal-sm': size === 'sm', 'modal-lg': size === 'lg' }"
        :style="width ? { width } : undefined"
        role="dialog"
        aria-modal="true"
      >
        <div v-if="title || $slots.head" class="modal-head">
          <slot name="head">
            <h3>{{ title }}</h3>
            <div v-if="subtitle" class="panel-sub">{{ subtitle }}</div>
          </slot>
        </div>
        <div class="modal-body" :style="!$slots.head && !title ? { paddingTop: '16px' } : undefined">
          <slot />
        </div>
        <div v-if="$slots.foot" class="modal-foot"><slot name="foot" /></div>
      </div>
    </div>
  </Teleport>
</template>

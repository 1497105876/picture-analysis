<script setup>
// 星级：0–5。点当前星再点一次 = 清零；只读模式用于卡片展示。
const props = defineProps({
  modelValue: { type: Number, default: 0 },
  readonly: { type: Boolean, default: false },
  size: { type: Number, default: 15 },
});
const emit = defineEmits(["update:modelValue"]);

function pick(n) {
  if (props.readonly) return;
  emit("update:modelValue", n === props.modelValue ? 0 : n);
}
</script>

<template>
  <div class="stars" :aria-label="`评分 ${modelValue} 星`">
    <button
      v-for="n in 5"
      :key="n"
      type="button"
      :class="{ on: n <= modelValue }"
      :style="{ fontSize: `${size}px` }"
      :disabled="readonly"
      :aria-label="`${n} 星`"
      @click="pick(n)"
    >
      ★
    </button>
  </div>
</template>

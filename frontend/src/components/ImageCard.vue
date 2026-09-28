<script setup>
import { thumbUrl } from "../api.js";

defineProps({
  image: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  selectable: { type: Boolean, default: true },
});
const emit = defineEmits(["toggle", "open"]);
</script>

<template>
  <div class="card" @click="emit('open', image)">
    <input
      v-if="selectable"
      class="check"
      type="checkbox"
      :checked="selected"
      @click.stop="emit('toggle', image.id)"
    />
    <span v-if="image.favorite" class="star">★</span>
    <div class="ph">
      <img :src="thumbUrl(image.id)" :alt="image.filename" loading="lazy" />
    </div>
    <div class="meta">
      <div class="name">{{ image.filename }}</div>
      <div class="desc">{{ image.description || "（无描述）" }}</div>
      <div>
        <span class="tag blue">{{ image.category || "未分类" }}</span>
        <span v-if="image.rating" class="tag">{{ "★".repeat(image.rating) }}</span>
        <span v-if="image.analysis_state === 'failed'" class="tag red">失败</span>
        <span v-else-if="image.analysis_state === 'skipped'" class="tag">跳过</span>
        <span v-else-if="image.analysis_state === 'done'" class="tag green">已识别</span>
      </div>
    </div>
  </div>
</template>

<script setup>
// 单图卡片。列表接口返回的是 images 表原始列，合并字段要自己算（人工位优先）。
import { computed, ref, watch } from "vue";

import { thumbUrl } from "../app/api.js";
import { categoryOf, descriptionOf, stateMeta, bytes } from "../app/format.js";
import Icon from "./Icon.vue";
import StarRating from "./StarRating.vue";

const props = defineProps({
  image: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  selectable: { type: Boolean, default: true },
  masked: { type: Boolean, default: false },
});
const emit = defineEmits(["toggle", "open"]);

const broken = ref(false);
watch(
  () => props.image.id,
  () => (broken.value = false),
);

const category = computed(() => categoryOf(props.image));
const description = computed(() => descriptionOf(props.image));
const meta = computed(() => stateMeta(props.image.analysis_state));
const href = computed(() => thumbUrl(props.image.id));
</script>

<template>
  <article
    class="img-card"
    :class="{ 'is-selected': selected, 'is-masked': masked }"
    tabindex="0"
    role="button"
    :aria-label="image.filename"
    @click="emit('open', image)"
    @keyup.enter="emit('open', image)"
  >
    <input
      v-if="selectable"
      class="check checkbox"
      type="checkbox"
      :checked="selected"
      :aria-label="`选择 ${image.filename}`"
      @click.stop
      @change="emit('toggle', image.id)"
    />
    <span v-if="image.favorite" class="star" title="已收藏">★</span>

    <div class="thumb">
      <img
        v-if="!broken"
        :src="href"
        :alt="image.filename"
        loading="lazy"
        decoding="async"
        @error="broken = true"
      />
      <div v-else class="fallback">
        <Icon name="image" :size="20" />
        <div class="tiny dim" style="margin-top: 2px">没有缩略图</div>
      </div>
      <span
        v-if="image.analysis_state !== 'done'"
        class="tag corner-state"
        :class="`tag-${meta.tone}`"
      >
        {{ meta.text }}
      </span>
    </div>

    <div class="meta">
      <div class="name clamp-1" :title="image.filename">{{ image.filename }}</div>
      <div class="desc clamp-1" :title="description">{{ description || "（尚无描述）" }}</div>
      <div class="row" style="gap: 4px">
        <span class="tag" :class="category ? 'tag-accent' : 'tag-outline'">
          {{ category || "未分类" }}
        </span>
        <StarRating v-if="image.rating" :model-value="image.rating" readonly :size="12" />
        <span v-if="image.hidden" class="tag tag-danger">隐藏</span>
        <span v-if="image.missing" class="tag tag-danger">文件丢失</span>
      </div>
      <div class="tiny dim mono">
        {{ image.width && image.height ? `${image.width}×${image.height} · ` : "" }}{{ bytes(image.bytes) }}
      </div>
    </div>
  </article>
</template>

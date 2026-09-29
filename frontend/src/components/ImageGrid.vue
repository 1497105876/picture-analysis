<script setup>
// 列表统一容器：网格 / 列表双视图 + 多选 + 全选 + 加载态 + 空态 + 无限滚动
import { computed, onBeforeUnmount, ref, watch } from "vue";

import { thumbUrl } from "../app/api.js";
import { categoryOf, descriptionOf, stateMeta } from "../app/format.js";
import EmptyState from "./EmptyState.vue";
import Icon from "./Icon.vue";
import ImageCard from "./ImageCard.vue";
import Skeleton from "./Skeleton.vue";

const props = defineProps({
  items: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  loadingMore: { type: Boolean, default: false },
  hasMore: { type: Boolean, default: false },
  error: { type: String, default: "" },
  view: { type: String, default: "grid" }, // grid | list
  selected: { type: Object, default: () => new Set() },
  selectable: { type: Boolean, default: true },
  masked: { type: Boolean, default: false },
  emptyTitle: { type: String, default: "这里还是空的" },
  emptyHint: { type: String, default: "" },
  skeletonCount: { type: Number, default: 12 },
});
const emit = defineEmits(["open", "toggle", "select-all", "clear-selection", "load-more"]);

const sentinel = ref(null);
let observer = null;

const ids = computed(() => props.items.map((i) => i.id));
const allPicked = computed(() => ids.value.length > 0 && ids.value.every((id) => props.selected.has(id)));
const pickedCount = computed(() => ids.value.filter((id) => props.selected.has(id)).length);

function toggle(id) {
  emit("toggle", id);
}
function toggleAll() {
  if (allPicked.value) emit("clear-selection");
  else emit("select-all", ids.value);
}

// 无限滚动：哨兵进入视口且还有下一页时触发一次
function observe(el) {
  observer?.disconnect();
  if (!el || typeof IntersectionObserver === "undefined") return;
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0]?.isIntersecting && props.hasMore && !props.loadingMore && !props.loading) {
        emit("load-more");
      }
    },
    { rootMargin: "320px" },
  );
  observer.observe(el);
}
watch(sentinel, (el) => observe(el));
watch(
  () => props.hasMore,
  (v) => {
    if (v) observe(sentinel.value);
  },
);
onBeforeUnmount(() => observer?.disconnect());

function rowState(row) {
  return stateMeta(row.analysis_state);
}
</script>

<template>
  <div class="stack-3">
    <!-- 工具条 -->
    <div v-if="$slots.toolbar || selectable" class="row-between">
      <slot name="toolbar" />
      <div v-if="selectable" class="row dim small">
        <label class="lab-check">
          <input class="checkbox" type="checkbox" :checked="allPicked" @change="toggleAll" />
          全选本页
        </label>
        <span v-if="pickedCount">已选 {{ pickedCount }}</span>
        <button v-if="pickedCount" class="btn btn-xs" @click="emit('clear-selection')">清空选择</button>
      </div>
    </div>

    <!-- 出错 -->
    <div v-if="error" class="banner banner-danger">
      <Icon name="warning" :size="16" style="margin-top: 2px" />
      <div class="stack" style="gap: 2px">
        <div class="strong">加载失败</div>
        <div class="small">{{ error }}</div>
      </div>
    </div>

    <!-- 首屏骨架 -->
    <Skeleton v-else-if="loading && !items.length" :variant="view === 'grid' ? 'cards' : 'rows'" :count="view === 'grid' ? skeletonCount : 8" />

    <!-- 空态 -->
    <EmptyState
      v-else-if="!loading && !items.length"
      :title="emptyTitle"
      :hint="emptyHint"
      :icon="view === 'grid' ? 'image' : 'list'"
    >
      <template v-if="$slots.empty" #action><slot name="empty" /></template>
    </EmptyState>

    <!-- 数据 -->
    <template v-else>
      <div v-if="view === 'grid'" class="grid-media">
        <ImageCard
          v-for="img in items"
          :key="img.id"
          :image="img"
          :selected="selected.has(img.id)"
          :selectable="selectable"
          :masked="masked"
          @toggle="toggle"
          @open="(i) => emit('open', i)"
        />
      </div>

      <div v-else style="border: 1px solid var(--line); border-radius: var(--radius-sm); overflow: hidden">
        <div
          v-for="img in items"
          :key="img.id"
          class="row-media"
          :class="{ 'is-selected': selected.has(img.id) }"
          role="button"
          tabindex="0"
          @click="emit('open', img)"
          @keyup.enter="emit('open', img)"
        >
          <input
            v-if="selectable"
            class="checkbox"
            type="checkbox"
            :checked="selected.has(img.id)"
            @click.stop
            @change="toggle(img.id)"
          />
          <div class="pic">
            <img :src="thumbUrl(img.id)" :alt="img.filename" loading="lazy" decoding="async" />
          </div>
          <div class="info">
            <div class="row" style="gap: 6px">
              <span class="strong clamp-1" style="max-width: 46%">{{ img.filename }}</span>
              <span class="tag" :class="categoryOf(img) ? 'tag-accent' : 'tag-outline'">
                {{ categoryOf(img) || "未分类" }}
              </span>
              <span class="tag" :class="`tag-${rowState(img).tone}`">{{ rowState(img).text }}</span>
              <span v-if="img.favorite" class="tag tag-warn">★ 收藏</span>
            </div>
            <div class="small muted clamp-1">{{ descriptionOf(img) || img.path }}</div>
          </div>
          <div class="small dim nowrap">{{ img.id }}</div>
        </div>
      </div>

      <!-- 翻页 -->
      <div ref="sentinel" style="height: 1px"></div>
      <div class="row" style="justify-content: center; padding-top: 4px">
        <span v-if="loadingMore" class="small muted row" style="gap: 6px">
          <span class="spin" style="width: 12px; height: 12px; border: 2px solid var(--line-strong); border-right-color: var(--accent); border-radius: 50%; display: inline-block; animation: pa-spin 700ms linear infinite"></span>
          加载中…
        </span>
        <button
          v-else-if="hasMore"
          class="btn btn-sm"
          @click="emit('load-more')"
        >
          加载更多
        </button>
        <span v-else class="small dim">没有更多了</span>
      </div>
    </template>
  </div>
</template>

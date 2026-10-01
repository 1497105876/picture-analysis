<script setup>
// 检索：关键词 + 向量 RRF 混合。结果头把耗时拆出来，让用户看得懂「为什么慢」。
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "../app/api.js";
import { catalog, loadCatalog } from "../app/catalog.js";
import { notify } from "../app/toast.js";
import { num } from "../app/format.js";
import { privacyMode } from "../app/settings.js";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import ImageDrawer from "../components/ImageDrawer.vue";
import ImageGrid from "../components/ImageGrid.vue";
import Panel from "../components/Panel.vue";

const route = useRoute();
const router = useRouter();

const form = reactive({
  q: "",
  mode: "",
  category: "",
  rating_min: "",
  date_from: "",
  date_to: "",
  favorite: "",
  sort: "",
  order: "desc",
});
const view = ref("grid");
const searching = ref(false);
const loadingMore = ref(false);
const result = ref(null);
const error = ref("");
const history = ref([]);
const openId = ref(null);
const selected = ref(new Set());

const items = computed(() => result.value?.items || []);
const ids = computed(() => items.value.map((i) => i.id));

function queryParams(extra = {}) {
  return {
    q: form.q || undefined,
    mode: form.mode || undefined,
    category: form.category || undefined,
    rating_min: form.rating_min || undefined,
    date_from: form.date_from || undefined,
    date_to: form.date_to || undefined,
    favorite: form.favorite || undefined,
    sort: form.sort || undefined,
    order: form.order,
    ...extra,
  };
}

async function run(reset = true) {
  if (reset) searching.value = true;
  else loadingMore.value = true;
  error.value = "";
  try {
    const data = await api.search({
      ...queryParams(),
      limit: 48,
      cursor: reset ? undefined : result.value?.next_cursor || undefined,
    });
    if (reset) {
      result.value = data;
      selected.value = new Set();
    } else {
      result.value = {
        ...data,
        items: [...(result.value?.items || []), ...(data.items || [])],
      };
    }
    if (reset && form.q) {
      try {
        history.value = (await api.searchHistory()).items || [];
      } catch {
        /* 历史拿不到就算了 */
      }
    }
  } catch (e) {
    error.value = e.message;
    if (reset) result.value = null;
  } finally {
    searching.value = false;
    loadingMore.value = false;
  }
}

async function loadHistory() {
  try {
    history.value = (await api.searchHistory()).items || [];
  } catch {
    history.value = [];
  }
}

async function clearHistory() {
  try {
    await api.clearSearchHistory();
    history.value = [];
    notify("搜索历史已清空", "ok");
  } catch (e) {
    notify(e.message, "error");
  }
}

function useHistory(q) {
  form.q = q;
  router.replace({ path: "/search", query: { q } });
  run();
}

function submit() {
  router.replace({ path: "/search", query: form.q ? { q: form.q } : {} });
  run();
}

const MODES = [
  { value: "", label: "跟随设置" },
  { value: "hybrid", label: "混合（默认）" },
  { value: "keyword", label: "纯关键词" },
  { value: "vector", label: "纯向量" },
];

const timings = computed(() => result.value?.timings || {});
// 基准取三者里的最大值：拿 total_ms 当分母的话，"总耗时"那条永远满格，等于没有信息
const maxTiming = computed(() =>
  Math.max(
    Number(timings.value.total_ms) || 0,
    Number(timings.value.keyword_ms) || 0,
    Number(timings.value.vector_ms) || 0,
    0.01,
  ),
);
function width(key) {
  const v = Number(timings.value[key]) || 0;
  return `${Math.min(100, (v / maxTiming.value) * 100)}%`;
}

onMounted(async () => {
  await loadCatalog();
  const q = route.query.q;
  form.q = typeof q === "string" ? q : "";
  await Promise.all([loadHistory(), run()]);
});

watch(
  () => route.query.q,
  (q) => {
    if (typeof q === "string" && q !== form.q) {
      form.q = q;
      run();
    }
  },
);

const hasFilter = computed(() =>
  Boolean(form.category || form.rating_min || form.date_from || form.date_to || form.favorite || form.mode),
);
function clearFilters() {
  Object.assign(form, { category: "", rating_min: "", date_from: "", date_to: "", favorite: "", mode: "" });
  run();
}
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>检索</h1>
        <div class="sub">FTS5 关键词 + 向量召回，RRF 融合后统一排序</div>
      </div>
      <div class="head-actions">
        <button class="btn btn-sm" :disabled="!history.length" @click="clearHistory">清空历史</button>
      </div>
    </div>

    <Panel flush>
      <div class="stack-3" style="padding: 12px var(--panel-pad)">
        <div class="row" style="gap: 8px">
          <div class="searchbox grow" style="width: auto">
            <Icon name="search" :size="14" />
            <input
              v-model="form.q"
              placeholder="描述你想找的图，回车检索（如：海边 日落）"
              @keyup.enter="submit"
            />
          </div>
          <select v-model="form.mode" class="select select-sm" style="width: 132px" @change="run()">
            <option v-for="m in MODES" :key="m.value" :value="m.value">{{ m.label }}</option>
          </select>
          <button class="btn btn-primary" :disabled="searching" @click="submit">
            <span v-if="searching" class="spin"></span>
            检索
          </button>
        </div>

        <div class="row" style="gap: 8px">
          <select v-model="form.category" class="select select-sm" style="width: 130px" @change="run()">
            <option value="">全部分类</option>
            <option v-for="c in catalog.categories" :key="c.id" :value="c.name">{{ c.emoji }} {{ c.name }}</option>
          </select>
          <select v-model="form.rating_min" class="select select-sm" style="width: 112px" @change="run()">
            <option value="">任意评分</option>
            <option v-for="n in 5" :key="n" :value="n">{{ n }} 星以上</option>
          </select>
          <select v-model="form.favorite" class="select select-sm" style="width: 104px" @change="run()">
            <option value="">收藏不限</option>
            <option value="true">仅收藏</option>
            <option value="false">未收藏</option>
          </select>
          <input v-model="form.date_from" class="input input-sm" type="date" style="width: 140px" @change="run()" />
          <span class="dim small">至</span>
          <input v-model="form.date_to" class="input input-sm" type="date" style="width: 140px" @change="run()" />
          <select v-model="form.sort" class="select select-sm" style="width: 116px" @change="run()">
            <option value="">默认排序</option>
            <option value="mtime">修改时间</option>
            <option value="taken">拍摄时间</option>
            <option value="created">入库时间</option>
            <option value="rating">评分</option>
            <option value="filename">文件名</option>
          </select>
          <span class="spacer"></span>
          <button v-if="hasFilter" class="btn btn-xs" @click="clearFilters">清空条件</button>
        </div>

        <div v-if="history.length" class="row small" style="gap: 6px">
          <span class="dim">历史：</span>
          <span v-for="q in history" :key="q" class="tag tag-outline tag-click" @click="useHistory(q)">{{ q }}</span>
        </div>
      </div>
    </Panel>

    <!-- 结果信息 -->
    <div v-if="result" class="panel">
      <div class="row-between">
        <div class="row small" style="gap: 10px">
          <span class="strong">{{ num(result.total ?? items.length) }} 条命中</span>
          <span class="tag tag-accent">{{ result.mode }}</span>
          <span class="dim">
            总耗时 {{ result.timings?.total_ms }}ms（关键词 {{ result.timings?.keyword_ms }}ms / 向量
            {{ result.timings?.vector_ms }}ms）
          </span>
        </div>
        <div class="seg">
          <button :class="{ 'is-on': view === 'grid' }" @click="view = 'grid'">
            <Icon name="grid" :size="13" />
          </button>
          <button :class="{ 'is-on': view === 'list' }" @click="view = 'list'">
            <Icon name="list" :size="13" />
          </button>
        </div>
      </div>

      <div v-if="result.degraded" class="banner banner-warn" style="margin-top: 10px">
        <Icon name="warning" :size="14" style="margin-top: 2px" />
        <div class="stack small" style="gap: 2px; min-width: 0">
          <div>本次检索已降级：没有可用的嵌入档案（或嵌入调用失败），实际只走了关键词通路。</div>
          <div class="dim">
            常见原因：档案里的「嵌入模型名」填了识图模型（不是所有模型都能做嵌入），
            或者这个模型需要额外的启动参数。
          </div>
        </div>
        <router-link class="btn btn-sm" style="margin-left: auto" to="/settings">
          去配嵌入模型
        </router-link>
        <router-link class="btn btn-sm" to="/jobs">看失败任务</router-link>
      </div>

      <div class="row small" style="gap: 8px; margin-top: 10px">
        <span class="dim" style="width: 62px">总耗时</span>
        <div class="bar grow"><i :style="{ width: width('total_ms') }"></i></div>
        <span class="mono dim nowrap" style="width: 72px; text-align: right">{{ timings.total_ms }}ms</span>
      </div>
      <div class="row small" style="gap: 8px; margin-top: 4px">
        <span class="dim" style="width: 62px">关键词</span>
        <div class="bar grow"><i :style="{ width: width('keyword_ms') }"></i></div>
        <span class="mono dim nowrap" style="width: 72px; text-align: right">{{ timings.keyword_ms }}ms</span>
      </div>
      <div class="row small" style="gap: 8px; margin-top: 4px">
        <span class="dim" style="width: 62px">向量</span>
        <div class="bar grow"><i :style="{ width: width('vector_ms') }"></i></div>
        <span class="mono dim nowrap" style="width: 72px; text-align: right">{{ timings.vector_ms }}ms</span>
      </div>
    </div>

    <!-- 结果列表 -->
    <template v-if="searching && !result">
      <div class="grid-media">
        <div v-for="i in 12" :key="i" class="stack" style="gap: 6px">
          <div class="sk sk-card"></div>
          <div class="sk sk-text" style="width: 70%"></div>
        </div>
      </div>
    </template>

    <ImageGrid
      v-else-if="result"
      :items="items"
      :loading="false"
      :loading-more="loadingMore"
      :has-more="Boolean(result?.next_cursor)"
      :error="error"
      :view="view"
      :selected="selected"
      :selectable="false"
      :masked="privacyMode"
      empty-title="没有匹配结果"
      empty-hint="换个说法、放宽评分条件，或者先在设置里配好检索档案。"
      @open="(img) => (openId = img.id)"
      @load-more="run(false)"
    />
    <EmptyState
      v-else-if="!error"
      icon="search"
      title="输入一句话开始找图"
      hint="支持自然语言式的关键词组合；混合模式会同时走关键词与向量两条路再融合。"
    />

    <ImageDrawer v-if="openId" v-model:image-id="openId" :ids="ids" @close="openId = null" />
  </div>
</template>

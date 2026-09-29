<script setup>
// 智能相册：按查询条件动态回放。图片变了相册自动跟着变，不需要手动维护成员表。
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, thumbUrl } from "../app/api.js";
import { catalog, loadCatalog } from "../app/catalog.js";
import { notify } from "../app/toast.js";
import { privacyMode } from "../app/settings.js";
import { num } from "../app/format.js";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import ImageDrawer from "../components/ImageDrawer.vue";
import ImageGrid from "../components/ImageGrid.vue";
import Panel from "../components/Panel.vue";
import Skeleton from "../components/Skeleton.vue";

const route = useRoute();
const router = useRouter();

const albums = ref([]);
const covers = ref({});
const active = ref(null);
const images = ref([]);
const cursor = ref(null);
const loading = ref(true);
const loadingImages = ref(false);
const openId = ref(null);
const askDelete = ref(null);
const selected = ref(new Set());

const formMode = ref("visual");
const form = reactive({
  id: null,
  name: "",
  category: "",
  rating_min: "",
  favorite: false,
  tags: [],
  dir_id: "",
  json: '{"category": "风景"}',
});

const dirs = ref([]);

async function load() {
  loading.value = true;
  try {
    albums.value = (await api.albums()).items || [];
    await loadCovers();
    const paramId = route.params.id;
    if (paramId) {
      const hit = albums.value.find((a) => String(a.id) === String(paramId));
      if (hit) await open(hit);
    }
  } catch (e) {
    notify(e.message, "error");
  } finally {
    loading.value = false;
  }
}

// 封面：只给前 8 个相册各取一张，避免相册一多就发一堆请求
async function loadCovers() {
  const picked = albums.value.slice(0, 8);
  const entries = await Promise.all(
    picked.map(async (a) => {
      try {
        const data = await api.albumImages(a.id, { limit: 1 });
        return [a.id, data.items?.[0]?.id || null];
      } catch {
        return [a.id, null];
      }
    }),
  );
  covers.value = Object.fromEntries(entries);
}

function buildQuery() {
  if (formMode.value === "json") {
    try {
      const parsed = JSON.parse(form.json || "{}");
      if (typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("必须是对象");
      return parsed;
    } catch (e) {
      notify(`query 不是合法 JSON 对象：${e.message}`, "warn");
      return null;
    }
  }
  const q = {};
  if (form.category) q.category = form.category;
  if (form.rating_min) q.rating_min = Number(form.rating_min);
  if (form.favorite) q.favorite = true;
  if (form.tags.length) q.tags = form.tags.join(",");
  if (form.dir_id) q.dir_id = Number(form.dir_id);
  return q;
}

async function save() {
  const query = buildQuery();
  if (query === null) return;
  if (!form.name.trim()) return notify("先给相册起个名字", "warn");
  try {
    if (form.id) {
      await api.patchAlbum(form.id, { name: form.name.trim(), query });
      notify("相册已更新（内部是删除重建，id 会变）", "ok");
    } else {
      await api.addAlbum({ name: form.name.trim(), query });
      notify("相册已创建，识别结果变了它会自动跟着变", "ok");
    }
    resetForm();
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

function editAlbum(a) {
  form.id = a.id;
  form.name = a.name;
  formMode.value = "json";
  form.json = JSON.stringify(a.query || {}, null, 2);
}

function resetForm() {
  form.id = null;
  form.name = "";
  form.category = "";
  form.rating_min = "";
  form.favorite = false;
  form.tags = [];
  form.dir_id = "";
  form.json = '{"category": "风景"}';
}

async function open(a) {
  active.value = a;
  loadingImages.value = true;
  images.value = [];
  cursor.value = null;
  selected.value = new Set();
  try {
    const data = await api.albumImages(a.id, { limit: 48 });
    images.value = data.items || [];
    cursor.value = data.next_cursor || null;
  } catch (e) {
    notify(e.message, "error");
  } finally {
    loadingImages.value = false;
  }
  if (String(route.params.id) !== String(a.id)) {
    router.replace(`/albums/${a.id}`);
  }
}

async function moreImages() {
  if (!cursor.value || !active.value) return;
  try {
    const data = await api.albumImages(active.value.id, { limit: 48, cursor: cursor.value });
    const seen = new Set(images.value.map((i) => i.id));
    images.value = [...images.value, ...(data.items || []).filter((i) => !seen.has(i.id))];
    cursor.value = data.next_cursor || null;
  } catch (e) {
    notify(e.message, "error");
  }
}

async function confirmDelete() {
  const a = askDelete.value;
  try {
    await api.deleteAlbum(a.id);
    notify(`相册「${a.name}」已删除`, "ok");
    askDelete.value = null;
    if (active.value?.id === a.id) {
      active.value = null;
      images.value = [];
      router.replace("/albums");
    }
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

const totalInAlbums = computed(() => albums.value.reduce((a, b) => a + (Number(b.count) || 0), 0));

watch(
  () => route.params.id,
  (id) => {
    if (!id && active.value) {
      active.value = null;
      images.value = [];
    }
  },
);

onMounted(async () => {
  await Promise.all([loadCatalog(), load()]);
  try {
    dirs.value = (await api.directories()).items || [];
  } catch {
    /* 目录拿不到不影响 */
  }
});
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>智能相册</h1>
        <div class="sub">{{ albums.length }} 个相册，合计 {{ num(totalInAlbums) }} 张命中</div>
      </div>
      <div class="head-actions">
        <button
          v-if="$route.params.id"
          class="btn btn-sm"
          @click="active = null; images = []; $router.replace('/albums')"
        >
          返回相册列表
        </button>
      </div>
    </div>

    <!-- 新建 / 编辑 -->
    <Panel :title="form.id ? `编辑相册「${form.name}」` : '新建相册'" collapsible :default-open="!albums.length">
      <template #actions>
        <div class="seg">
          <button :class="{ 'is-on': formMode === 'visual' }" @click="formMode = 'visual'">可视化</button>
          <button :class="{ 'is-on': formMode === 'json' }" @click="formMode = 'json'">JSON</button>
        </div>
      </template>

      <div class="stack-3">
        <input v-model="form.name" class="input" placeholder="相册名，如：海边的日落" />

        <template v-if="formMode === 'visual'">
          <div class="row" style="gap: 8px">
            <label class="field" style="flex: 1 1 150px">
              <span class="lab">分类</span>
              <select v-model="form.category" class="select">
                <option value="">不限</option>
                <option v-for="c in catalog.categories" :key="c.id" :value="c.name">{{ c.emoji }} {{ c.name }}</option>
              </select>
            </label>
            <label class="field" style="flex: 0 1 120px">
              <span class="lab">评分 ≥</span>
              <select v-model="form.rating_min" class="select">
                <option value="">不限</option>
                <option v-for="n in 5" :key="n" :value="n">{{ n }} 星</option>
              </select>
            </label>
            <label class="field" style="flex: 1 1 160px">
              <span class="lab">目录</span>
              <select v-model="form.dir_id" class="select">
                <option value="">不限</option>
                <option v-for="d in dirs" :key="d.id" :value="d.id">{{ d.path }}</option>
              </select>
            </label>
            <label class="lab-check" style="align-self: flex-end; padding-bottom: 6px">
              <input v-model="form.favorite" class="checkbox" type="checkbox" /> 仅收藏
            </label>
          </div>
          <div class="small dim">
            等价于 query：<code>{{ JSON.stringify(buildQuery() || {}) }}</code>
          </div>
        </template>

        <label v-else class="field">
          <span class="lab">query JSON</span>
          <textarea v-model="form.json" class="textarea mono" rows="4" placeholder='{"category": "风景", "rating_min": 4}' />
          <span class="hint">支持的键：q / category / tags / rating_min / favorite / dir_id / date_from / date_to / analysis_state / sort / order</span>
        </label>

        <div class="row">
          <button class="btn btn-primary" @click="save">{{ form.id ? "保存修改" : "创建相册" }}</button>
          <button v-if="form.id" class="btn" @click="resetForm">取消编辑</button>
        </div>
      </div>
    </Panel>

    <!-- 相册墙 -->
    <Panel title="相册列表" :count="albums.length">
      <Skeleton v-if="loading" variant="cards" :count="4" />
      <EmptyState
        v-else-if="!albums.length"
        compact
        icon="album"
        title="还没有相册"
        hint="相册是一段查询条件，不是一堆图片的外键表——AI 识别结果变了，相册内容会自动跟着变。"
      />
      <div v-else class="grid-media" style="--card-min: 240px">
        <article
          v-for="a in albums"
          :key="a.id"
          class="img-card"
          :class="{ 'is-selected': active?.id === a.id }"
          role="button"
          tabindex="0"
          @click="open(a)"
          @keyup.enter="open(a)"
        >
          <div class="thumb">
            <img v-if="covers[a.id]" :src="thumbUrl(covers[a.id])" :alt="a.name" loading="lazy" />
            <div v-else class="fallback">
              <Icon name="album" :size="22" />
              <div class="tiny dim" style="margin-top: 2px">暂无匹配封面</div>
            </div>
          </div>
          <div class="meta">
            <div class="row-between">
              <span class="name clamp-1">{{ a.name }}</span>
              <span class="tag tag-accent">{{ num(a.count) }}</span>
            </div>
            <div class="tiny dim clamp-2 mono">{{ JSON.stringify(a.query) }}</div>
            <div class="row" style="gap: 4px">
              <button class="btn btn-xs" @click.stop="open(a)">
                <Icon name="eye" :size="12" /> 查看
              </button>
              <button class="btn btn-xs" @click.stop="editAlbum(a)">编辑</button>
              <button class="btn btn-xs btn-danger" @click.stop="askDelete = a">删除</button>
            </div>
          </div>
        </article>
      </div>
    </Panel>

    <!-- 选中的相册内容 -->
    <template v-if="active">
      <div class="page-head">
        <div class="stack" style="gap: 3px">
          <h1>{{ active.name }}</h1>
          <div class="sub">
            命中 {{ images.length }} 张 · 条件
            <code class="mono small">{{ JSON.stringify(active.query) }}</code>
          </div>
        </div>
      </div>
      <ImageGrid
        :items="images"
        :loading="loadingImages"
        :loading-more="false"
        :has-more="Boolean(cursor)"
        :view="'grid'"
        :selected="selected"
        :selectable="false"
        :masked="privacyMode"
        empty-title="这个相册还没有匹配图片"
        empty-hint="识别完成后符合 query 的图会自动进来。"
        @open="(img) => (openId = img.id)"
        @load-more="moreImages"
      />
    </template>

    <ImageDrawer
      v-if="openId"
      v-model:image-id="openId"
      :ids="images.map((i) => i.id)"
      @close="openId = null"
    />

    <ConfirmDialog
      :open="Boolean(askDelete)"
      title="删除相册"
      :message="`删除「${askDelete?.name}」？`"
      :details="['相册只是一段查询条件，删掉它不会删除任何图片', '源文件与索引都不受影响']"
      confirm-text="确认删除"
      danger
      @close="askDelete = null"
      @confirm="confirmDelete"
    />
  </div>
</template>

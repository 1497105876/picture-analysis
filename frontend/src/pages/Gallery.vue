<script setup>
// 图库：登记目录、浏览、筛选、多选批量、导出、上传。
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, http } from "../app/api.js";
import { catalog, loadCatalog } from "../app/catalog.js";
import { notify } from "../app/toast.js";
import { useList } from "../app/useList.js";
import { privacyMode, defaultSort, defaultView, settings } from "../app/settings.js";
import { queue } from "../app/notices.js";
import { bytes, num, SORT_OPTIONS, datetime } from "../app/format.js";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import ImageDrawer from "../components/ImageDrawer.vue";
import ImageGrid from "../components/ImageGrid.vue";
import Panel from "../components/Panel.vue";

// ---------------------------------------------------------------- 列表
const route = useRoute();
const router = useRouter();
const filters = reactive({
  dir_id: "",
  category: "",
  analysis_state: "",
  rating_min: "",
  favorite: "",
  tags: "",
});
const sort = ref(defaultSort.value);
const order = ref("desc");
const dirs = ref([]);
const selected = ref(new Set());
const openId = ref(null);
const view = ref(defaultView.value);

const list = useList(api.images, { pageSize: 48 });
const ids = computed(() => list.items.value.map((i) => i.id));

function queryParams() {
  return {
    dir_id: filters.dir_id || undefined,
    category: filters.category || undefined,
    analysis_state: filters.analysis_state || undefined,
    rating_min: filters.rating_min || undefined,
    favorite: filters.favorite || undefined,
    tags: filters.tags || undefined,
    sort: sort.value,
    order: order.value,
  };
}

function reload() {
  selected.value = new Set();
  return list.reload(queryParams());
}

async function loadDirs() {
  try {
    dirs.value = (await api.directories()).items || [];
  } catch (e) {
    notify(e.message, "error");
  }
}

onMounted(async () => {
  // 支持从仪表盘点进来带筛选：/gallery?analysis_state=failed
  const q = route.query;
  if (q.analysis_state) filters.analysis_state = String(q.analysis_state);
  if (q.dir_id) filters.dir_id = String(q.dir_id);
  if (q.category) filters.category = String(q.category);
  await Promise.all([loadCatalog(), loadDirs()]);
  await reload();
  // 深链：/gallery?image=123 直接打开这张图的详情，刷新不丢
  if (q.image && ids.value.includes(Number(q.image))) openId.value = Number(q.image);
});

// 抽屉开合同步进 URL：刷新能留住，也能把某张图发给以后的自己
watch(openId, (v) => {
  const query = { ...route.query };
  if (v) query.image = String(v);
  else delete query.image;
  router.replace({ path: "/gallery", query });
});

// ---------------------------------------------------------------- 批量
const batchBusy = ref(false);
const exportOpen = ref(false);
const exportFormat = ref("json");

function toggleSelect(id) {
  const next = new Set(selected.value);
  next.has(id) ? next.delete(id) : next.add(id);
  selected.value = next;
}
function selectAll(list) {
  const next = new Set(selected.value);
  list.forEach((id) => next.add(id));
  selected.value = next;
}
function clearSelection() {
  selected.value = new Set();
}

const picked = computed(() => [...selected.value]);

async function runBatch(op, payload, label) {
  if (!picked.value.length) return notify("先选几张图", "warn");
  batchBusy.value = true;
  try {
    await api.batch(op, picked.value, payload);
    notify(`${label}完成（${picked.value.length} 张）`, "ok");
    await reload();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    batchBusy.value = false;
  }
}

const askDeleteBatch = ref(false);
function deleteBatch() {
  if (!picked.value.length) return notify("先选几张图", "warn");
  askDeleteBatch.value = true;
}
async function confirmDeleteBatch() {
  batchBusy.value = true;
  try {
    await api.batch("delete", picked.value);
    notify(`已删除 ${picked.value.length} 张的索引（源文件未动）`, "ok");
    askDeleteBatch.value = false;
    await reload();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    batchBusy.value = false;
  }
}

async function doExport() {
  batchBusy.value = true;
  try {
    const data = await api.exportImages(picked.value, exportFormat.value);
    notify(`已导出 ${data.count} 条到 ${data.path}`, "ok");
    exportOpen.value = false;
  } catch (e) {
    notify(e.message, "error");
  } finally {
    batchBusy.value = false;
  }
}

// ---------------------------------------------------------------- 目录
async function patchDir(d, patch, label) {
  try {
    const row = await api.patchDirectory(d.id, patch);
    Object.assign(d, row);
    if (label) notify(label, "ok");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function startScan(d) {
  try {
    const res = await api.scanDirectory(d.id);
    const excl = Number(res.excluded) || 0;
    notify(
      `扫描完成：新增 ${res.added ?? 0}、更新 ${res.updated ?? 0}、跳过 ${res.skipped ?? 0}、丢失 ${res.missing ?? 0}` +
        (excl ? `、已排除「仅移除索引」${excl} 张` : ""),
      "ok",
    );
    await Promise.all([loadDirs(), reload()]);
  } catch (e) {
    notify(e.message, "error");
  }
}

const askRemoveDir = ref(null);
async function confirmRemoveDir() {
  const d = askRemoveDir.value;
  try {
    await api.deleteDirectory(d.id);
    notify(`已注销「${d.path}」，源文件未动`, "ok");
    askRemoveDir.value = null;
    await Promise.all([loadDirs(), reload()]);
  } catch (e) {
    notify(e.message, "error");
  }
}

// ---------------------------------------------------------------- 登记向导
const wizard = reactive({ open: false, path: "", recursive: true, estimate: null, busy: false });

async function estimate() {
  if (!wizard.path.trim()) return;
  wizard.busy = true;
  wizard.estimate = null;
  try {
    const data = await api.estimateDirectory({ path: wizard.path.trim(), recursive: wizard.recursive });
    wizard.estimate = data.estimate;
  } catch (e) {
    notify(e.message, "error");
  } finally {
    wizard.busy = false;
  }
}

async function register() {
  wizard.busy = true;
  try {
    if (wizard.estimate?.registered_id) {
      await api.scanDirectory(wizard.estimate.registered_id);
      notify("该目录已登记，已执行增量扫描", "ok");
    } else {
      const data = await api.registerDirectory({
        path: wizard.path.trim(),
        recursive: wizard.recursive,
        estimate: wizard.estimate,
      });
      const s = data.scan || {};
      notify(
        `已登记并扫描：新增 ${s.added ?? 0}、更新 ${s.updated ?? 0}、跳过 ${s.skipped ?? 0}、丢失 ${s.missing ?? 0}`,
        "ok",
      );
    }
    wizard.open = false;
    wizard.path = "";
    wizard.estimate = null;
    await Promise.all([loadDirs(), reload()]);
  } catch (e) {
    if (e.status === 409) {
      const hit = dirs.value.find((d) => d.path === wizard.path.trim());
      if (hit) {
        await api.scanDirectory(hit.id);
        notify("该目录已登记，已执行增量扫描", "ok");
        wizard.open = false;
        wizard.estimate = null;
        await Promise.all([loadDirs(), reload()]);
        return;
      }
    }
    notify(e.message, "error");
  } finally {
    wizard.busy = false;
  }
}

// ---------------------------------------------------------------- 上传
const picking = ref(false);
const dragOver = ref(false);
const uploadResult = reactive({ done: 0, failed: 0 });

async function uploadFiles(files) {
  if (!files?.length) return;
  picking.value = true;
  uploadResult.done = 0;
  uploadResult.failed = 0;
  for (const f of files) {
    try {
      await http.upload(f);
      uploadResult.done += 1;
    } catch (e) {
      uploadResult.failed += 1;
      notify(`${f.name}：${e.message}`, "error");
    }
  }
  picking.value = false;
  notify(`上传完成：成功 ${uploadResult.done}${uploadResult.failed ? `、失败 ${uploadResult.failed}` : ""}`, uploadResult.failed ? "warn" : "ok");
  await Promise.all([loadDirs(), reload()]);
}

function onPick(e) {
  uploadFiles([...e.target.files]);
  e.target.value = "";
}
function onDrop(e) {
  dragOver.value = false;
  uploadFiles([...(e.dataTransfer?.files || [])]);
}

const hasFilter = computed(() =>
  Boolean(filters.dir_id || filters.category || filters.analysis_state || filters.rating_min || filters.favorite || filters.tags),
);
function clearFilters() {
  Object.assign(filters, { dir_id: "", category: "", analysis_state: "", rating_min: "", favorite: "", tags: "" });
  reload();
}

const totalBytes = computed(() => list.items.value.reduce((a, b) => a + (Number(b.bytes) || 0), 0));

// 「照片进来了却一直不识别」时给一句话解释。
// 新手不会想到去任务页看，这里不说，他只会以为功能坏了。
const aiHint = computed(() => {
  if (!settings.loaded || !list.items.value.length) return null;
  const waiting = list.items.value.filter((i) => i.analysis_state !== "done").length;
  if (!waiting) return null;
  if (!(settings.profiles || []).length) {
    return {
      tone: "warn",
      title: `${waiting} 张已入库，但还没配置 AI 服务，识别不会开始`,
      detail: "识别、向量检索、以图搜图都需要先配一个服务档案（云端或本地 Ollama 都行）。",
      actionLabel: "去配置档案",
      to: "/settings",
    };
  }
  if (queue.paused) {
    return {
      tone: "info",
      title: `识别队列已暂停：${queue.reason || "等待恢复"}`,
      detail: "暂停期间不会消耗任何 API 调用，恢复后自动继续排队。",
      actionLabel: "看任务队列",
      to: "/jobs",
    };
  }
  return null;
});
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>图库</h1>
        <div class="sub">
          已索引 {{ list.items.value.length }} 张<span v-if="list.cursor.value">，滚动可继续加载</span>
          <template v-if="list.items.value.length"> · 本页 {{ bytes(totalBytes) }}</template>
        </div>
      </div>
      <div class="head-actions">
        <button class="btn" @click="wizard.open = true">
          <Icon name="folder" :size="14" /> 登记目录
        </button>
        <label class="btn btn-primary">
          <Icon name="upload" :size="14" /> 上传图片
          <input type="file" accept="image/*" multiple hidden @change="onPick" />
        </label>
      </div>
    </div>

    <!-- 照片进来了却不识别时，必须有一句话解释原因 -->
    <div v-if="aiHint" class="banner" :class="aiHint.tone === 'warn' ? 'banner-warn' : ''">
      <Icon :name="aiHint.tone === 'warn' ? 'warning' : 'info'" :size="16" style="margin-top: 2px" />
      <div class="stack" style="gap: 3px; min-width: 0">
        <div class="strong">{{ aiHint.title }}</div>
        <div class="small">{{ aiHint.detail }}</div>
      </div>
      <router-link class="btn btn-sm" style="margin-left: auto" :to="aiHint.to">
        {{ aiHint.actionLabel }}
      </router-link>
    </div>

    <!-- 已登记目录 -->
    <Panel
      title="已登记目录"
      :count="dirs.length"
      subtitle="只扫登记过的路径；未登记目录一概不碰"
      collapsible
      :default-open="true"
    >
      <template #actions>
        <button class="btn btn-sm" @click="wizard.open = true">新增登记</button>
      </template>

      <EmptyState
        v-if="!dirs.length"
        compact
        icon="folder"
        title="还没有登记任何目录"
        hint="登记目录是这个库的开关：不登记就不会扫，也不会有任何一张图被送去做 AI 识别。"
      >
        <template #action>
          <button class="btn btn-primary btn-sm" @click="wizard.open = true">登记第一个目录</button>
        </template>
      </EmptyState>

      <div v-else class="stack-3">
        <div v-for="d in dirs" :key="d.id" class="dir-row">
          <div class="stack" style="gap: 4px; min-width: 0">
            <div class="row" style="gap: 6px">
              <Icon name="folder" :size="14" class="dim" />
              <span class="mono strong wrap-anywhere">{{ d.path }}</span>
            </div>
            <div class="row small" style="gap: 6px">
              <span class="tag tag-outline">#{{ d.id }}</span>
              <span class="tag tag-accent">{{ num(d.image_count) }} 张</span>
              <span v-if="d.hidden_count" class="tag tag-danger">{{ d.hidden_count }} 张隐藏</span>
              <span v-if="d.source !== 'manual'" class="tag tag-outline">来源 {{ d.source }}</span>
              <span class="dim">最后扫描 {{ datetime(d.last_scanned_at) || "从未" }}</span>
            </div>
            <div class="row small" style="gap: 10px; margin-top: 2px">
              <label class="lab-check">
                <input class="checkbox" type="checkbox" :checked="Boolean(d.recursive)" @change="patchDir(d, { recursive: !d.recursive })" />
                递归
              </label>
              <label class="lab-check">
                <input class="checkbox" type="checkbox" :checked="Boolean(d.enabled)" @change="patchDir(d, { enabled: !d.enabled })" />
                启用
              </label>
              <label class="lab-check" title="离线盘：盘不在时不标丢失">
                <input class="checkbox" type="checkbox" :checked="Boolean(d.offline)" @change="patchDir(d, { offline: !d.offline })" />
                离线盘
              </label>
              <label class="lab-check" title="隐私目录：不送云端识别">
                <input class="checkbox" type="checkbox" :checked="Boolean(d.privacy)" @change="patchDir(d, { privacy: !d.privacy })" />
                隐私
              </label>
              <label class="lab-check" title="冻结：扫描只更新已有记录，不收录新图">
                <input class="checkbox" type="checkbox" :checked="Boolean(d.frozen)" @change="patchDir(d, { frozen: !d.frozen })" />
                冻结
              </label>
              <label class="field field-inline" style="gap: 4px">
                <span class="tiny dim">OCR</span>
                <select
                  class="select select-sm"
                  style="width: 84px"
                  :value="d.ocr_policy"
                  @change="patchDir(d, { ocr_policy: $event.target.value })"
                >
                  <option value="auto">auto</option>
                  <option value="on">强制</option>
                  <option value="off">关闭</option>
                </select>
              </label>
            </div>
          </div>

          <div class="row" style="gap: 6px; flex: none">
            <button
              class="btn btn-sm"
              :class="d.watcher ? 'btn-primary' : ''"
              :title="d.watcher ? '自动：30 秒轮询增量扫描' : '手动：只在点「增量扫描」时更新'"
              @click="patchDir(d, { watcher: !d.watcher }, d.watcher ? '已切换为手动模式' : '已开启自动跟踪（需在设置 G4 打开全局开关）')"
            >
              {{ d.watcher ? "自动跟踪" : "手动" }}
            </button>
            <button class="btn btn-sm" @click="startScan(d)">
              <Icon name="refresh" :size="13" /> 增量扫描
            </button>
            <button class="btn btn-sm btn-danger" @click="askRemoveDir = d">注销</button>
          </div>
        </div>
      </div>
    </Panel>

    <!-- 筛选 -->
    <Panel flush>
      <div class="row" style="padding: 12px var(--panel-pad); gap: 8px">
        <select v-model="filters.dir_id" class="select select-sm" style="width: 168px" @change="reload">
          <option value="">全部目录</option>
          <option v-for="d in dirs" :key="d.id" :value="d.id">{{ d.path }}</option>
        </select>
        <select v-model="filters.category" class="select select-sm" style="width: 132px" @change="reload">
          <option value="">全部分类</option>
          <option v-for="c in catalog.categories" :key="c.id" :value="c.name">{{ c.emoji }} {{ c.name }}</option>
        </select>
        <select v-model="filters.analysis_state" class="select select-sm" style="width: 132px" @change="reload">
          <option value="">全部状态</option>
          <option value="unanalyzed">未识别</option>
          <option value="done">已识别</option>
          <option value="failed">识别失败</option>
          <option value="skipped">跳过</option>
          <option value="queued">排队中</option>
          <option value="running">识别中</option>
        </select>
        <select v-model="filters.rating_min" class="select select-sm" style="width: 116px" @change="reload">
          <option value="">任意评分</option>
          <option v-for="n in 5" :key="n" :value="n">{{ n }} 星以上</option>
        </select>
        <select v-model="filters.favorite" class="select select-sm" style="width: 104px" @change="reload">
          <option value="">收藏不限</option>
          <option value="true">仅收藏</option>
          <option value="false">未收藏</option>
        </select>
        <input
          v-model="filters.tags"
          class="input input-sm"
          style="width: 132px"
          placeholder="标签过滤"
          @keyup.enter="reload"
        />
        <span class="spacer"></span>
        <button v-if="hasFilter" class="btn btn-xs" @click="clearFilters">清空筛选</button>
      </div>

      <div class="row-between" style="padding: 0 var(--panel-pad) 12px; border-top: 1px solid var(--line); padding-top: 10px">
        <div class="row" style="gap: 6px">
          <select v-model="sort" class="select select-sm" style="width: 120px" @change="reload">
            <option v-for="s in SORT_OPTIONS" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>
          <div class="seg">
            <button :class="{ 'is-on': order === 'desc' }" title="降序" @click="order = 'desc'; reload()">
              ↓ 新在前
            </button>
            <button :class="{ 'is-on': order === 'asc' }" title="升序" @click="order = 'asc'; reload()">
              ↑ 旧在前
            </button>
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

        <div class="row" style="gap: 6px">
          <span class="small dim">{{ list.loading.value ? "加载中…" : `${picked.length} 张待操作` }}</span>
          <button class="btn btn-sm" :disabled="!picked.length || batchBusy" @click="runBatch('patch', { favorite: 1 }, '批量收藏')">
            <Icon name="star" :size="13" /> 收藏
          </button>
          <button class="btn btn-sm" :disabled="!picked.length || batchBusy" @click="exportOpen = true">
            <Icon name="download" :size="13" /> 导出
          </button>
          <button class="btn btn-sm" :disabled="!picked.length || batchBusy" @click="runBatch('hide', {}, '批量移入隐藏区')">
            <Icon name="eye-off" :size="13" /> 隐藏
          </button>
          <button class="btn btn-sm btn-danger" :disabled="!picked.length || batchBusy" @click="deleteBatch">
            <Icon name="trash" :size="13" /> 删索引
          </button>
        </div>
      </div>
    </Panel>

    <!-- 内容 -->
    <div
      class="dropzone-target"
      :class="{ 'is-over': dragOver }"
      @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false"
      @drop.prevent="onDrop"
    >
      <ImageGrid
        :items="list.items.value"
        :loading="list.loading.value"
        :loading-more="list.loadingMore.value"
        :has-more="Boolean(list.cursor.value)"
        :error="list.error.value"
        :view="view"
        :selected="selected"
        :masked="privacyMode"
        empty-title="还没有图片"
        empty-hint="登记一个目录，或者把图拖到这里上传。"
        @open="(img) => (openId = img.id)"
        @toggle="toggleSelect"
        @select-all="selectAll"
        @clear-selection="clearSelection"
        @load-more="list.more(queryParams())"
      >
        <template #toolbar>
          <span class="small dim">
            {{ list.items.value.length }} 张
            <template v-if="hasFilter">· 已筛选</template>
          </span>
        </template>
        <template #empty>
          <div class="row" style="justify-content: center">
            <button class="btn btn-primary btn-sm" @click="wizard.open = true">登记目录</button>
          </div>
        </template>
      </ImageGrid>
      <div v-if="dragOver" class="drop-hint">松开即可上传到 data/uploads</div>
    </div>

    <!-- 详情抽屉 -->
    <ImageDrawer
      v-if="openId"
      v-model:image-id="openId"
      :ids="ids"
      :dirs="dirs"
      @close="openId = null"
      @changed="reload"
    />

    <!-- 登记向导 -->
    <Teleport to="body">
      <div v-if="wizard.open" class="mask" @click="wizard.open = false"></div>
      <div v-if="wizard.open" class="modal">
        <div class="modal-box modal-lg">
          <div class="modal-head">
            <h3>登记目录</h3>
            <div class="panel-sub">
              两步走：先估数（不写库不调用 AI），确认后再落库扫描。未登记的路径永远不会被碰。
            </div>
          </div>
          <div class="modal-body stack-3">
            <label class="field">
              <span class="lab">目录绝对路径</span>
              <input v-model="wizard.path" class="input mono" placeholder="如 D:\Photos 或 Z:\good\shishi" />
              <span class="hint">
                网页拿不到文件夹选择器（浏览器的安全限制），请在资源管理器地址栏复制路径后粘贴到这里，
                例如 <code>D:\Photos</code>；也可以直接把文件夹拖到图库页面上传。
              </span>
            </label>
            <label class="lab-check">
              <input v-model="wizard.recursive" class="checkbox" type="checkbox" /> 递归子目录
            </label>

            <div v-if="wizard.estimate" class="panel-inset stack-3">
              <div class="row" style="gap: 6px">
                <span class="tag" :class="wizard.estimate.within_budget ? 'tag-ok' : 'tag-warn'">
                  {{ wizard.estimate.within_budget ? "在日预算内" : "超出今日预算" }}
                </span>
                <span v-if="wizard.estimate.registered_id" class="tag tag-accent">该目录已登记</span>
              </div>
              <dl class="kv">
                <dt>发现文件</dt>
                <dd>{{ num(wizard.estimate.count) }} 个 · {{ bytes(wizard.estimate.bytes) }}</dd>
                <dt>预计耗时</dt>
                <dd>约 {{ wizard.estimate.est_minutes }} 分钟</dd>
                <dt>预计 token</dt>
                <dd>
                  {{ num(wizard.estimate.est_tokens) }}
                  <span v-if="wizard.estimate.tokens_left !== null">（今日剩余 {{ num(wizard.estimate.tokens_left) }}）</span>
                  <span v-else>（未设上限）</span>
                </dd>
              </dl>
              <div v-if="wizard.estimate.overlap" class="small warn-text">{{ wizard.estimate.overlap }}</div>
              <ul class="small muted" style="margin: 0; padding-left: 18px">
                <li v-for="p in wizard.estimate.phases" :key="p">{{ p }}</li>
              </ul>
            </div>
          </div>
          <div class="modal-foot">
            <button class="btn" @click="wizard.open = false">取消</button>
            <button class="btn" :disabled="!wizard.path.trim() || wizard.busy" @click="estimate">
              <span v-if="wizard.busy" class="spin"></span>
              第一步：估算
            </button>
            <button
              class="btn btn-primary"
              :disabled="!wizard.estimate || wizard.busy"
              @click="register"
            >
              {{ wizard.estimate?.registered_id ? "第二步：增量扫描" : "第二步：确认登记" }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 导出选择 -->
    <Teleport to="body">
      <div v-if="exportOpen" class="mask" @click="exportOpen = false"></div>
      <div v-if="exportOpen" class="modal">
        <div class="modal-box modal-sm">
          <div class="modal-head"><h3>导出元数据</h3></div>
          <div class="modal-body stack-3">
            <div class="small muted">导出 {{ picked.length }} 张图的元数据到 data/exports。</div>
            <label class="field">
              <span class="lab">格式</span>
              <select v-model="exportFormat" class="select">
                <option value="json">JSON（含全部字段与识别历史）</option>
                <option value="csv">CSV（精简表：id/路径/分类/描述/评分/标签）</option>
              </select>
            </label>
            <div class="banner">
              <Icon name="info" :size="14" style="margin-top: 2px" />
              <span class="small">
                若设置里开着 G15「导出剥离 EXIF」，会额外复制一份去掉 EXIF 的原图到 images- 目录。
              </span>
            </div>
          </div>
          <div class="modal-foot">
            <button class="btn" @click="exportOpen = false">取消</button>
            <button class="btn btn-primary" :disabled="batchBusy" @click="doExport">开始导出</button>
          </div>
        </div>
      </div>
    </Teleport>

    <ConfirmDialog
      :open="Boolean(askRemoveDir)"
      title="注销目录"
      :message="`注销「${askRemoveDir?.path}」后，该目录下所有图片的索引会被移除。`"
      :details="['源文件一律不动', '可以重新登记把它找回来', '已登记为「仅移除索引」的文件在重新登记后仍不会自动回来']"
      confirm-text="确认注销"
      danger
      :busy="batchBusy"
      @close="askRemoveDir = null"
      @confirm="confirmRemoveDir"
    />

    <ConfirmDialog
      :open="askDeleteBatch"
      title="批量删除索引"
      :message="`将删除选中的 ${picked.length} 张图的索引记录。`"
      :details="['源文件不会被删除', '删除后该路径会被登记为「仅移除索引」，增量扫描不再收录']"
      confirm-text="确认删除"
      danger
      :busy="batchBusy"
      @close="askDeleteBatch = false"
      @confirm="confirmDeleteBatch"
    />
  </div>
</template>

<style scoped>
.dir-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface-inset);
}
.dir-row + .dir-row {
  margin-top: 8px;
}
.dropzone-target {
  position: relative;
  min-height: 200px;
}
.dropzone-target.is-over {
  outline: 2px dashed var(--accent);
  outline-offset: 6px;
  border-radius: var(--radius);
}
.drop-hint {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: var(--accent-soft);
  border-radius: var(--radius);
  color: var(--accent-text);
  font-weight: 600;
  pointer-events: none;
}
.warn-text {
  color: var(--warn);
}
@media (max-width: 900px) {
  .dir-row {
    flex-direction: column;
  }
}
</style>

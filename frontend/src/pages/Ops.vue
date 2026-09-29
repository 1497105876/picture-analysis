<script setup>
// 运维：健康状态、通知中心、日志查看器、存储、SQLite 直读契约、危险操作。
// 这一页把「后端有、界面没有」的运维能力集中补齐。
import { computed, onMounted, ref } from "vue";

import { api } from "../app/api.js";
import { backend, loadNotices, notices, clearNotices } from "../app/notices.js";
import { notify } from "../app/toast.js";
import { bytes, datetime, megabytes, noticeKind, num } from "../app/format.js";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import Panel from "../components/Panel.vue";
import StatCard from "../components/StatCard.vue";

const logs = ref([]);
const logLevel = ref("");
const logLines = ref(200);
const logLoading = ref(false);
const kindFilter = ref("");
const askClearIndex = ref(false);
const busy = ref(false);

const DB_PATH_HINT = "data/library.db";

const DIRECT_READ_SQL = `-- 只读打开（Python）
import sqlite3
conn = sqlite3.connect("file:${DB_PATH_HINT}?mode=ro", uri=True)

-- 基本列表：category/description 已按人工优先合并
SELECT id, path, category, category_source, description, rating, favorite
FROM v_images ORDER BY mtime DESC LIMIT 50;

-- 关键词检索（FTS5，中文已 jieba 预分词）
SELECT v.id, v.path, v.description
FROM image_fts f JOIN v_images v ON v.id = f.image_id
WHERE image_fts MATCH '傍晚 海岸' ORDER BY rank LIMIT 20;

-- 某张图的识别内容：AI 标签 / 元素 / OCR
SELECT category, description, ai_tags, elements, ocr_text, has_text
FROM v_analysis WHERE image_id = ?;

-- 标签合并视图（人工与 AI 按 source 区分）
SELECT tag, source FROM v_tags WHERE image_id = ?;

-- 启用中的资料库实体
SELECT id, name, category, description FROM v_entities;`;

const VIEW_LIST = [
  ["v_images", "可见图片主视图（分类/描述已 COALESCE 人工优先，带 category_source）"],
  ["v_analysis", "识别结果视图（AI 标签、元素、OCR 文本）"],
  ["v_tags", "标签合并视图（人工 / AI 按 source 区分）"],
  ["v_entities", "启用的资料库实体"],
  ["v_directories", "登记目录清单"],
  ["images / hidden_images", "原始表；隐藏区单独成表，不在任何视图里"],
];

const filtered = computed(() =>
  kindFilter.value ? notices.items.filter((n) => n.kind === kindFilter.value) : notices.items,
);
const kinds = computed(() => [...new Set(notices.items.map((n) => n.kind))].filter(Boolean));

async function loadLogs() {
  logLoading.value = true;
  try {
    const data = await api.logs(logLines.value);
    logs.value = data.lines || [];
    logLevel.value = data.level || "";
  } catch (e) {
    notify(e.message, "error");
  } finally {
    logLoading.value = false;
  }
}

async function copySql() {
  try {
    await navigator.clipboard.writeText(DIRECT_READ_SQL);
    notify("示例 SQL 已复制", "ok");
  } catch {
    notify("复制失败，请手动选择文本", "warn");
  }
}

async function onClearNotices() {
  try {
    await clearNotices();
    notify("通知已清空", "ok");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function clearIndex() {
  busy.value = true;
  try {
    const res = await api.clearIndex();
    notify(`索引已清空：移除 ${res.removed} 条记录，源文件一律未动`, "ok");
    askClearIndex.value = false;
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

async function clearJobs() {
  try {
    const res = await api.clearJobs();
    notify(`已清理 ${res.cleared} 个已完成任务`, "ok");
  } catch (e) {
    notify(e.message, "error");
  }
}

const sys = ref(null);
const cleanup = ref(null);

onMounted(async () => {
  await Promise.all([loadLogs(), loadNotices(200)]);
  try {
    sys.value = await api.systemStats();
    cleanup.value = await api.cleanup();
  } catch {
    /* 单独失败不影响页面其余部分 */
  }
});
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>运维</h1>
        <div class="sub">服务状态、通知、日志、存储与直读契约</div>
      </div>
      <div class="head-actions">
        <button class="btn btn-sm" @click="loadLogs"><Icon name="refresh" :size="13" /> 刷新日志</button>
      </div>
    </div>

    <!-- 健康 -->
    <div class="stat-grid">
      <StatCard
        :value="backend.online ? '在线' : '离线'"
        label="后端服务"
        :tone="backend.online ? 'ok' : 'danger'"
        icon="cpu"
        :footer="backend.version ? `版本 ${backend.version}` : ''"
      />
      <StatCard :value="num(notices.items.length)" label="站内通知" icon="bell" />
      <StatCard :value="megabytes(sys?.db_bytes)" label="索引体积" icon="database" />
      <StatCard :value="bytes(sys?.free_bytes)" label="磁盘可用" icon="save" :footer="`总容量 ${bytes(sys?.total_bytes)}`" />
      <StatCard :value="num(cleanup?.missing_files)" label="丢失文件" :tone="cleanup?.missing_files ? 'warn' : ''" icon="warning" />
      <StatCard :value="num(cleanup?.orphan_thumbs)" label="孤儿缩略图" :tone="cleanup?.orphan_thumbs ? 'warn' : ''" icon="image" />
    </div>

    <!-- 通知中心 -->
    <Panel title="通知中心" :count="notices.items.length" subtitle="识别纠错、扫描跳过、自动导入等事件的记录">
      <template #actions>
        <select v-model="kindFilter" class="select select-sm" style="width: 140px">
          <option value="">全部类型</option>
          <option v-for="k in kinds" :key="k" :value="k">{{ noticeKind(k) }}</option>
        </select>
        <button class="btn btn-xs" :disabled="!notices.items.length" @click="onClearNotices">清空</button>
        <button class="btn btn-xs" @click="loadNotices(200)"><Icon name="refresh" :size="12" /></button>
      </template>

      <EmptyState v-if="!filtered.length" compact icon="bell" title="没有通知" hint="识别纠错、扫描跳过、自动导入都会在这里留痕。" />
      <div v-else style="border: 1px solid var(--line); border-radius: var(--radius-sm); overflow: hidden">
        <div v-for="n in filtered" :key="n.id" class="notice-item" :class="`lv-${n.level}`">
          <span class="pin"></span>
          <div class="stack" style="gap: 2px; min-width: 0; flex: 1">
            <div class="wrap-anywhere">{{ n.message }}</div>
            <div class="tiny dim">{{ noticeKind(n.kind) }} · {{ n.level }} · {{ datetime(n.created_at) }}</div>
          </div>
        </div>
      </div>
    </Panel>

    <!-- 日志 -->
    <Panel title="日志查看器" :count="logs.length" :subtitle="`当前级别 ${logLevel || '—'} · 文件 data/logs/app.log`">
      <template #actions>
        <select v-model.number="logLines" class="select select-sm" style="width: 108px" @change="loadLogs">
          <option :value="100">最近 100 行</option>
          <option :value="200">最近 200 行</option>
          <option :value="500">最近 500 行</option>
          <option :value="2000">最近 2000 行</option>
        </select>
        <button class="btn btn-xs" :disabled="logLoading" @click="loadLogs">
          <Icon name="refresh" :size="12" /> 重新读取
        </button>
      </template>

      <pre v-if="logs.length" class="logview">{{ logs.join("\n") }}</pre>
      <EmptyState
        v-else
        compact
        icon="terminal"
        title="还没有日志内容"
        hint="日志只在服务真正写入时才产生；把 G7 的日志级别调到 DEBUG 可以看得更细。"
      />
    </Panel>

    <!-- 直读契约 -->
    <Panel title="SQLite 直读契约" subtitle="对本机 Agent 而言，这个库文件才是真正的对外接口">
      <div class="stack-3">
        <div class="banner">
          <Icon name="database" :size="16" style="margin-top: 2px" />
          <div class="stack" style="gap: 2px">
            <div class="strong">只读打开，别写</div>
            <div class="small">
              库文件路径 <code>{{ DB_PATH_HINT }}</code>（默认数据目录；设置
              <code>PA_DATA_DIR</code> 环境变量可改）。隐藏图片不在任何视图里，也没有参数能绕过。
            </div>
          </div>
        </div>

        <div class="table-wrap">
          <table class="table">
            <thead><tr><th style="width: 220px">对象</th><th>用途</th></tr></thead>
            <tbody>
              <tr v-for="row in VIEW_LIST" :key="row[0]">
                <td class="mono small">{{ row[0] }}</td>
                <td class="small">{{ row[1] }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="row-between">
          <span class="small dim">示例：连上就能查</span>
          <button class="btn btn-xs" @click="copySql"><Icon name="copy" :size="12" /> 复制</button>
        </div>
        <pre class="codeblock">{{ DIRECT_READ_SQL }}</pre>

        <div class="row small dim" style="gap: 8px">
          <a href="/api/docs" target="_blank" rel="noreferrer" class="row" style="gap: 4px">
            <Icon name="external" :size="13" /> OpenAPI 文档
          </a>
          <a href="/api/health" target="_blank" rel="noreferrer" class="row" style="gap: 4px">
            <Icon name="external" :size="13" /> 健康检查
          </a>
        </div>
      </div>
    </Panel>

    <!-- 危险操作 -->
    <Panel title="危险操作" danger>
      <div class="stack-3">
        <div class="row">
          <button class="btn btn-sm" @click="clearJobs">
            <Icon name="trash" :size="13" /> 清理已完成的任务
          </button>
          <span class="small dim">只清任务记录，不动图片与文件</span>
        </div>
        <hr />
        <div class="row">
          <button class="btn btn-sm btn-danger" @click="askClearIndex = true">
            <Icon name="warning" :size="13" /> 清空索引
          </button>
          <span class="small dim">
            删除所有目录的图片记录与任务，源文件一律不动；需要输入「清空索引」确认。
          </span>
        </div>
      </div>
    </Panel>

    <ConfirmDialog
      :open="askClearIndex"
      title="清空索引"
      message="所有登记目录的图片索引记录与任务会被删除，库会回到空状态。"
      :details="['源文件一律不动', '这张表里的识别结果、标签、OCR 全部清除', '可以重新扫描目录把索引建回来，但会重新消耗 AI 调用']"
      confirm-word="清空索引"
      confirm-text="确认清空"
      danger
      :busy="busy"
      @close="askClearIndex = false"
      @confirm="clearIndex"
    />
  </div>
</template>

<script setup>
// 仪表盘：库的整体体检报告。所有区块的数据都来自后端现成的统计端点，比例按真实最大值算。
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { api } from "../app/api.js";
import { notify } from "../app/toast.js";
import { bytes, num, percent, datetime, megabytes } from "../app/format.js";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import ImageDrawer from "../components/ImageDrawer.vue";
import Panel from "../components/Panel.vue";
import Skeleton from "../components/Skeleton.vue";
import StatCard from "../components/StatCard.vue";

const router = useRouter();

const dash = ref(null);
const sys = ref(null);
const cleanup = ref(null);
const dups = ref([]);
const loading = ref(true);
const dupLoading = ref(false);
const perceptual = ref(0);
const threshold = ref(6);
const askPerceptual = ref(false);
const trashConfirm = ref("");
const openId = ref(null);

const states = computed(() => dash.value?.analysis_states || {});
const maxCategory = computed(() =>
  Math.max(1, ...(dash.value?.by_category || []).map((r) => Number(r.count) || 0)),
);
const monthly = computed(() => [...(dash.value?.monthly || [])].reverse());
const maxMonth = computed(() => Math.max(1, ...monthly.value.map((r) => Number(r.count) || 0)));
const storage = computed(() => dash.value?.storage || []);
const maxStorage = computed(() => Math.max(1, ...storage.value.map((r) => Number(r.bytes) || 0)));
const openIdList = computed(() => dups.value.flatMap((g) => g.images.map((i) => i.id)));

async function load() {
  loading.value = true;
  try {
    const [d, s, c] = await Promise.all([api.dashboard(), api.systemStats(), api.cleanup()]);
    dash.value = d;
    sys.value = s;
    cleanup.value = c;
    await loadDups();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    loading.value = false;
  }
}

async function loadDups() {
  dupLoading.value = true;
  try {
    const data = await api.duplicates(perceptual.value, threshold.value);
    dups.value = data.groups || [];
  } catch (e) {
    notify(e.message, "error");
    dups.value = [];
  } finally {
    dupLoading.value = false;
  }
}

function onModeChange() {
  if (perceptual.value) {
    askPerceptual.value = true;
    return;
  }
  loadDups();
}

async function confirmPerceptual() {
  askPerceptual.value = false;
  await loadDups();
}

function cancelPerceptual() {
  perceptual.value = 0;
  askPerceptual.value = false;
}

async function clearTrash() {
  try {
    const res = await api.clearTrash();
    notify(`回收站已清空，删除 ${res.removed} 个文件`, "ok");
    trashConfirm.value = "";
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function restore(t) {
  try {
    await api.restoreTrash(t.id);
    notify("已恢复到原路径并重新扫描", "ok");
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

function goto(state) {
  router.push({ path: "/gallery", query: state ? { analysis_state: state } : {} });
}

onMounted(load);
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>仪表盘</h1>
        <div class="sub">索引规模、识别进度、重复与清理建议</div>
      </div>
      <div class="head-actions">
        <button class="btn btn-sm" :disabled="loading" @click="load">
          <Icon name="refresh" :size="13" /> 刷新
        </button>
      </div>
    </div>

    <Skeleton v-if="loading && !dash" variant="stats" :count="8" />

    <template v-else>
      <!-- 总览 -->
      <div class="stat-grid">
        <StatCard
          :value="num(dash?.total)"
          label="已索引图片"
          icon="image"
          clickable
          @click="goto('')"
        />
        <StatCard :value="num(dash?.hidden)" label="隐藏区" tone="warn" icon="eye-off" clickable @click="router.push('/hidden')" />
        <StatCard :value="num(states.done)" label="已识别" tone="ok" icon="check" clickable @click="goto('done')" />
        <StatCard
          :value="num((states.queued || 0) + (states.pending || 0) + (states.unanalyzed || 0) + (states.running || 0))"
          label="待处理 / 识别中"
          tone="accent"
          icon="task"
          clickable
          @click="goto('unanalyzed')"
        />
        <StatCard :value="num(states.failed)" label="识别失败" tone="danger" icon="warning" clickable @click="goto('failed')" />
        <StatCard :value="num(states.skipped)" label="跳过（超大图/隐私）" icon="minus" clickable @click="goto('skipped')" />
        <StatCard :value="num(dash?.tokens_total)" label="累计 token" icon="sparkle" footer="G3/G13 可设每日上限" />
        <StatCard :value="num(dash?.dirs)" label="登记目录" icon="folder" clickable @click="router.push('/gallery')" />
        <StatCard :value="megabytes(sys?.db_bytes)" label="索引体积" icon="database" :footer="`可用磁盘 ${bytes(sys?.free_bytes)}`" />
      </div>

      <!-- 分布 -->
      <div class="two-col">
        <Panel title="分类分布" :count="(dash?.by_category || []).length">
          <div v-for="row in dash?.by_category || []" :key="row.category" class="bar-row">
            <span class="clamp-1" :title="row.category">{{ row.category }}</span>
            <div class="bar"><i :style="{ width: `${((row.count / maxCategory) * 100).toFixed(1)}%` }"></i></div>
            <span class="v">{{ num(row.count) }}</span>
          </div>
          <EmptyState v-if="!(dash?.by_category || []).length" compact icon="tag" title="还没有分类数据" />
        </Panel>

        <Panel title="按月分布" :count="monthly.length" subtitle="优先用 EXIF 拍摄时间，缺失时回退入库时间">
          <div v-for="row in monthly" :key="row.month" class="bar-row">
            <span class="mono">{{ row.month }}</span>
            <div class="bar"><i :style="{ width: `${((row.count / maxMonth) * 100).toFixed(1)}%` }"></i></div>
            <span class="v">{{ num(row.count) }}</span>
          </div>
          <EmptyState v-if="!monthly.length" compact icon="calendar" title="还没有时间分布数据" />
        </Panel>
      </div>

      <!-- 目录占用 -->
      <Panel title="目录占用" :count="storage.length" subtitle="按实际文件字节数排序">
        <template #actions>
          <span class="small dim">合计 {{ bytes(storage.reduce((a, b) => a + Number(b.bytes || 0), 0)) }}</span>
        </template>
        <div v-for="row in storage" :key="row.dir_id" class="bar-row" style="grid-template-columns: 1fr 220px 96px">
          <span class="mono clamp-1 wrap-anywhere" :title="row.path">{{ row.path }}</span>
          <div class="bar"><i :style="{ width: `${((row.bytes / maxStorage) * 100).toFixed(1)}%` }"></i></div>
          <span class="v">{{ bytes(row.bytes) }} · {{ row.count }}</span>
        </div>
        <EmptyState v-if="!storage.length" compact icon="folder" title="还没有登记目录" />
      </Panel>

      <!-- 重复 -->
      <Panel title="重复检测" :count="dups.length" subtitle="完全重复按 MD5；感知相似按 dhash 汉明距离">
        <template #actions>
          <select
            v-model.number="perceptual"
            class="select select-sm"
            style="width: 190px"
            @change="onModeChange"
          >
            <option :value="0">完全重复（MD5）</option>
            <option :value="1">感知相似（dhash）</option>
          </select>
          <label v-if="perceptual" class="field field-inline" style="gap: 4px">
            <span class="tiny dim nowrap">汉明 ≤</span>
            <input
              v-model.number="threshold"
              class="input input-sm"
              type="number"
              min="0"
              max="32"
              style="width: 64px"
              @change="loadDups"
            />
          </label>
          <button class="btn btn-sm" :disabled="dupLoading" @click="loadDups">
            <Icon name="refresh" :size="13" />
          </button>
        </template>

        <div v-if="dupLoading" class="small muted row" style="gap: 6px">
          <span class="spin" style="width: 12px; height: 12px; border: 2px solid var(--line-strong); border-right-color: var(--accent); border-radius: 50%; display: inline-block; animation: pa-spin 700ms linear infinite"></span>
          正在比对…
        </div>
        <template v-else-if="dups.length">
          <div v-for="(g, gi) in dups" :key="gi" class="stack" style="gap: 6px; margin-bottom: var(--sp-3)">
            <div class="small muted">
              <span class="tag tag-outline">{{ g.kind === "perceptual" ? "感知相似" : "完全相同" }}</span>
              {{ g.images.length }} 张 · {{ g.md5 ? `md5 ${g.md5.slice(0, 12)}…` : "" }}
            </div>
            <div class="grid-media" style="--card-min: 120px">
              <div
                v-for="it in g.images"
                :key="it.id"
                class="img-card"
                role="button"
                @click="openId = it.id"
              >
                <div class="thumb"><img :src="`/api/thumbs/${it.id}`" :alt="it.filename" loading="lazy" /></div>
                <div class="meta" style="padding: 6px 8px">
                  <div class="tiny clamp-1">{{ it.filename }}</div>
                  <div class="tiny dim clamp-1">{{ it.path }}</div>
                </div>
              </div>
            </div>
          </div>
        </template>
        <EmptyState v-else compact icon="check" title="没有发现重复" hint="换个模式或放宽汉明距离阈值再试试" />
      </Panel>

      <!-- 清理建议 -->
      <Panel title="清理建议" icon="wrench">
        <template #actions>
          <span class="small dim">可视 {{ num(cleanup?.visible) }} · 隐藏 {{ num(cleanup?.hidden) }}</span>
        </template>
        <div class="stat-grid" style="margin-bottom: var(--sp-3)">
          <StatCard :value="num(cleanup?.missing_files)" label="源文件已丢失" :tone="cleanup?.missing_files ? 'warn' : ''" />
          <StatCard :value="num(cleanup?.orphan_thumbs)" label="孤儿缩略图" :tone="cleanup?.orphan_thumbs ? 'warn' : ''" />
          <StatCard :value="num(cleanup?.trash_count)" label="回收站" icon="trash" />
          <StatCard :value="megabytes(cleanup?.db_bytes)" label="数据库体积" icon="database" />
        </div>

        <ul v-if="(cleanup?.suggestions || []).length" class="small" style="margin: 0; padding-left: 18px">
          <li v-for="(s, i) in cleanup.suggestions" :key="i">{{ s }}</li>
        </ul>
        <div v-else class="small muted">当前没有需要处理的清理项。</div>

        <template v-if="(cleanup?.trash_items || []).length">
          <h4 style="margin: var(--sp-3) 0 6px">回收站最近 50 条</h4>
          <div class="table-wrap">
            <table class="table">
              <thead><tr><th>原路径</th><th>删除时间</th><th style="width: 96px">操作</th></tr></thead>
              <tbody>
                <tr v-for="t in cleanup.trash_items" :key="t.id">
                  <td class="small wrap-anywhere">{{ t.original_path }}</td>
                  <td class="small nowrap dim">{{ datetime(t.deleted_at) }}</td>
                  <td><button class="btn btn-xs" @click="restore(t)">恢复</button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <div class="row" style="margin-top: var(--sp-3)">
          <input v-model="trashConfirm" class="input" style="max-width: 220px" placeholder="输入「清空回收站」" />
          <button
            class="btn btn-danger"
            :disabled="trashConfirm !== '清空回收站' || !cleanup?.trash_count"
            @click="clearTrash"
          >
            清空回收站
          </button>
          <span class="small dim">清空会真的删除回收站里的文件</span>
        </div>
      </Panel>

      <!-- 存储 -->
      <Panel title="磁盘与索引">
        <dl class="kv">
          <dt>索引数据库</dt>
          <dd>{{ megabytes(sys?.db_bytes) }}</dd>
          <dt>磁盘可用</dt>
          <dd>
            {{ bytes(sys?.free_bytes) }} / {{ bytes(sys?.total_bytes) }}
            <span class="dim">（已用 {{ percent((sys?.total_bytes || 0) - (sys?.free_bytes || 0), sys?.total_bytes || 0) }}）</span>
          </dd>
          <dt>后台任务</dt>
          <dd>
            <span v-for="(v, k) in dash?.jobs || {}" :key="k" class="tag tag-outline" style="margin-right: 4px">
              {{ k }} {{ v }}
            </span>
            <span v-if="!Object.keys(dash?.jobs || {}).length" class="dim">无任务</span>
          </dd>
        </dl>
      </Panel>
    </template>

    <ImageDrawer v-if="openId" v-model:image-id="openId" :ids="openIdList" @close="openId = null" />

    <ConfirmDialog
      :open="askPerceptual"
      title="感知相似比对可能较慢"
      message="感知相似要在 Python 侧对所有图片的 dhash 做两两比对，图多时可能要几十秒到几分钟，期间界面不会锁死但后端会忙。"
      :details="[`当前阈值：汉明距离 ≤ ${threshold}`, '想快一点就把阈值调小', '随时可以切回「完全重复」模式']"
      confirm-text="开始比对"
      icon="info"
      @close="cancelPerceptual"
      @confirm="confirmPerceptual"
    />
  </div>
</template>

<style scoped>
.two-col {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: var(--sp-4);
}
.two-col > .panel {
  margin-top: 0;
}
</style>

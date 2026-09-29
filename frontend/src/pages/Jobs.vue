<script setup>
// 任务队列：扫描 / 识别 / 嵌入三类。轮询可暂停，离开页面必清定时器。
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { api } from "../app/api.js";
import { notify } from "../app/toast.js";
import { datetime, JOB_STATE } from "../app/format.js";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import Panel from "../components/Panel.vue";
import Skeleton from "../components/Skeleton.vue";
import StatCard from "../components/StatCard.vue";

const counts = ref({});
const items = ref([]);
const stateFilter = ref("");
const typeFilter = ref("");
const polling = ref(true);
const eventsFor = ref(null);
const events = ref([]);
const loading = ref(true);

let timer = null;
let inFlight = false;

const STATES = [
  { value: "", label: "全部状态" },
  { value: "pending", label: "pending 待运行" },
  { value: "running", label: "running 运行中" },
  { value: "paused", label: "paused 已暂停" },
  { value: "succeeded", label: "succeeded 成功" },
  { value: "failed", label: "failed 失败" },
  { value: "dead", label: "dead 重试耗尽" },
];

const types = computed(() => [...new Set(items.value.map((j) => j.type))].filter(Boolean));

const visible = computed(() =>
  items.value.filter((j) => (typeFilter.value ? j.type === typeFilter.value : true)),
);

async function load() {
  if (inFlight) return;
  inFlight = true;
  try {
    const data = await api.jobs(stateFilter.value || undefined);
    counts.value = data.counts || {};
    items.value = data.items || [];
  } catch (e) {
    notify(e.message, "error");
  } finally {
    inFlight = false;
    loading.value = false;
  }
}

function startPolling() {
  stopPolling();
  timer = setInterval(() => {
    if (!document.hidden) load();
  }, 3000);
}
function stopPolling() {
  if (timer) clearInterval(timer);
  timer = null;
}

watch(polling, (v) => (v ? startPolling() : stopPolling()));

async function showEvents(job) {
  eventsFor.value = job.id;
  try {
    events.value = (await api.jobEvents(job.id)).items || [];
  } catch (e) {
    notify(e.message, "error");
  }
}

async function cancel(job) {
  try {
    await api.cancelJob(job.id);
    notify(`任务 #${job.id} 已取消`, "ok");
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function retry(job) {
  try {
    await api.retryJob(job.id);
    notify(`任务 #${job.id} 已重新入队`, "ok");
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function clearDone() {
  try {
    const res = await api.clearJobs();
    notify(`已清理 ${res.cleared} 个已完成任务`, "ok");
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

function pickState(state) {
  stateFilter.value = stateFilter.value === state ? "" : state;
  load();
}

onMounted(async () => {
  await load();
  startPolling();
});
onBeforeUnmount(stopPolling);
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>任务队列</h1>
        <div class="sub">扫描 / 识别 / 嵌入三类任务；暂停、退避、重试状态一目了然</div>
      </div>
      <div class="head-actions">
        <label class="lab-check small">
          <input v-model="polling" class="checkbox" type="checkbox" /> 3 秒自动刷新
        </label>
        <button class="btn btn-sm" :disabled="loading" @click="load">
          <Icon name="refresh" :size="13" /> 立即刷新
        </button>
        <button class="btn btn-sm btn-danger" @click="clearDone">清理已完成</button>
      </div>
    </div>

    <div class="stat-grid">
      <StatCard
        v-for="s in STATES.filter((x) => x.value)"
        :key="s.value"
        :value="counts[s.value] ?? 0"
        :label="s.label"
        :tone="JOB_STATE[s.value] || ''"
        clickable
        @click="pickState(s.value)"
      />
    </div>

    <Panel :count="visible.length" flush>
      <template #actions>
        <span class="small dim">
          {{ polling ? "每 3 秒自动刷新" : "已暂停自动刷新" }}
        </span>
      </template>
      <div class="row" style="padding: 12px var(--panel-pad); gap: 8px">
        <select v-model="stateFilter" class="select select-sm" style="width: 170px" @change="load">
          <option v-for="s in STATES" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
        <select v-model="typeFilter" class="select select-sm" style="width: 130px">
          <option value="">全部类型</option>
          <option v-for="t in types" :key="t" :value="t">{{ t }}</option>
        </select>
      </div>

      <Skeleton v-if="loading && !items.length" variant="rows" :count="6" />
      <EmptyState
        v-else-if="!visible.length"
        compact
        icon="check"
        title="当前没有任务"
        hint="登记目录或上传图片后，扫描与识别任务会出现在这里。"
      />
      <div v-else class="table-wrap" style="max-height: 66vh">
        <table class="table">
          <thead>
            <tr>
              <th style="width: 62px">#</th>
              <th style="width: 88px">类型</th>
              <th style="width: 82px">图片</th>
              <th style="width: 100px">状态</th>
              <th style="width: 74px">尝试</th>
              <th>错误 / 暂停原因</th>
              <th style="width: 150px">更新时间</th>
              <th style="width: 128px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="j in visible" :key="j.id" :class="{ 'is-active': eventsFor === j.id }">
              <td>
                <a class="mono small" style="cursor: pointer" @click="showEvents(j)">#{{ j.id }}</a>
              </td>
              <td class="small">{{ j.type }}</td>
              <td class="mono small">{{ j.image_id ?? "—" }}</td>
              <td>
                <span class="tag" :class="`tag-${JOB_STATE[j.state] || ''}`">{{ j.state }}</span>
              </td>
              <td class="small mono">{{ j.attempts }}/{{ j.max_attempts ?? "—" }}</td>
              <td class="small muted wrap-anywhere">{{ j.error || j.pause || "—" }}</td>
              <td class="small nowrap dim">{{ datetime(j.updated_at) }}</td>
              <td>
                <div class="row" style="gap: 4px">
                  <button
                    v-if="['pending', 'running', 'paused'].includes(j.state)"
                    class="btn btn-xs"
                    @click="cancel(j)"
                  >
                    取消
                  </button>
                  <button
                    v-if="['failed', 'dead'].includes(j.state)"
                    class="btn btn-xs"
                    @click="retry(j)"
                  >
                    <Icon name="retry" :size="12" /> 重试
                  </button>
                  <button class="btn btn-xs" @click="showEvents(j)">事件</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>

    <Panel v-if="eventsFor" :title="`任务 #${eventsFor} 事件回放`" count="" subtitle="最新的在最上面">
      <template #actions>
        <button class="btn btn-xs" @click="eventsFor = null; events = []">关闭</button>
      </template>
      <EmptyState v-if="!events.length" compact icon="history" title="这个任务还没有事件" />
      <div v-else class="timeline">
        <div v-for="ev in events" :key="ev.id" class="ev" :class="`ev-${ev.level === 'error' ? 'error' : ev.level === 'warning' ? 'warn' : 'ok'}`">
          <div class="small wrap-anywhere">{{ ev.message }}</div>
          <div class="tiny dim">{{ ev.level }} · {{ datetime(ev.created_at) }}</div>
        </div>
      </div>
    </Panel>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import { api, notify } from "../api.js";

const counts = ref({});
const items = ref([]);
const stateFilter = ref("");
const eventsFor = ref(null);
const events = ref([]);
let timer = null;

async function load() {
  try {
    const data = await api.get("/api/jobs", { state: stateFilter.value || undefined });
    counts.value = data.counts || {};
    items.value = data.items || [];
  } catch (e) {
    notify(e.message, "error");
  }
}

async function showEvents(job) {
  eventsFor.value = job.id;
  events.value = (await api.get(`/api/jobs/${job.id}/events`)).items || [];
}

async function cancel(job) {
  try {
    await api.post(`/api/jobs/${job.id}/cancel`, {});
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function retry(job) {
  try {
    await api.post(`/api/jobs/${job.id}/retry`, {});
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function clearDone() {
  try {
    await api.del("/api/jobs");
    notify("已清理完成任务");
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

onMounted(() => {
  load();
  timer = setInterval(load, 3000);
});
onUnmounted(() => clearInterval(timer));
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>任务</h1>
        <div class="sub">扫描 / 识别 / 嵌入 三类任务；暂停、退避、重试状态一目了然</div>
      </div>
      <button class="btn" @click="clearDone">清理已完成</button>
    </div>

    <div class="grid-stats" style="margin-bottom: 14px">
      <div v-for="(v, k) in counts" :key="k" class="stat">
        <div class="num">{{ v }}</div>
        <div class="label">{{ k }}</div>
      </div>
    </div>

    <div class="panel">
      <div class="row">
        <select v-model="stateFilter" @change="load">
          <option value="">全部状态</option>
          <option value="pending">pending</option>
          <option value="running">running</option>
          <option value="paused">paused</option>
          <option value="succeeded">succeeded</option>
          <option value="failed">failed</option>
          <option value="dead">dead</option>
        </select>
        <span class="small muted">每 3 秒自动刷新</span>
      </div>
    </div>

    <div class="panel">
      <table>
        <thead>
          <tr><th>#</th><th>类型</th><th>图片</th><th>状态</th><th>尝试</th><th>错误/暂停</th><th>更新时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="j in items" :key="j.id">
            <td><a class="small" style="cursor: pointer" @click="showEvents(j)">{{ j.id }}</a></td>
            <td>{{ j.type }}</td>
            <td>{{ j.image_id ?? "—" }}</td>
            <td>
              <span
                class="tag"
                :class="{
                  green: j.state === 'succeeded',
                  red: j.state === 'dead' || j.state === 'failed',
                  blue: j.state === 'running' || j.state === 'pending',
                }"
                >{{ j.state }}</span
              >
            </td>
            <td>{{ j.attempts }}/{{ j.max_attempts ?? "—" }}</td>
            <td class="small muted">{{ j.error || j.pause || "—" }}</td>
            <td class="small">{{ j.updated_at }}</td>
            <td class="row">
              <button
                v-if="['pending', 'running', 'paused'].includes(j.state)"
                class="btn small"
                @click="cancel(j)"
              >
                取消
              </button>
              <button
                v-if="['failed', 'dead'].includes(j.state)"
                class="btn small"
                @click="retry(j)"
              >
                重试
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!items.length" class="empty">暂无任务</div>
    </div>

    <div v-if="eventsFor" class="panel">
      <div class="row" style="justify-content: space-between">
        <h3>任务 #{{ eventsFor }} 事件回放</h3>
        <button class="btn small" @click="eventsFor = null">关闭</button>
      </div>
      <div v-for="ev in events" :key="ev.id" class="small muted">{{ ev.created_at }} {{ ev.message }}</div>
      <div v-if="!events.length" class="empty">无事件</div>
    </div>
  </div>
</template>

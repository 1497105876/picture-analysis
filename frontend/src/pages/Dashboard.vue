<script setup>
import { onMounted, ref } from "vue";
import { api, notify, thumbUrl } from "../api.js";

const dash = ref(null);
const sys = ref(null);
const cleanup = ref(null);
const perceptual = ref(0);
const dups = ref([]);
const openId = ref(null);
const trashConfirm = ref("");

const mb = (n) => (n === undefined || n === null ? "—" : (n / 1048576).toFixed(1));

async function load() {
  try {
    dash.value = await api.get("/api/stats/dashboard");
    sys.value = await api.get("/api/stats/system");
    cleanup.value = await api.get("/api/stats/cleanup");
    await loadDups();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function loadDups() {
  try {
    const data = await api.get("/api/stats/duplicates", { perceptual: perceptual.value });
    dups.value = data.groups || [];
  } catch (e) {
    notify(e.message, "error");
  }
}

async function clearTrash() {
  try {
    await api.del("/api/trash", { confirm: "清空回收站" });
    notify("回收站已清空");
    trashConfirm.value = "";
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function restore(t) {
  try {
    await api.post(`/api/trash/${t.id}/restore`, {});
    notify("已恢复到原路径并重新扫描");
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

onMounted(load);
</script>

<template>
  <div>
    <div class="page-head"><h1>仪表盘</h1></div>

    <div class="grid-stats" style="margin-bottom: 14px">
      <div class="stat"><div class="num">{{ dash?.total ?? "—" }}</div><div class="label">图片总数</div></div>
      <div class="stat"><div class="num">{{ dash?.hidden ?? "—" }}</div><div class="label">隐藏</div></div>
      <div class="stat">
        <div class="num">{{ dash?.analysis_states?.done ?? 0 }}</div>
        <div class="label">已识别</div>
      </div>
      <div class="stat">
        <div class="num">{{ (dash?.analysis_states?.queued || 0) + (dash?.analysis_states?.pending || 0) }}</div>
        <div class="label">排队中</div>
      </div>
      <div class="stat">
        <div class="num">{{ dash?.analysis_states?.failed ?? 0 }}</div>
        <div class="label">失败</div>
      </div>
      <div class="stat"><div class="num">{{ dash?.tokens_total ?? 0 }}</div><div class="label">累计 token</div></div>
      <div class="stat"><div class="num">{{ dash?.dirs ?? 0 }}</div><div class="label">登记目录</div></div>
      <div class="stat"><div class="num">{{ mb(sys?.db_bytes) }}</div><div class="label">索引体积 (MB)</div></div>
    </div>

    <div class="panel">
      <h3>分类分布</h3>
      <div v-for="row in dash?.by_category || []" :key="row.category" class="bar-row">
        <span style="width: 110px">{{ row.category }}</span>
        <div
          class="bar"
          :style="{
            width:
              (row.count * 100) /
                Math.max(1, ...(dash?.by_category || []).map((r) => r.count)) +
              '%',
          }"
        ></div>
        <span>{{ row.count }}</span>
      </div>
      <div v-if="!(dash?.by_category || []).length" class="empty">暂无数据</div>
    </div>

    <div class="panel">
      <h3>按月分布</h3>
      <div v-for="row in dash?.monthly || []" :key="row.month" class="bar-row">
        <span style="width: 110px">{{ row.month }}</span>
        <div
          class="bar"
          :style="{
            width:
              (row.count * 100) / Math.max(1, ...(dash?.monthly || []).map((r) => r.count)) + '%',
          }"
        ></div>
        <span>{{ row.count }}</span>
      </div>
      <div v-if="!(dash?.monthly || []).length" class="empty">暂无数据</div>
    </div>

    <div class="panel">
      <h3>重复检测</h3>
      <div class="row" style="margin-bottom: 8px">
        <select v-model.number="perceptual" @change="loadDups">
          <option :value="0">完全重复（md5）</option>
          <option :value="1">感知相似（dhash 汉明 ≤6）</option>
        </select>
      </div>
      <div v-for="(g, gi) in dups" :key="gi" style="margin-bottom: 12px">
        <div class="small muted">{{ g.md5 || g.kind || "重复组" }} · {{ g.images.length }} 张</div>
        <div class="cards" style="grid-template-columns: repeat(auto-fill, minmax(130px, 1fr))">
          <div v-for="it in g.images" :key="it.id" class="card" @click="openId = it.id">
            <div class="ph"><img :src="thumbUrl(it.id)" :alt="it.filename" /></div>
            <div class="meta"><div class="name">{{ it.filename }}</div></div>
          </div>
        </div>
      </div>
      <div v-if="!dups.length" class="empty">未发现重复</div>
    </div>

    <div class="panel">
      <h3>清理建议</h3>
      <ul class="small">
        <li>丢失文件 {{ cleanup?.missing_files ?? 0 }} 个 · 孤儿缩略图 {{ cleanup?.orphan_thumbs ?? 0 }} 个 ·
          回收站 {{ cleanup?.trash_count ?? 0 }} 条</li>
        <li v-for="(s, i) in cleanup?.suggestions || []" :key="i">{{ s }}</li>
      </ul>
      <div v-if="!(cleanup?.suggestions || []).length" class="empty">无需清理</div>

      <table v-if="(cleanup?.trash_items || []).length" style="margin-top: 8px">
        <thead><tr><th>原路径</th><th>删除时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="t in cleanup.trash_items" :key="t.id">
            <td>{{ t.original_path }}</td>
            <td>{{ t.deleted_at }}</td>
            <td><button class="btn small" @click="restore(t)">恢复</button></td>
          </tr>
        </tbody>
      </table>

      <div class="row" style="margin-top: 10px">
        <input v-model="trashConfirm" placeholder="输入「清空回收站」确认" />
        <button class="btn danger" :disabled="trashConfirm !== '清空回收站'" @click="clearTrash">
          清空回收站
        </button>
      </div>
    </div>

    <div class="panel">
      <h3>存储</h3>
      <table>
        <tbody>
          <tr><th>索引库</th><td>{{ mb(sys?.db_bytes) }} MB</td></tr>
          <tr><th>磁盘可用</th><td>{{ mb(sys?.free_bytes) }} MB / {{ mb(sys?.total_bytes) }} MB</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

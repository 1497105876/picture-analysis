<script setup>
import { onMounted, ref } from "vue";
import { api, notify } from "../api.js";

const status = ref("pending");
const items = ref([]);

async function load() {
  items.value =
    (await api.get("/api/proposals", { status: status.value || undefined })).items || [];
}

async function decide(p, decision) {
  try {
    await api.post(`/api/proposals/${p.id}/${decision}`, {});
    notify(decision === "approve" ? "已批准并应用" : "已拒绝");
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

onMounted(load);
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>提案</h1>
        <div class="sub">对话产生的实体/标签建议：批准前库内零变化</div>
      </div>
      <select v-model="status" @change="load">
        <option value="pending">待处理</option>
        <option value="approved">已批准</option>
        <option value="rejected">已拒绝</option>
        <option value="">全部</option>
      </select>
    </div>

    <div class="panel">
      <table v-if="items.length">
        <thead><tr><th>#</th><th>类型</th><th>内容</th><th>来源</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="p in items" :key="p.id">
            <td>{{ p.id }}</td>
            <td>{{ p.type }}</td>
            <td class="small">{{ JSON.stringify(p.payload) }}</td>
            <td>{{ p.source }}</td>
            <td><span class="tag" :class="p.status === 'approved' ? 'green' : p.status === 'pending' ? 'blue' : 'red'">{{ p.status }}</span></td>
            <td class="row">
              <template v-if="p.status === 'pending'">
                <button class="btn small primary" @click="decide(p, 'approve')">批准</button>
                <button class="btn small danger" @click="decide(p, 'reject')">拒绝</button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">没有提案</div>
    </div>
  </div>
</template>

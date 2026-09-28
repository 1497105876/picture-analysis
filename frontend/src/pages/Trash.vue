<script setup>
import { onMounted, ref } from "vue";
import { api, notify } from "../api.js";

const items = ref([]);
const confirmWord = ref("");

async function load() {
  items.value = (await api.get("/api/trash")).items || [];
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

async function clearAll() {
  try {
    await api.del("/api/trash", { confirm: confirmWord.value });
    notify("回收站已清空");
    confirmWord.value = "";
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
        <h1>回收站</h1>
        <div class="sub">删除源文件进回收站，可恢复；清空需确认词</div>
      </div>
    </div>

    <div class="panel">
      <table v-if="items.length">
        <thead><tr><th>原路径</th><th>回收位置</th><th>删除时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="t in items" :key="t.id">
            <td>{{ t.original_path }}</td>
            <td class="small muted">{{ t.trash_path }}</td>
            <td>{{ t.deleted_at }}</td>
            <td><button class="btn small" @click="restore(t)">恢复</button></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">回收站是空的</div>

      <div class="row" style="margin-top: 12px">
        <input v-model="confirmWord" placeholder="输入「清空回收站」确认" />
        <button class="btn danger" :disabled="confirmWord !== '清空回收站'" @click="clearAll">
          清空回收站
        </button>
      </div>
    </div>
  </div>
</template>

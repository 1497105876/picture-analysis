<script setup>
// 回收站：删除源文件的落点，可以从这里恢复原路径。
import { onMounted, ref } from "vue";

import { api } from "../app/api.js";
import { notify } from "../app/toast.js";
import { datetime } from "../app/format.js";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import Panel from "../components/Panel.vue";
import StatCard from "../components/StatCard.vue";

const items = ref([]);
const loading = ref(true);
const askClear = ref(false);
const busy = ref(false);

async function load() {
  loading.value = true;
  try {
    items.value = (await api.trash()).items || [];
  } catch (e) {
    notify(e.message, "error");
  } finally {
    loading.value = false;
  }
}

async function restore(t) {
  busy.value = true;
  try {
    await api.restoreTrash(t.id);
    notify("已恢复到原路径并重新扫描", "ok");
    await load();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

async function clearAll() {
  busy.value = true;
  try {
    const res = await api.clearTrash();
    notify(`回收站已清空，删除 ${res.removed} 个文件`, "ok");
    askClear.value = false;
    await load();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>回收站</h1>
        <div class="sub">删除源文件先进 data/trash，可以原地恢复；清空需要确认词</div>
      </div>
      <div class="head-actions">
        <button class="btn btn-sm" :disabled="loading" @click="load">
          <Icon name="refresh" :size="13" /> 刷新
        </button>
        <button class="btn btn-sm btn-danger" :disabled="!items.length" @click="askClear = true">
          <Icon name="trash" :size="13" /> 清空回收站
        </button>
      </div>
    </div>

    <div class="stat-grid">
      <StatCard :value="items.length" label="待处理条目" icon="trash" />
      <StatCard
        :value="datetime(items[0]?.deleted_at)"
        label="最近一次删除"
        icon="calendar"
      />
    </div>

    <Panel title="回收站内容" :count="items.length">
      <EmptyState
        v-if="!items.length"
        compact
        icon="check"
        title="回收站是空的"
        hint="在图片详情里选择「删除源文件」，文件会先到这里待着。"
      />
      <div v-else class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th style="width: 88px">#</th>
              <th>原路径</th>
              <th>回收位置</th>
              <th style="width: 150px">删除时间</th>
              <th style="width: 88px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in items" :key="t.id">
              <td class="mono">#{{ t.id }}</td>
              <td class="small wrap-anywhere mono">{{ t.original_path }}</td>
              <td class="small dim wrap-anywhere mono">{{ t.trash_path }}</td>
              <td class="small nowrap">{{ datetime(t.deleted_at) }}</td>
              <td>
                <button class="btn btn-xs" :disabled="busy" @click="restore(t)">恢复</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>

    <ConfirmDialog
      :open="askClear"
      title="清空回收站"
      message="回收站里的文件会被真正删除，无法再通过本界面恢复。"
      :details="[`当前 ${items.length} 条记录`, '索引不会受影响（索引在删除源文件时已经移除）']"
      confirm-word="清空回收站"
      confirm-text="确认清空"
      danger
      :busy="busy"
      @close="askClear = false"
      @confirm="clearAll"
    />
  </div>
</template>

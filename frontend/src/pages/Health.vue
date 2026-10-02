<script setup>
// 断链体检：源文件在磁盘上被改名、挪走或删掉之后，索引里那条记录就成了打不开的死链。
// 以前项目只在仪表盘统计了一个 missing_files 数字——看不出是哪几张，也没地方清理。
// 这里逐条比对磁盘，把死链摆出来，并且给两条出路：
//   重扫目录 = 文件可能只是被挪走/改名，扫一遍自动对上（missing 标记会被抹掉）
//   从索引移除 = 默认只删索引不留墓碑，文件哪天挪回来还能被重新收录
import { computed, onMounted, ref } from "vue";

import { api } from "../app/api.js";
import { notify } from "../app/toast.js";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import Panel from "../components/Panel.vue";
import Skeleton from "../components/Skeleton.vue";
import StatCard from "../components/StatCard.vue";

const items = ref([]);
const scanned = ref(0);
const loading = ref(true);
const busy = ref(false);
const picked = ref([]);
const askPrune = ref(false);
const askPruneExclude = ref(false);

const dirCount = computed(() => new Set(items.value.map((i) => i.dir_id)).size);
const flaggedCount = computed(() => items.value.filter((i) => i.flagged).length);
const allPicked = computed(() => items.value.length > 0 && picked.value.length === items.value.length);

function toggleAll() {
  picked.value = allPicked.value ? [] : items.value.map((i) => i.id);
}

async function load() {
  loading.value = true;
  try {
    const data = await api.broken();
    items.value = data.items || [];
    scanned.value = data.scanned || 0;
    picked.value = picked.value.filter((id) => items.value.some((i) => i.id === id));
  } catch (e) {
    notify(e.message, "error");
  } finally {
    loading.value = false;
  }
}

async function rescan(row) {
  if (!row.dir_registered) {
    notify("这个目录已经注销了，只能从索引里移除", "error");
    return;
  }
  busy.value = true;
  try {
    const res = await api.rescanDir(row.dir_id);
    notify(`目录已重扫：新增 ${res.added || 0}，更新 ${res.updated || 0}`, "ok");
    await load();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

async function prune(exclude) {
  const ids = picked.value.slice();
  if (!ids.length) {
    notify("先勾选要清理的条目", "error");
    return;
  }
  busy.value = true;
  try {
    const res = await api.pruneBroken(ids, exclude);
    const skip = res.skipped?.length ? `，${res.skipped.length} 条文件已回来、跳过` : "";
    notify(
      exclude
        ? `已清理 ${res.count} 条并登记排除${skip}`
        : `已清理 ${res.count} 条${skip}，文件挪回来后重新扫描会再收录`,
      "ok",
    );
    askPrune.value = false;
    askPruneExclude.value = false;
    picked.value = [];
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
        <h1>断链体检</h1>
        <div class="sub">索引里有、但磁盘上已经打不开的条目</div>
      </div>
      <div class="head-actions">
        <button class="btn btn-sm" :disabled="loading" @click="load">
          <Icon name="refresh" :size="13" /> 重新体检
        </button>
      </div>
    </div>

    <div class="stat-grid">
      <StatCard :value="items.length" label="断链条目" icon="warning" />
      <StatCard :value="scanned" label="已比对条目" icon="image" />
      <StatCard :value="dirCount" label="涉及目录" icon="folder" />
    </div>

    <Panel title="断链清单" :count="items.length" subtitle="常见原因：在资源管理器里改了名、挪了位置、或者整个文件夹搬走了">
      <template #actions>
        <button
          v-if="items.length"
          class="btn btn-sm"
          :disabled="busy || !picked.length"
          @click="askPrune = true"
        >
          <Icon name="trash" :size="13" />
          清理选中（{{ picked.length }}）
        </button>
      </template>

      <Skeleton v-if="loading" variant="rows" :count="5" />

      <EmptyState
        v-else-if="!items.length"
        compact
        icon="check"
        title="没有断链，索引和磁盘对得上"
        hint="在资源管理器里动过文件之后，可以回来再体检一次"
      />

      <div v-else class="stack-3">
        <div class="row" style="gap: 8px; align-items: center">
          <label class="row small" style="gap: 6px; cursor: pointer">
            <input type="checkbox" :checked="allPicked" @change="toggleAll" />
            全选 {{ items.length }} 条
          </label>
          <span class="small dim">
            其中 {{ flaggedCount }} 条已被增量扫描标记为 missing，其余是这次体检才发现的
          </span>
          <span style="flex: 1"></span>
          <button
            class="btn btn-xs btn-ghost"
            :disabled="busy || !picked.length"
            @click="askPruneExclude = true"
          >
            清理并排除（不再收录）
          </button>
        </div>

        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th style="width: 40px"></th>
                <th style="width: 72px">#</th>
                <th>文件</th>
                <th>原目录</th>
                <th style="width: 210px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in items" :key="b.id">
                <td>
                  <input v-model="picked" type="checkbox" :value="b.id" />
                </td>
                <td class="mono">#{{ b.id }}</td>
                <td class="small wrap-anywhere mono">
                  {{ b.filename }}
                  <div class="dim" style="font-size: 11px">{{ b.path }}</div>
                </td>
                <td class="small dim wrap-anywhere mono">
                  {{ b.dir_path || "（原目录已注销）" }}
                  <span v-if="b.hidden">（隐藏区）</span>
                </td>
                <td>
                  <div class="row" style="gap: 6px">
                    <button
                      class="btn btn-xs"
                      :disabled="busy || !b.dir_registered"
                      :title="b.dir_registered ? '扫一遍这个目录，文件还在就自动对上' : '目录已注销，无法重扫'"
                      @click="rescan(b)"
                    >
                      重扫目录
                    </button>
                    <button
                      class="btn btn-xs btn-ghost"
                      :disabled="busy"
                      @click="picked = [b.id]; askPrune = true"
                    >
                      移除
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </Panel>

    <ConfirmDialog
      :open="askPrune"
      icon="trash"
      title="从索引里移除这些断链"
      :message="`将移除 ${picked.length} 条打不开的索引记录，磁盘上的文件不会被碰。`"
      :details="[
        '默认只删索引、不留墓碑：文件哪天挪回原处，增量扫描会重新收录它。',
        '想让它永远别再被收录，请用「清理并排除」。',
      ]"
      confirm-text="确认移除"
      :busy="busy"
      @close="askPrune = false"
      @confirm="prune(false)"
    />

    <ConfirmDialog
      :open="askPruneExclude"
      danger
      icon="eye-off"
      title="清理并排除"
      :message="`将移除 ${picked.length} 条断链，并登记排除：以后增量扫描不会再收录这些文件。`"
      :details="['如果只是暂时挪走了，请用普通的「清理选中」，别排除。']"
      confirm-word="清理并排除"
      confirm-text="确认排除"
      :busy="busy"
      @close="askPruneExclude = false"
      @confirm="prune(true)"
    />
  </div>
</template>

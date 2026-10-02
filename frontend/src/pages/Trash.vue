<script setup>
// 回收站与已排除。
// 「删除源文件」的文件落在这里，可原地恢复；「只删索引」只会留一条墓碑。
// 以前墓碑完全不可见、也没法撤销——等于永久丢失。这里把它摆出来：
//   恢复     = 解除排除 + 立刻重新入库（不用再让用户自己去点增量扫描）
//   移除记录 = 只删墓碑，下次增量扫描自动重新收录
import { computed, onMounted, ref } from "vue";

import { api } from "../app/api.js";
import { notify } from "../app/toast.js";
import { bytes, datetime } from "../app/format.js";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import Panel from "../components/Panel.vue";
import Skeleton from "../components/Skeleton.vue";
import StatCard from "../components/StatCard.vue";

const items = ref([]);
const excluded = ref([]);
const loading = ref(true);
const busy = ref(false);
const tab = ref("trash");
const askClearTrash = ref(false);
const askClearExcluded = ref(false);
const askForget = ref(null);

const rows = computed(() => (tab.value === "trash" ? items.value : excluded.value));
const trashBytes = computed(() => items.value.reduce((a, b) => a + (Number(b.bytes) || 0), 0));

const subtitle = computed(() =>
  tab.value === "trash"
    ? "文件本身已经被搬进 data/trash，恢复就是搬回原路径并重建索引"
    : "「只删索引」留下的墓碑。文件还在原处，只是不再被收录",
);
const emptyHint = computed(() =>
  tab.value === "trash"
    ? "删掉的文件会出现在这里，随时能一键恢复"
    : "用「只删索引」删掉的图会记在这里，随时能撤销",
);

async function load() {
  loading.value = true;
  try {
    const [trash, ex] = await Promise.all([api.trash(), api.excluded()]);
    items.value = trash.items || [];
    excluded.value = ex.items || [];
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
    notify("已恢复到原路径，索引已重建", "ok");
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
    await load();
  }
}

async function clearTrash() {
  busy.value = true;
  try {
    const res = await api.clearTrash();
    notify(`回收站已清空，删除 ${res.removed} 个文件`, "ok");
    askClearTrash.value = false;
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
    await load();
  }
}

async function restoreExclusion(e) {
  busy.value = true;
  try {
    const res = await api.restoreExcluded(e.id);
    notify(`已恢复「${e.filename}」：解除排除并重新入库（${res.action}）`, "ok");
  } catch (err) {
    notify(err.message, "error");
  } finally {
    busy.value = false;
    await load();
  }
}

async function forgetExclusion() {
  const e = askForget.value;
  askForget.value = null;
  if (!e) return;
  busy.value = true;
  try {
    await api.forgetExcluded(e.id);
    notify(`已移除「${e.filename}」的排除记录，下次增量扫描会重新收录`, "ok");
    await load();
  } catch (err) {
    notify(err.message, "error");
  } finally {
    busy.value = false;
  }
}

async function clearExcluded() {
  busy.value = true;
  try {
    const res = await api.clearExcluded();
    notify(`已清除 ${res.removed} 条排除记录，重新扫描会全部收录回来`, "ok");
    askClearExcluded.value = false;
  } catch (err) {
    notify(err.message, "error");
  } finally {
    busy.value = false;
    await load();
  }
}

onMounted(load);
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>回收站</h1>
        <div class="sub">删掉的东西在这里都留了一手，别急着清空</div>
      </div>
      <div class="head-actions">
        <div class="seg">
          <button :class="{ 'is-on': tab === 'trash' }" @click="tab = 'trash'">
            待恢复 {{ items.length }}
          </button>
          <button :class="{ 'is-on': tab === 'excluded' }" @click="tab = 'excluded'">
            已排除 {{ excluded.length }}
          </button>
        </div>
        <button class="btn btn-sm" :disabled="loading" @click="load">
          <Icon name="refresh" :size="13" /> 刷新
        </button>
      </div>
    </div>

    <div class="stat-grid">
      <StatCard :value="items.length" label="待恢复文件" icon="trash" />
      <StatCard :value="excluded.length" label="已排除（墓碑）" icon="eye-off" />
      <StatCard :value="bytes(trashBytes)" label="回收站占用" icon="save" />
    </div>

    <Panel
      :title="tab === 'trash' ? '待恢复文件' : '已排除（墓碑）'"
      :count="rows.length"
      :subtitle="subtitle"
    >
      <template #actions>
        <button
          v-if="tab === 'trash' && items.length"
          class="btn btn-sm btn-danger"
          :disabled="busy"
          @click="askClearTrash = true"
        >
          <Icon name="trash" :size="13" />
          清空回收站（{{ items.length }} 个文件）
        </button>
        <button
          v-else-if="excluded.length"
          class="btn btn-sm btn-danger"
          :disabled="busy"
          @click="askClearExcluded = true"
        >
          <Icon name="trash" :size="13" />
          清空排除表（{{ excluded.length }} 条）
        </button>
      </template>

      <Skeleton v-if="loading" variant="rows" :count="5" />

      <EmptyState
        v-else-if="!rows.length"
        compact
        icon="check"
        :title="tab === 'trash' ? '回收站是空的' : '没有排除记录'"
        :hint="emptyHint"
      />

      <div v-else class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th style="width: 72px">#</th>
              <th>文件</th>
              <th>位置</th>
              <th style="width: 150px">时间</th>
              <th style="width: 148px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in rows" :key="t.id">
              <td class="mono">#{{ t.id }}</td>
              <td class="small wrap-anywhere mono">{{ t.original_path || t.filename || t.path }}</td>
              <td class="small dim wrap-anywhere mono">
                {{ t.trash_path || t.dir_path || "（原目录已注销）" }}
              </td>
              <td class="small nowrap">{{ datetime(t.deleted_at) }}</td>
              <td>
                <div v-if="tab === 'trash'" class="row" style="gap: 6px">
                  <button class="btn btn-xs" :disabled="busy" @click="restore(t)">恢复</button>
                </div>
                <div v-else class="row" style="gap: 6px">
                  <button
                    class="btn btn-xs"
                    :disabled="busy || t.exists === false"
                    :title="t.exists === false ? '文件已不在原位置，只能移除记录' : '解除排除并立刻重新入库'"
                    @click="restoreExclusion(t)"
                  >
                    恢复
                  </button>
                  <button class="btn btn-xs btn-ghost" :disabled="busy" @click="askForget = t">
                    移除记录
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>

    <ConfirmDialog
      :open="askClearTrash"
      danger
      icon="trash"
      title="清空回收站"
      :message="`将永久删除 data/trash 中 ${items.length} 个文件，无法恢复。`"
      :details="['回收站里的文件是磁盘上真实存在的副本，删掉就真没了。']"
      confirm-word="清空回收站"
      confirm-text="确认清空"
      :busy="busy"
      @close="askClearTrash = false"
      @confirm="clearTrash"
    />

    <ConfirmDialog
      :open="askClearExcluded"
      danger
      icon="trash"
      title="清空排除表"
      :message="`将清除 ${excluded.length} 条排除记录。文件本身不受影响，重新扫描后会被重新收录。`"
      :details="['如果你只是想恢复其中某一张，请用行内的「恢复」按钮，别整表清空。']"
      confirm-word="清空排除表"
      confirm-text="确认清除"
      :busy="busy"
      @close="askClearExcluded = false"
      @confirm="clearExcluded"
    />

    <ConfirmDialog
      :open="askForget !== null"
      danger
      icon="eye-off"
      title="移除这条排除记录"
      :message="askForget ? `不再记住「${askForget.filename}」曾被排除。文件仍在原处，下次增量扫描会重新收录它。` : ''"
      confirm-text="移除记录"
      :busy="busy"
      @close="askForget = null"
      @confirm="forgetExclusion"
    />
  </div>
</template>

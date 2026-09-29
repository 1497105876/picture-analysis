<script setup>
// 提案：对话过程中 AI 建议的实体/标签，批准前库内零变化。
import { computed, onMounted, ref } from "vue";

import { api } from "../app/api.js";
import { notify } from "../app/toast.js";
import { datetime } from "../app/format.js";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import Panel from "../components/Panel.vue";

const status = ref("pending");
const items = ref([]);
const busy = ref(false);

const STATUS = [
  { value: "pending", label: "待处理" },
  { value: "approved", label: "已批准" },
  { value: "rejected", label: "已拒绝" },
  { value: "", label: "全部" },
];

async function load() {
  try {
    items.value = (await api.proposals(status.value)).items || [];
  } catch (e) {
    notify(e.message, "error");
  }
}

async function decide(p, decision) {
  busy.value = true;
  try {
    await (decision === "approve" ? api.approveProposal(p.id) : api.rejectProposal(p.id));
    notify(decision === "approve" ? "已批准并写入库" : "已拒绝", "ok");
    await load();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

/** 把 payload 渲染成人能读的形式，而不是裸 JSON */
function describe(p) {
  const payload = p.payload || {};
  if (p.type === "entity") {
    return [
      ["名称", payload.name],
      ["分类", payload.category || "—"],
      ["描述", payload.description || "—"],
      ["别名", (payload.aliases || []).join("、") || "—"],
    ];
  }
  if (p.type === "tag") return [["标签", payload.tag]];
  return Object.entries(payload).map(([k, v]) => [k, v]);
}

const pendingCount = computed(() => items.value.filter((i) => i.status === "pending").length);

onMounted(load);
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>提案</h1>
        <div class="sub">对话产生的实体/标签建议，批准之前库里不会有任何变化</div>
      </div>
      <div class="head-actions">
        <select v-model="status" class="select select-sm" style="width: 116px" @change="load">
          <option v-for="s in STATUS" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
        <button class="btn btn-sm" @click="load"><Icon name="refresh" :size="13" /></button>
      </div>
    </div>

    <Panel :count="items.length" :subtitle="status === 'pending' ? `${pendingCount} 条等待你拍板` : ''">
      <template #actions>
        <span class="small dim">来源列显示是谁提的：对话（chat）或规则</span>
      </template>

      <EmptyState
        v-if="!items.length"
        compact
        icon="inbox"
        title="当前没有提案"
        hint="去对话页跟它聊聊，AI 认出了新的人/物/地点会在这里生成建议。"
      />

      <div v-else class="stack-3">
        <div v-for="p in items" :key="p.id" class="proposal">
          <div class="row-between">
            <div class="row" style="gap: 6px">
              <span class="tag tag-accent">{{ p.type === "entity" ? "实体" : p.type === "tag" ? "标签" : p.type }}</span>
              <span class="mono small dim">#{{ p.id }}</span>
              <span
                class="tag"
                :class="p.status === 'approved' ? 'tag-ok' : p.status === 'pending' ? 'tag-warn' : 'tag-danger'"
              >
                {{ p.status }}
              </span>
            </div>
            <div class="row" style="gap: 6px">
              <span class="tiny dim">{{ p.source }} · {{ datetime(p.created_at) }}</span>
              <template v-if="p.status === 'pending'">
                <button class="btn btn-xs btn-primary" :disabled="busy" @click="decide(p, 'approve')">
                  <Icon name="check" :size="12" /> 批准
                </button>
                <button class="btn btn-xs btn-danger" :disabled="busy" @click="decide(p, 'reject')">
                  <Icon name="close" :size="12" /> 拒绝
                </button>
              </template>
            </div>
          </div>
          <dl class="kv" style="margin-top: 8px">
            <template v-for="(row, i) in describe(p)" :key="i">
              <dt>{{ row[0] }}</dt>
              <dd class="wrap-anywhere">{{ row[1] }}</dd>
            </template>
          </dl>
        </div>
      </div>
    </Panel>
  </div>
</template>

<style scoped>
.proposal {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 12px;
  background: var(--surface-inset);
}
</style>

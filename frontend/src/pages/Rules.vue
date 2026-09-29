<script setup>
// 分类规则：IF 条件 → THEN 动作。按优先级首条命中即停，改规则永不触发 AI 外发。
import { onMounted, reactive, ref } from "vue";

import { api } from "../app/api.js";
import { notify } from "../app/toast.js";
import { RULE_TARGETS, RULE_OPS } from "../app/format.js";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import Panel from "../components/Panel.vue";

const rules = ref([]);
const editingId = ref(null);
const trial = ref(null);
const busy = ref(false);
const askRecompute = ref("");
const trialOpen = ref(false);

const blank = {
  name: "",
  priority: 0,
  enabled: true,
  target: "dir_prefix",
  op: "contains",
  value: "",
  set_category: "",
  add_tags: [],
  add_to_album: "",
  exclude: false,
};
const form = reactive({ ...blank, add_tags: [] });

function condition() {
  return { target: form.target, op: form.op, value: form.value };
}
function action() {
  const out = {};
  if (form.set_category) out.set_category = form.set_category;
  if (form.add_tags.length) out.add_tags = [...form.add_tags];
  if (form.add_to_album) out.add_to_album = form.add_to_album;
  return out;
}

async function load() {
  try {
    rules.value = (await api.rules()).items || [];
  } catch (e) {
    notify(e.message, "error");
  }
}

function reset() {
  editingId.value = null;
  Object.assign(form, { ...blank, add_tags: [] });
}

function edit(r) {
  editingId.value = r.id;
  form.name = r.name || "";
  form.priority = Number(r.priority) || 0;
  form.enabled = Boolean(r.enabled);
  form.target = r.condition?.target || "dir_prefix";
  form.op = r.condition?.op || "contains";
  form.value = r.condition?.value || "";
  form.set_category = r.action?.set_category || "";
  form.add_tags = [...(r.action?.add_tags || [])];
  form.add_to_album = r.action?.add_to_album || "";
}

async function save() {
  const act = action();
  if (!Object.keys(act).length) return notify("动作至少填一项：分类、标签或相册", "warn");
  if (!form.value.trim()) return notify("条件匹配值不能为空", "warn");
  busy.value = true;
  try {
    const payload = {
      name: form.name.trim() || "未命名规则",
      priority: Number(form.priority) || 0,
      enabled: form.enabled,
      condition: condition(),
      action: act,
    };
    if (editingId.value) {
      await api.patchRule(editingId.value, payload);
      notify("规则已更新", "ok");
    } else {
      await api.addRule(payload);
      notify("规则已创建", "ok");
    }
    reset();
    trial.value = null;
    await load();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

async function remove(r) {
  busy.value = true;
  try {
    await api.deleteRule(r.id);
    notify(`已删除规则「${r.name}」`, "ok");
    await load();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

async function toggleEnabled(r) {
  try {
    await api.patchRule(r.id, { enabled: !r.enabled });
    r.enabled = !r.enabled;
  } catch (e) {
    notify(e.message, "error");
  }
}

async function movePriority(r, delta) {
  const next = Math.max(0, Number(r.priority) + delta);
  try {
    await api.patchRule(r.id, { priority: next });
    notify(`优先级已改为 ${next}（数字越小越先判）`, "ok");
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function tryRun() {
  if (!form.value.trim()) return notify("先填好条件的匹配值", "warn");
  busy.value = true;
  try {
    trial.value = await api.tryRule(condition(), 50);
    trialOpen.value = true;
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

async function recompute() {
  const phase = askRecompute.value;
  busy.value = true;
  try {
    const data = await api.recomputeRules(phase);
    notify(`${phase} 阶段补算完成，命中 ${data.applied} 张`, "ok");
    askRecompute.value = "";
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

function targetLabel(v) {
  return RULE_TARGETS.find((t) => t.value === v)?.label || v;
}
function opLabel(v) {
  return RULE_OPS.find((o) => o.value === v)?.label || v;
}
function actionText(a) {
  const parts = [];
  if (a?.set_category) parts.push(`分类→${a.set_category}`);
  if (a?.add_tags?.length) parts.push(`标签+${a.add_tags.join("/")}`);
  if (a?.add_to_album) parts.push(`相册→${a.add_to_album}`);
  return parts.join(" · ") || "（空）";
}

onMounted(load);
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>分类规则</h1>
        <div class="sub">
          入库时 pre 阶段先判、OCR 完成后再判一次；只写 AI 分类位，人工分类永远不动
        </div>
      </div>
      <div class="head-actions">
        <button class="btn btn-sm" @click="askRecompute = 'pre'">补算 pre 阶段</button>
        <button class="btn btn-sm" @click="askRecompute = 'ocr'">补算 ocr 阶段</button>
      </div>
    </div>

    <Panel :title="editingId ? `编辑规则 #${editingId}` : '新建规则'" flush>
      <div class="stack-3" style="padding: 12px var(--panel-pad)">
        <div class="row" style="gap: 8px">
          <input v-model="form.name" class="input grow" style="min-width: 200px" placeholder="规则名，如：截图归档" />
          <label class="field field-inline" style="gap: 6px">
            <span class="tiny dim nowrap">优先级</span>
            <input v-model.number="form.priority" class="input input-sm" type="number" style="width: 76px" />
          </label>
          <label class="lab-check">
            <input v-model="form.enabled" class="checkbox" type="checkbox" /> 启用
          </label>
        </div>

        <div class="rule-line">
          <span class="kw">IF</span>
          <select v-model="form.target" class="select select-sm" style="width: 132px">
            <option v-for="t in RULE_TARGETS" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
          <select v-model="form.op" class="select select-sm" style="width: 104px">
            <option v-for="o in RULE_OPS" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
          <input v-model="form.value" class="input input-sm grow" placeholder="匹配值，如 screenshots 或 [Ss]creenshot" />
        </div>

        <div class="rule-line">
          <span class="kw kw-then">THEN</span>
          <input v-model="form.set_category" class="input input-sm" style="width: 168px" placeholder="设为分类…" />
          <span class="small dim">再往下填「追加标签」和「加入相册」，动作至少要有一样</span>
        </div>

        <div class="row" style="gap: 8px">
          <div class="stack" style="gap: 4px; flex: 1 1 260px; min-width: 220px">
            <span class="tiny dim">追加标签</span>
            <div class="taginput" @click="$refs.tagEl?.focus()">
              <span v-for="t in form.add_tags" :key="t" class="tag tag-accent">
                {{ t }}<span class="x" @click.stop="form.add_tags = form.add_tags.filter((x) => x !== t)">×</span>
              </span>
              <input
                ref="tagEl"
                placeholder="回车添加"
                @keyup.enter="
                  (e) => {
                    const v = e.target.value.trim();
                    if (v && !form.add_tags.includes(v)) form.add_tags.push(v);
                    e.target.value = '';
                  }
                "
              />
            </div>
          </div>
          <label class="field" style="flex: 0 1 200px">
            <span class="tiny dim">加入相册</span>
            <input v-model="form.add_to_album" class="input input-sm" placeholder="相册名" />
          </label>
        </div>

        <div class="row" style="gap: 8px">
          <button class="btn btn-sm" :disabled="busy" @click="tryRun">
            <Icon name="zoom" :size="13" /> 试跑预览
          </button>
          <button class="btn btn-primary" :disabled="busy" @click="save">
            <span v-if="busy" class="spin"></span>
            {{ editingId ? "保存修改" : "创建规则" }}
          </button>
          <button v-if="editingId" class="btn btn-sm" @click="reset">取消编辑</button>
          <span class="small dim">试跑只预览不落库</span>
        </div>
      </div>
    </Panel>

    <Panel title="规则列表" :count="rules.length" subtitle="按优先级从小到大执行，第一条命中后就停止">
      <EmptyState
        v-if="!rules.length"
        compact
        icon="rule"
        title="还没有规则"
        hint="规则适合处理「某个目录下的图一定是某分类」这种确定性判断，能省下一大笔识别费用。"
      />
      <div v-else class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th style="width: 78px">优先级</th>
              <th>名称</th>
              <th>条件</th>
              <th>动作</th>
              <th style="width: 78px">状态</th>
              <th style="width: 150px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rules" :key="r.id">
              <td class="mono">
                <div class="row" style="gap: 2px">
                  <button class="btn btn-xs" title="上移（优先级 -1）" @click="movePriority(r, -1)">↑</button>
                  <span class="strong" style="min-width: 20px; text-align: center">{{ r.priority }}</span>
                  <button class="btn btn-xs" title="下移（优先级 +1）" @click="movePriority(r, 1)">↓</button>
                </div>
              </td>
              <td class="strong">{{ r.name }}</td>
              <td class="small wrap-anywhere">
                <span class="mono">{{ targetLabel(r.condition?.target) }} {{ opLabel(r.condition?.op) }}</span>
                「{{ r.condition?.value }}」
              </td>
              <td class="small wrap-anywhere">{{ actionText(r.action) }}</td>
              <td>
                <span class="tag" :class="r.enabled ? 'tag-ok' : 'tag-outline'">
                  {{ r.enabled ? "启用" : "停用" }}
                </span>
              </td>
              <td>
                <div class="row" style="gap: 4px">
                  <button class="btn btn-xs" @click="toggleEnabled(r)">{{ r.enabled ? "停用" : "启用" }}</button>
                  <button class="btn btn-xs" @click="edit(r)">编辑</button>
                  <button class="btn btn-xs btn-danger" @click="remove(r)">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>

    <Teleport to="body">
      <div v-if="trialOpen" class="mask" @click="trialOpen = false"></div>
      <div v-if="trialOpen" class="modal">
        <div class="modal-box modal-lg">
          <div class="modal-head">
            <h3>试跑结果</h3>
            <div class="panel-sub">
              命中 {{ trial?.count }} 张（扫描 {{ trial?.scanned }} 张，未落库，未触发任何 AI 调用）
            </div>
          </div>
          <div class="modal-body">
            <EmptyState v-if="!trial?.matches?.length" compact icon="check" title="没有命中任何图片" hint="放宽条件或检查匹配值是否与实际路径相符" />
            <div v-else class="table-wrap" style="max-height: 46vh">
              <table class="table">
                <thead><tr><th style="width: 72px">ID</th><th>路径</th></tr></thead>
                <tbody>
                  <tr v-for="m in trial.matches" :key="m.id">
                    <td class="mono">#{{ m.id }}</td>
                    <td class="small wrap-anywhere mono">{{ m.path }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div class="modal-foot">
            <button class="btn" @click="trialOpen = false">关闭</button>
            <button class="btn btn-primary" :disabled="busy" @click="trialOpen = false; save()">
              按这个条件创建规则
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <ConfirmDialog
      :open="Boolean(askRecompute)"
      :title="`补算 ${askRecompute} 阶段规则`"
      message="会对库里所有历史图片重跑一遍规则：AI 分类位会被覆盖，人工填写的分类/描述不参与也不会被改。"
      :details="[
        askRecompute === 'pre' ? 'pre 阶段：评估除 OCR 之外的条件' : 'ocr 阶段：只评估 OCR 条件（无 OCR 结果的图不会命中）',
        '幂等操作：可以重复执行',
        '图多时可能耗时较久',
      ]"
      confirm-text="开始补算"
      icon="refresh"
      :busy="busy"
      @close="askRecompute = ''"
      @confirm="recompute"
    />
  </div>
</template>

<style scoped>
.rule-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface-inset);
}
.kw {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--accent-text);
  background: var(--accent-soft);
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  flex: none;
}
.kw-then {
  color: var(--ok);
  background: var(--ok-soft);
}
</style>

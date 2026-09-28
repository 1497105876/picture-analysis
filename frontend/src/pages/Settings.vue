<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { api, notify } from "../api.js";

const emit = defineEmits(["saved"]);
const schema = ref({ groups: [], values: {}, danger_groups: [] });
const values = ref({});
const profiles = ref([]);
const profileForm = reactive({ name: "", base_url: "", type: "openai", api_key: "" });
const probeResult = ref(null);
const auditItems = ref([]);
const showAdvanced = ref(false);
const synonyms = ref([]);
const synForm = reactive({ group: "", terms: "" });
const weights = ref({});
const weightForm = reactive({ term: "", weight: 1.0 });
const dangerConfirm = ref("");

const visibleGroups = computed(() =>
  (schema.value.groups || []).map((g) => ({
    ...g,
    items: g.items.filter((it) => showAdvanced.value || !it.advanced),
  })).filter((g) => g.items.length)
);

async function load() {
  schema.value = await api.get("/api/settings");
  const raw = { ...schema.value.values };
  for (const key of Object.keys(raw)) {
    if (Array.isArray(raw[key])) raw[key] = raw[key].join(",");
  }
  values.value = raw;
  profiles.value = schema.value.profiles || [];
  await Promise.all([loadAudit(), loadSyn()]);
}

async function loadAudit() {
  auditItems.value = (await api.get("/api/settings/audit", { limit: 50 })).items || [];
}

async function loadSyn() {
  synonyms.value = (await api.get("/api/synonyms")).groups || {};
  weights.value = (await api.get("/api/term-weights")).weights || {};
}

function toPayload(item) {
  const v = values.value[item.key];
  if (item.type === "csv") return Array.isArray(v) ? v.join(",") : String(v ?? "");
  if (item.type === "int") return Number(v) || 0;
  if (item.type === "float") return Number(v) || 0;
  if (item.type === "bool") return Boolean(v);
  return v;
}

async function save() {
  const payload = {};
  for (const g of schema.value.groups || []) {
    for (const it of g.items) payload[it.key] = toPayload(it);
  }
  try {
    await api.put("/api/settings", { values: payload });
    notify("设置已保存");
    emit("saved");
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function testConn() {
  try {
    probeResult.value = await api.post("/api/settings/test", {});
    notify(probeResult.value.ok ? "连接成功" : "连接失败", probeResult.value.ok ? "info" : "error");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function saveProfile() {
  try {
    await api.post("/api/settings/profiles", { ...profileForm });
    notify(`档案「${profileForm.name}」已保存`);
    profileForm.name = "";
    profileForm.base_url = "";
    profileForm.api_key = "";
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function deleteProfile(name) {
  if (!window.confirm(`删除档案「${name}」及其密钥？`)) return;
  try {
    await api.del(`/api/settings/profiles/${encodeURIComponent(name)}`);
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function rollback(a) {
  if (!window.confirm(`回滚 #${a.id}（${a.key}）？`)) return;
  try {
    await api.post(`/api/settings/audit/${a.id}/rollback`, {});
    notify("已回滚");
    emit("saved");
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function backup() {
  try {
    const data = await api.post("/api/settings/backup", {});
    notify(`备份完成：${data.path}`);
  } catch (e) {
    notify(e.message, "error");
  }
}

async function addSyn() {
  try {
    await api.put("/api/synonyms", {
      group: synForm.group,
      terms: synForm.terms.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
    });
    synForm.group = "";
    synForm.terms = "";
    await loadSyn();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function addWeight() {
  try {
    await api.put("/api/term-weights", { term: weightForm.term, weight: Number(weightForm.weight) });
    weightForm.term = "";
    await loadSyn();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function clearIndex() {
  try {
    await api.post("/api/danger/clear-index", { confirm: dangerConfirm.value });
    notify("索引已清空（源文件未动）");
    dangerConfirm.value = "";
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
        <h1>设置</h1>
        <div class="sub">schema 驱动渲染：新增配置项前端零代码；密钥存 .env，日志与导出不落密钥</div>
      </div>
      <div class="row">
        <label class="small"><input v-model="showAdvanced" type="checkbox" /> 显示高级项</label>
        <button class="btn" @click="testConn">连接探测</button>
        <button class="btn" @click="backup">备份数据库</button>
        <button class="btn primary" @click="save">保存设置</button>
      </div>
    </div>

    <div v-if="probeResult" class="panel">
      <span :class="probeResult.ok ? 'tag green' : 'tag red'">
        {{ probeResult.ok ? `连接成功（${probeResult.latency_ms}ms）` : `连接失败：${probeResult.error}` }}
      </span>
    </div>

    <div v-for="g in visibleGroups" :key="g.id" class="panel">
      <h3>{{ g.label }}</h3>
      <div class="row">
        <template v-for="it in g.items" :key="it.key">
          <label v-if="it.type === 'bool'" class="field" style="min-width: 190px">
            <span class="lab">{{ it.label }}</span>
            <input v-model="values[it.key]" type="checkbox" />
            <span v-if="it.help" class="small muted">{{ it.help }}</span>
          </label>

          <label v-else-if="it.type === 'select'" class="field" style="min-width: 190px">
            <span class="lab">{{ it.label }}</span>
            <select v-model="values[it.key]">
              <option v-for="o in it.options" :key="o" :value="o">{{ o }}</option>
            </select>
            <span v-if="it.help" class="small muted">{{ it.help }}</span>
          </label>

          <label
            v-else-if="it.type === 'int' || it.type === 'float'"
            class="field"
            style="min-width: 190px"
          >
            <span class="lab">{{ it.label }}</span>
            <input
              v-model="values[it.key]"
              type="number"
              :step="it.type === 'float' ? 0.1 : 1"
              :min="it.min ?? undefined"
              :max="it.max ?? undefined"
            />
            <span v-if="it.help" class="small muted">{{ it.help }}</span>
          </label>

          <label v-else class="field grow" style="min-width: 260px">
            <span class="lab">{{ it.label }}（{{ it.type }}）</span>
            <input v-model="values[it.key]" />
            <span v-if="it.help" class="small muted">{{ it.help }}</span>
          </label>
        </template>
      </div>
    </div>

    <div class="panel">
      <h3>服务档案（G1 · 密钥明文可见，仅存 .env）</h3>
      <table>
        <thead><tr><th>名称</th><th>类型</th><th>base_url</th><th>密钥</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="p in profiles" :key="p.name">
            <td>{{ p.name }}</td>
            <td>{{ p.type }}</td>
            <td>{{ p.base_url }}</td>
            <td class="small">{{ p.api_key ? p.api_key.slice(0, 6) + "…" + p.api_key.slice(-4) : "未设置" }}</td>
            <td class="row">
              <button
                class="btn small"
                @click="
                  profileForm.name = p.name;
                  profileForm.base_url = p.base_url;
                  profileForm.type = p.type;
                "
              >
                载入
              </button>
              <button class="btn small danger" @click="deleteProfile(p.name)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="row" style="margin-top: 10px">
        <input v-model="profileForm.name" placeholder="档案名（如 default）" />
        <input v-model="profileForm.base_url" placeholder="http(s)://…/v1" class="grow" />
        <select v-model="profileForm.type">
          <option value="openai">openai</option>
          <option value="ollama">ollama</option>
          <option value="lmstudio">lmstudio</option>
        </select>
        <input v-model="profileForm.api_key" type="password" placeholder="API Key（写入 .env）" />
        <button class="btn primary" :disabled="!profileForm.name || !profileForm.base_url" @click="saveProfile">
          保存档案
        </button>
      </div>
    </div>

    <div class="panel">
      <h3>同义词组（G12 检索增强）</h3>
      <div v-for="(terms, group) in synonyms" :key="group" class="small">
        <span class="tag blue">{{ group }}</span>{{ terms.join("、") }}
      </div>
      <div class="row" style="margin-top: 8px">
        <input v-model="synForm.group" placeholder="组名（如：海边）" />
        <input v-model="synForm.terms" class="grow" placeholder="词条，逗号分隔（海、沙滩、海岸）" />
        <button class="btn small" :disabled="!synForm.group || !synForm.terms" @click="addSyn">添加</button>
      </div>
      <h3 style="margin-top: 12px">术语权重</h3>
      <div class="row">
        <span v-for="(w, t) in weights" :key="t" class="tag">{{ t }}×{{ w }}</span>
      </div>
      <div class="row" style="margin-top: 8px">
        <input v-model="weightForm.term" placeholder="术语" />
        <input v-model.number="weightForm.weight" type="number" step="0.1" style="width: 90px" />
        <button class="btn small" :disabled="!weightForm.term" @click="addWeight">设置权重</button>
      </div>
    </div>

    <div class="panel">
      <h3>审计与回滚（G16）</h3>
      <table>
        <thead><tr><th>#</th><th>键</th><th>动作</th><th>变更前</th><th>变更后</th><th>时间</th><th></th></tr></thead>
        <tbody>
          <tr v-for="a in auditItems" :key="a.id">
            <td>{{ a.id }}</td>
            <td>{{ a.key }}</td>
            <td>{{ a.action }}</td>
            <td class="small muted">{{ JSON.stringify(a.before) }}</td>
            <td class="small">{{ JSON.stringify(a.after) }}</td>
            <td class="small">{{ a.created_at }}</td>
            <td><button class="btn small" @click="rollback(a)">回滚</button></td>
          </tr>
        </tbody>
      </table>
      <div v-if="!auditItems.length" class="empty">暂无审计记录</div>
    </div>

    <div class="panel" style="border-color: var(--danger)">
      <h3 style="color: var(--danger)">危险操作（G10）</h3>
      <p class="small muted">清空索引：删除所有目录的图片记录与任务（源文件一律不动）。请输入「清空索引」确认。</p>
      <div class="row">
        <input v-model="dangerConfirm" placeholder="清空索引" />
        <button class="btn danger" :disabled="dangerConfirm !== '清空索引'" @click="clearIndex">
          清空索引
        </button>
      </div>
    </div>
  </div>
</template>

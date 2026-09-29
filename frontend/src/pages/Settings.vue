<script setup>
// 设置：schema 驱动渲染（新增配置项前端零改动）+ 外观 + 服务档案 + 审计回滚。
// 保存只提交脏值，避免一次微调把 92 项配置全写一遍审计。
import { computed, onMounted, reactive, ref } from "vue";

import { api } from "../app/api.js";
import {
  ACCENTS,
  MODULES,
  applyAppearance,
  dirtyCount,
  isDirty,
  loadSettings,
  rawValue,
  revertDirty,
  saveSettings,
  setSetting,
  settings,
  sidebarModules,
  stage,
} from "../app/settings.js";
import { notify } from "../app/toast.js";
import { datetime, maskKey, pretty, PROFILE_USAGE } from "../app/format.js";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import Panel from "../components/Panel.vue";
import SettingItem from "../components/SettingItem.vue";

const keyword = ref("");
const showAdvanced = ref(false);
const saving = ref(false);

const audit = ref([]);
const profiles = ref([]);
const showKeys = ref({});
const probe = ref(null);
const probeBusy = ref(false);
const usage = ref("vision");
const testForm = reactive({ base_url: "", api_key: "" });
const askDeleteProfile = ref(null);
const askRollback = ref(null);
const backupPath = ref("");

const profileForm = reactive({ name: "", type: "openai", base_url: "", api_key: "" });

const visibleGroups = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  return (settings.groups || [])
    .map((g) => ({
      ...g,
      items: g.items.filter((it) => {
        if (it.advanced && !showAdvanced.value) return false;
        if (!q) return true;
        return `${it.label}${it.key}${it.help || ""}`.toLowerCase().includes(q);
      }),
    }))
    .filter((g) => g.items.length);
});

const hiddenByAdvanced = computed(() =>
  (settings.groups || []).reduce(
    (acc, g) => acc + g.items.filter((it) => it.advanced && !showAdvanced.value).length,
    0,
  ),
);

const dangerGroups = computed(() => settings.dangerGroups || []);

// ---------------------------------------------------------------- 动作
async function save() {
  saving.value = true;
  await saveSettings();
  applyAppearance();
  saving.value = false;
}

function revert() {
  revertDirty();
  notify("已放弃未保存的修改", "ok");
}

async function setAppearance(key, value) {
  try {
    await setSetting(key, value);
    applyAppearance();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function loadSide() {
  await loadSettings({ quiet: true });
  profiles.value = settings.profiles || [];
  await loadAudit();
}

async function loadAudit() {
  try {
    audit.value = (await api.audit(60)).items || [];
  } catch {
    audit.value = [];
  }
}

async function testConnection() {
  probeBusy.value = true;
  probe.value = null;
  try {
    const payload = { usage: usage.value };
    if (testForm.base_url.trim()) payload.base_url = testForm.base_url.trim();
    if (testForm.api_key.trim()) payload.api_key = testForm.api_key.trim();
    probe.value = await api.testConnection(payload);
    notify(probe.value.ok ? "连接成功" : "连接失败", probe.value.ok ? "ok" : "error");
  } catch (e) {
    notify(e.message, "error");
  } finally {
    probeBusy.value = false;
  }
}

async function saveProfile() {
  if (!profileForm.name.trim() || !profileForm.base_url.trim()) {
    return notify("档案名与 base_url 都要填", "warn");
  }
  try {
    await api.saveProfile({ ...profileForm });
    notify(`档案「${profileForm.name}」已保存（密钥写进 .env）`, "ok");
    Object.assign(profileForm, { name: "", base_url: "", api_key: "" });
    await loadSettings({ quiet: true });
    profiles.value = settings.profiles || [];
  } catch (e) {
    notify(e.message, "error");
  }
}

async function confirmDeleteProfile() {
  const name = askDeleteProfile.value;
  try {
    await api.deleteProfile(name);
    notify(`档案「${name}」与它的密钥已删除`, "ok");
    askDeleteProfile.value = null;
    await loadSettings({ quiet: true });
    profiles.value = settings.profiles || [];
  } catch (e) {
    notify(e.message, "error");
  }
}

async function confirmRollback() {
  const a = askRollback.value;
  try {
    await api.rollback(a.id);
    notify(`已回滚 #${a.id}（${a.key}）`, "ok");
    askRollback.value = null;
    await loadSettings({ quiet: true });
    await loadAudit();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function backup() {
  try {
    const data = await api.backup();
    backupPath.value = data.path;
    notify(`备份完成：${data.path}`, "ok");
  } catch (e) {
    notify(e.message, "error");
  }
}

// ---------------------------------------------------------------- 侧栏模块
const moduleOrder = computed(() => sidebarModules.value.map((m) => m.key));
function toggleModule(key) {
  const next = new Set(moduleOrder.value);
  next.has(key) ? next.delete(key) : next.add(key);
  stage("sidebar_modules", MODULES.filter((m) => next.has(m.key)).map((m) => m.key));
}
function moveModule(key, delta) {
  const arr = [...moduleOrder.value];
  const i = arr.indexOf(key);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= arr.length) return;
  [arr[i], arr[j]] = [arr[j], arr[i]];
  stage("sidebar_modules", arr);
}

const currentAccent = computed(() => String(rawValue("accent") || "").toLowerCase());
const currentMode = computed(() => String(rawValue("theme") || "system"));
const currentDensity = computed(() => String(rawValue("card_density") || "comfortable"));
const cardSize = computed(() => Number(rawValue("thumb_size")) || 208);

onMounted(async () => {
  await loadSettings({ quiet: true });
  profiles.value = settings.profiles || [];
  await loadAudit();
});
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>设置</h1>
        <div class="sub">
          schema 驱动渲染：新增配置项前端零代码；密钥只存 .env，不进日志与导出
        </div>
      </div>
      <div class="head-actions">
        <span v-if="isDirty" class="tag tag-warn">{{ dirtyCount }} 项未保存</span>
        <button class="btn btn-sm" :disabled="!isDirty" @click="revert">放弃修改</button>
        <button class="btn btn-primary" :disabled="!isDirty || saving" @click="save">
          <span v-if="saving" class="spin"></span>
          保存设置
        </button>
      </div>
    </div>

    <!-- 外观 -->
    <Panel title="外观" subtitle="直接生效并写入后端配置（G8），刷新后保持">
      <div class="settings-grid">
        <div class="field">
          <span class="lab">模式</span>
          <div class="seg">
            <button :class="{ 'is-on': currentMode === 'light' }" @click="setAppearance('theme', 'light')">亮色</button>
            <button :class="{ 'is-on': currentMode === 'dark' }" @click="setAppearance('theme', 'dark')">暗色</button>
            <button :class="{ 'is-on': currentMode === 'system' }" @click="setAppearance('theme', 'system')">跟随系统</button>
          </div>
        </div>
        <div class="field">
          <span class="lab">强调色</span>
          <div class="row" style="gap: 6px">
            <button
              v-for="a in ACCENTS"
              :key="a.name"
              class="swatch"
              :class="{ 'is-on': currentAccent === a.color.toLowerCase() }"
              :style="{ background: a.color }"
              :title="a.label"
              @click="setAppearance('accent', a.color)"
            ></button>
            <input
              class="color-input"
              type="color"
              :value="currentAccent.startsWith('#') ? currentAccent : '#2563eb'"
              title="自定义强调色"
              @change="setAppearance('accent', $event.target.value)"
            />
          </div>
        </div>
        <div class="field">
          <span class="lab">卡片密度</span>
          <div class="seg">
            <button :class="{ 'is-on': currentDensity === 'comfortable' }" @click="setAppearance('card_density', 'comfortable')">宽松</button>
            <button :class="{ 'is-on': currentDensity === 'compact' }" @click="setAppearance('card_density', 'compact')">紧凑</button>
          </div>
        </div>
        <div class="field">
          <span class="lab">缩略图尺寸 {{ cardSize }}px</span>
          <input
            class="input"
            type="range"
            min="120"
            max="480"
            step="8"
            :value="cardSize"
            @change="setAppearance('thumb_size', Number($event.target.value))"
          />
        </div>
      </div>
    </Panel>

    <!-- 服务档案 -->
    <Panel title="服务档案" :count="profiles.length" subtitle="G1：密钥以明文存在 .env，界面上默认打码，可随时展开查看">
      <div class="stack-3">
        <div v-if="probe" class="banner" :class="probe.ok ? 'banner-ok' : 'banner-danger'">
          <Icon :name="probe.ok ? 'check' : 'warning'" :size="16" style="margin-top: 2px" />
          <div class="small">
            {{ probe.ok ? `连接成功（${probe.latency_ms}ms）` : `连接失败：${probe.error || '未知原因'}` }}
          </div>
        </div>

        <div class="row" style="gap: 8px">
          <select v-model="usage" class="select select-sm" style="width: 132px">
            <option v-for="u in PROFILE_USAGE" :key="u.value" :value="u.value">探测：{{ u.label }}</option>
          </select>
          <input v-model="testForm.base_url" class="input input-sm grow" style="min-width: 180px" placeholder="可选：临时指定 base_url" />
          <input v-model="testForm.api_key" class="input input-sm" style="width: 160px" placeholder="可选：临时指定 Key" />
          <button class="btn btn-sm" :disabled="probeBusy" @click="testConnection">
            <span v-if="probeBusy" class="spin"></span>
            连接探测
          </button>
        </div>

        <EmptyState v-if="!profiles.length" compact icon="cpu" title="还没有服务档案" hint="建一个档案（云端或本地 Ollama / LM Studio 都行），识图和嵌入才有地方跑。" />

        <div v-else class="table-wrap">
          <table class="table">
            <thead><tr><th>名称</th><th style="width: 96px">类型</th><th>base_url</th><th style="width: 168px">密钥</th><th style="width: 128px">操作</th></tr></thead>
            <tbody>
              <tr v-for="p in profiles" :key="p.name">
                <td class="strong">{{ p.name }}</td>
                <td class="small">{{ p.type }}</td>
                <td class="small wrap-anywhere mono">{{ p.base_url }}</td>
                <td class="small">
                  <span class="mono">{{ showKeys[p.name] ? p.api_key || "未设置" : maskKey(p.api_key) }}</span>
                  <button class="btn btn-xs" @click="showKeys[p.name] = !showKeys[p.name]">
                    {{ showKeys[p.name] ? "隐藏" : "显示" }}
                  </button>
                </td>
                <td>
                  <div class="row" style="gap: 4px">
                    <button
                      class="btn btn-xs"
                      @click="Object.assign(profileForm, { name: p.name, type: p.type, base_url: p.base_url, api_key: '' })"
                    >
                      载入
                    </button>
                    <button class="btn btn-xs btn-danger" @click="askDeleteProfile = p.name">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="row" style="gap: 8px">
          <input v-model="profileForm.name" class="input input-sm" style="width: 140px" placeholder="档案名" />
          <select v-model="profileForm.type" class="select select-sm" style="width: 112px">
            <option value="openai">openai</option>
            <option value="ollama">ollama</option>
            <option value="lmstudio">lmstudio</option>
          </select>
          <input v-model="profileForm.base_url" class="input input-sm grow" style="min-width: 180px" placeholder="http(s)://…/v1" />
          <input v-model="profileForm.api_key" class="input input-sm" style="width: 190px" type="password" placeholder="API Key（写入 .env）" />
          <button class="btn btn-sm btn-primary" @click="saveProfile">保存档案</button>
        </div>
        <div class="tiny dim">同名档案会被覆盖；留空密钥表示不改动已存的密钥。</div>
      </div>
    </Panel>

    <!-- schema 驱动 -->
    <Panel flush>
      <div class="row" style="padding: 12px var(--panel-pad); gap: 8px">
        <div class="searchbox grow" style="width: auto; max-width: 320px">
          <Icon name="search" :size="14" />
          <input v-model="keyword" placeholder="搜索配置项（名称 / key / 说明）" />
        </div>
        <label class="lab-check small">
          <input v-model="showAdvanced" class="checkbox" type="checkbox" />
          显示高级项
          <span v-if="hiddenByAdvanced && !showAdvanced" class="dim">（{{ hiddenByAdvanced }} 项已隐藏）</span>
        </label>
        <span class="spacer"></span>
        <span class="small dim">{{ visibleGroups.length }} / {{ (settings.groups || []).length }} 个分组匹配</span>
      </div>

      <div style="padding: 0 var(--panel-pad) 12px">
        <EmptyState v-if="!visibleGroups.length" compact icon="filter" title="没有匹配的配置项" hint="换个关键词，或者打开「显示高级项」。" />

        <div v-for="g in visibleGroups" :key="g.id" class="group">
          <div class="group-head">
            <span class="tag tag-outline">{{ g.id }}</span>
            <span class="strong">{{ g.label }}</span>
            <span class="small dim">{{ g.items.length }} 项</span>
            <span v-if="dangerGroups.includes(g.id)" class="tag tag-danger">危险</span>
          </div>
          <div class="settings-grid">
            <SettingItem
              v-for="it in g.items"
              :key="it.key"
              :item="it"
              :model-value="rawValue(it.key)"
              @update:model-value="(v) => stage(it.key, v)"
            />
          </div>
        </div>
      </div>
    </Panel>

    <!-- 侧栏模块 -->
    <Panel title="侧栏模块" subtitle="G17：勾选后保存，决定侧栏显示哪些模块与它们的顺序">
      <div class="stack-3">
        <div v-for="m in MODULES" :key="m.key" class="row-between small" style="padding: 4px 0; border-bottom: 1px solid var(--line)">
          <label class="lab-check">
            <input class="checkbox" type="checkbox" :checked="moduleOrder.includes(m.key)" @change="toggleModule(m.key)" />
            {{ m.label }}
            <span class="tiny dim">{{ m.group }}</span>
          </label>
          <div v-if="moduleOrder.includes(m.key)" class="row" style="gap: 4px">
            <button class="btn btn-xs" @click="moveModule(m.key, -1)">↑</button>
            <button class="btn btn-xs" @click="moveModule(m.key, 1)">↓</button>
          </div>
        </div>
      </div>
    </Panel>

    <!-- 审计 -->
    <Panel title="配置变更审计" :count="audit.length" subtitle="G16：记录每一次配置变更，可回滚到变更前的值">
      <template #actions>
        <button class="btn btn-xs" @click="loadAudit"><Icon name="refresh" :size="12" /></button>
      </template>
      <EmptyState v-if="!audit.length" compact icon="history" title="还没有审计记录" />
      <div v-else class="table-wrap">
        <table class="table">
          <thead><tr><th style="width: 62px">#</th><th style="width: 180px">键</th><th style="width: 120px">动作</th><th>变更前 → 变更后</th><th style="width: 150px">时间</th><th style="width: 76px"></th></tr></thead>
          <tbody>
            <tr v-for="a in audit" :key="a.id">
              <td class="mono dim">{{ a.id }}</td>
              <td class="mono small wrap-anywhere">{{ a.key }}</td>
              <td class="small">{{ a.action }}</td>
              <td class="small wrap-anywhere">
                <span class="dim">{{ pretty(a.before) }}</span>
                <Icon name="chevronRight" :size="11" class="dim" />
                <span class="strong">{{ pretty(a.after) }}</span>
              </td>
              <td class="small dim nowrap">{{ datetime(a.created_at) }}</td>
              <td><button class="btn btn-xs" @click="askRollback = a">回滚</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>

    <!-- 备份 -->
    <Panel title="维护" subtitle="备份会把数据库复制一份到 data/backups">
      <div class="row">
        <button class="btn" @click="backup"><Icon name="save" :size="14" /> 备份数据库</button>
        <span v-if="backupPath" class="small mono dim">{{ backupPath }}</span>
      </div>
    </Panel>

    <ConfirmDialog
      :open="Boolean(askDeleteProfile)"
      title="删除服务档案"
      :message="`删除档案「${askDeleteProfile}」以及存在 .env 里的密钥？`"
      :details="['正在使用该档案的用途会回退到 default 档案', '如果 default 也没有，识图会停止排队']"
      confirm-text="确认删除"
      danger
      @close="askDeleteProfile = null"
      @confirm="confirmDeleteProfile"
    />

    <ConfirmDialog
      :open="Boolean(askRollback)"
      title="回滚配置"
      :message="`把 ${askRollback?.key} 回滚到 #${askRollback?.id} 之前的值？`"
      :details="['回滚本身也会记一条审计', '不会重新触发 AI 调用']"
      confirm-text="确认回滚"
      icon="retry"
      @close="askRollback = null"
      @confirm="confirmRollback"
    />
  </div>
</template>

<style scoped>
.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: var(--sp-3) var(--sp-4);
}
.group {
  border-top: 1px solid var(--line);
  padding-top: var(--sp-3);
  margin-top: var(--sp-3);
}
.group:first-child {
  border-top: 0;
  padding-top: 0;
  margin-top: 0;
}
.group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: var(--sp-3);
  flex-wrap: wrap;
}
.swatch {
  width: 24px;
  height: 24px;
  border-radius: 8px;
  border: 2px solid transparent;
  box-shadow: 0 0 0 1px var(--line-strong);
  cursor: pointer;
  padding: 0;
}
.swatch.is-on {
  border-color: var(--surface);
  box-shadow: 0 0 0 2px var(--accent);
}
</style>

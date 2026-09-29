<script setup>
// 分类与字段：分类字典、自定义字段、同义词组、术语权重。
// 这四个东西后端早就有了，本轮把它们做成界面——之前只能改数据库或用 curl 才碰得到。
import { computed, onMounted, reactive, ref } from "vue";

import { api } from "../app/api.js";
import { catalog, loadCatalog, upsertCategory, dropCategory } from "../app/catalog.js";
import { notify } from "../app/toast.js";
import { FIELD_TYPES } from "../app/format.js";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import Panel from "../components/Panel.vue";
import TagInput from "../components/TagInput.vue";

const loading = ref(true);
const askDeleteCat = ref(null);
const askDeleteField = ref(null);

const catForm = reactive({ name: "", color: "#64748b", emoji: "", editName: "" });
const fieldForm = reactive({ name: "", type: "text", options: [] });
const synForm = reactive({ group: "", terms: [] });
const weightForm = reactive({ term: "", weight: 1.0 });
const synonyms = ref({});
const weights = ref({});

const sorted = computed(() => [...catalog.categories].sort((a, b) => (a.sort || 0) - (b.sort || 0)));

async function load() {
  loading.value = true;
  try {
    await loadCatalog({ force: true });
    await loadEnhance();
  } finally {
    loading.value = false;
  }
}

async function loadEnhance() {
  try {
    synonyms.value = (await api.synonyms()).groups || {};
    weights.value = (await api.termWeights()).weights || {};
  } catch (e) {
    notify(e.message, "error");
  }
}

async function addCategory() {
  if (!catForm.name.trim()) return notify("分类名不能为空", "warn");
  try {
    await api.addCategory({ name: catForm.name.trim(), color: catForm.color, emoji: catForm.emoji.trim() });
    notify(`分类「${catForm.name.trim()}」已创建`, "ok");
    catForm.name = "";
    catForm.emoji = "";
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

function startEditCategory(c) {
  catForm.editName = c.name;
  catForm.name = c.name;
  catForm.color = c.color || "#64748b";
  catForm.emoji = c.emoji || "";
}

async function saveCategory() {
  const oldName = catForm.editName;
  if (!oldName) return;
  try {
    const row = await api.patchCategory(oldName, {
      name: catForm.name.trim() || oldName,
      color: catForm.color,
      emoji: catForm.emoji.trim(),
    });
    if (oldName !== row.name) dropCategory(oldName);
    upsertCategory(row);
    notify(oldName !== row.name ? `已改名：${oldName} → ${row.name}（图片分类会级联跟随）` : "分类已更新", "ok");
    catForm.editName = "";
    catForm.name = "";
    catForm.emoji = "";
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function toggleCategory(c) {
  try {
    const row = await api.patchCategory(c.name, { active: c.active ? 0 : 1 });
    upsertCategory(row);
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function confirmDeleteCategory() {
  const c = askDeleteCat.value;
  try {
    await api.deleteCategory(c.name);
    notify(`分类「${c.name}」已停用（内置分类不可删，实际操作是置为停用）`, "ok");
    askDeleteCat.value = null;
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function addField() {
  if (!fieldForm.name.trim()) return notify("字段名不能为空", "warn");
  try {
    await api.addCustomField({
      name: fieldForm.name.trim(),
      type: fieldForm.type,
      options: fieldForm.options,
    });
    notify(`字段「${fieldForm.name.trim()}」已创建`, "ok");
    fieldForm.name = "";
    fieldForm.options = [];
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function confirmDeleteField() {
  const f = askDeleteField.value;
  try {
    await api.deleteCustomField(f.id);
    notify(`字段「${f.name}」已删除`, "ok");
    askDeleteField.value = null;
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function addSynonyms() {
  if (!synForm.group.trim() || !synForm.terms.length) return notify("组名和词条都要填", "warn");
  try {
    await api.putSynonyms(synForm.group.trim(), [...synForm.terms]);
    notify(`同义词组「${synForm.group.trim()}」已保存`, "ok");
    synForm.group = "";
    synForm.terms = [];
    await loadEnhance();
  } catch (e) {
    notify(e.message, "error");
  }
}

function editSynonym(group) {
  synForm.group = group;
  synForm.terms = [...(synonyms.value[group] || [])];
}

async function addWeight() {
  if (!weightForm.term.trim()) return notify("术语不能为空", "warn");
  try {
    await api.putTermWeight(weightForm.term.trim(), Number(weightForm.weight) || 1);
    notify(`术语「${weightForm.term.trim()}」权重已设为 ${weightForm.weight}`, "ok");
    weightForm.term = "";
    await loadEnhance();
  } catch (e) {
    notify(e.message, "error");
  }
}

const EMOJI_SUGGEST = ["🏖️", "🌅", "👤", "🐱", "🐶", "🍜", "📱", "🖼️", "🏠", "🌳", "🚗", "📄", "🎮", "✈️"];

onMounted(load);
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>分类与字段</h1>
        <div class="sub">分类字典、自定义字段，以及检索增强用的同义词与术语权重</div>
      </div>
      <div class="head-actions">
        <button class="btn btn-sm" :disabled="loading" @click="load">
          <Icon name="refresh" :size="13" /> 刷新
        </button>
      </div>
    </div>

    <!-- 分类字典 -->
    <Panel title="分类字典" :count="sorted.length" subtitle="内置分类不可改删；改名会级联更新所有图片的该分类" collapsible>
      <div class="stack-3">
        <div class="row" style="gap: 8px">
          <input v-model="catForm.name" class="input" style="flex: 1 1 160px" placeholder="新分类名，如：截图" />
          <input v-model="catForm.emoji" class="input" style="width: 76px" placeholder="emoji" :list="'emoji-list'" />
          <datalist id="emoji-list">
            <option v-for="e in EMOJI_SUGGEST" :key="e" :value="e" />
          </datalist>
          <input v-model="catForm.color" class="color-input" type="color" title="标记色" />
          <button v-if="!catForm.editName" class="btn" @click="addCategory">
            <Icon name="plus" :size="13" /> 新建分类
          </button>
          <template v-else>
            <button class="btn btn-primary" @click="saveCategory">保存修改</button>
            <button class="btn" @click="catForm.editName = ''; catForm.name = ''; catForm.emoji = ''">取消</button>
          </template>
        </div>

        <EmptyState v-if="!sorted.length" compact icon="tag" title="还没有分类" />
        <div v-else class="cat-grid">
          <div v-for="c in sorted" :key="c.id" class="cat-row">
            <span class="cat-dot" :style="{ background: c.color || 'var(--text-3)' }"></span>
            <span class="strong clamp-1">{{ c.emoji }} {{ c.name }}</span>
            <span v-if="c.builtin" class="tag tag-outline" title="内置分类：不可改名、不可删除">
              <Icon name="lock" :size="11" /> 内置
            </span>
            <span v-if="!c.active" class="tag tag-warn">已停用</span>
            <span class="spacer"></span>
            <button v-if="!c.builtin" class="btn btn-xs" @click="startEditCategory(c)">编辑</button>
            <button class="btn btn-xs" @click="toggleCategory(c)">{{ c.active ? "停用" : "启用" }}</button>
            <button v-if="!c.builtin" class="btn btn-xs btn-danger" @click="askDeleteCat = c">删除</button>
          </div>
        </div>
        <div class="tiny dim">
          删除其实是「停用」：已经在图片上的分类不会被改写，只是不再出现在可选列表里。
        </div>
      </div>
    </Panel>

    <!-- 自定义字段 -->
    <Panel title="自定义字段" :count="catalog.customFields.length" subtitle="字段会在图片详情里出现，可填写并参与人工修正" collapsible>
      <div class="stack-3">
        <div class="row" style="gap: 8px">
          <input v-model="fieldForm.name" class="input" style="flex: 1 1 150px" placeholder="字段名，如：拍摄设备" />
          <select v-model="fieldForm.type" class="select" style="width: 108px">
            <option v-for="t in FIELD_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
          <button class="btn" @click="addField"><Icon name="plus" :size="13" /> 新建字段</button>
        </div>
        <div v-if="fieldForm.type === 'select'" class="field">
          <span class="lab">可选值</span>
          <TagInput v-model="fieldForm.options" placeholder="回车添加选项" />
        </div>

        <EmptyState v-if="!catalog.customFields.length" compact icon="file" title="还没有自定义字段" />
        <div v-else class="table-wrap">
          <table class="table">
            <thead><tr><th style="width: 60px">#</th><th>名称</th><th style="width: 100px">类型</th><th>可选值</th><th style="width: 88px">操作</th></tr></thead>
            <tbody>
              <tr v-for="f in catalog.customFields" :key="f.id">
                <td class="mono dim">{{ f.id }}</td>
                <td class="strong">{{ f.name }}</td>
                <td class="small">{{ f.type }}</td>
                <td class="small">
                  <span v-for="o in f.options || []" :key="o" class="tag tag-outline" style="margin-right: 4px">{{ o }}</span>
                  <span v-if="!(f.options || []).length" class="dim">—</span>
                </td>
                <td><button class="btn btn-xs btn-danger" @click="askDeleteField = f">删除</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </Panel>

    <!-- 检索增强 -->
    <Panel title="同义词组" :count="Object.keys(synonyms).length" subtitle="检索时把同义的词一起展开，提升召回" collapsible>
      <div class="stack-3">
        <div v-for="(terms, group) in synonyms" :key="group" class="row-between small" style="padding: 4px 0; border-bottom: 1px solid var(--line)">
          <span class="row" style="gap: 6px; flex: 1; min-width: 0">
            <span class="tag tag-accent">{{ group }}</span>
            <span class="wrap-anywhere">{{ terms.join("、") }}</span>
          </span>
          <button class="btn btn-xs" @click="editSynonym(group)">编辑</button>
        </div>
        <div v-if="!Object.keys(synonyms).length" class="small dim">还没有同义词组</div>
        <div class="row" style="gap: 8px; align-items: flex-start">
          <input v-model="synForm.group" class="input" style="width: 150px" placeholder="组名，如：海边" />
          <div style="flex: 1 1 240px; min-width: 200px">
            <TagInput v-model="synForm.terms" placeholder="词条，回车添加：海、沙滩、海岸" />
          </div>
          <button class="btn" @click="addSynonyms"><Icon name="save" :size="13" /> 保存</button>
        </div>
      </div>
    </Panel>

    <Panel title="术语权重" :count="Object.keys(weights).length" subtitle="给某些词加重，让它在融合排序里更靠前" collapsible>
      <div class="stack-3">
        <div class="row" style="gap: 6px">
          <span v-for="(w, t) in weights" :key="t" class="tag tag-outline">{{ t }} × {{ w }}</span>
          <span v-if="!Object.keys(weights).length" class="small dim">还没有设置权重</span>
        </div>
        <div class="row" style="gap: 8px">
          <input v-model="weightForm.term" class="input" style="width: 160px" placeholder="术语，如：猫" />
          <input v-model.number="weightForm.weight" class="input" style="width: 92px" type="number" step="0.1" />
          <button class="btn" @click="addWeight"><Icon name="save" :size="13" /> 设置</button>
          <span class="small dim">默认权重 1.0，调大让该词更占优</span>
        </div>
      </div>
    </Panel>

    <ConfirmDialog
      :open="Boolean(askDeleteCat)"
      title="删除分类"
      :message="`停用分类「${askDeleteCat?.name}」？`"
      :details="['已经打在图片上的这个分类不会被改写', '图片详情里仍可能看到该分类名']"
      confirm-text="确认停用"
      danger
      @close="askDeleteCat = null"
      @confirm="confirmDeleteCategory"
    />

    <ConfirmDialog
      :open="Boolean(askDeleteField)"
      title="删除自定义字段"
      :message="`删除字段「${askDeleteField?.name}」？`"
      :details="['所有图片上填写的该字段值会一并删除', '此操作不可撤销']"
      confirm-text="确认删除"
      danger
      @close="askDeleteField = null"
      @confirm="confirmDeleteField"
    />
  </div>
</template>

<style scoped>
.cat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px;
}
.cat-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface-inset);
  min-width: 0;
}
.cat-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex: none;
}
</style>

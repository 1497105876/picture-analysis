<script setup>
import { onMounted, reactive, ref } from "vue";
import { api, notify } from "../api.js";

const rules = ref([]);
const form = reactive({
  name: "",
  priority: 0,
  enabled: true,
  target: "dir_prefix",
  op: "contains",
  value: "",
  set_category: "",
  add_tags: "",
  add_to_album: "",
});
const editingId = ref(null);
const trial = ref(null);

async function load() {
  rules.value = (await api.get("/api/rules")).items || [];
}

function condition() {
  return { target: form.target, op: form.op, value: form.value };
}

function action() {
  const out = {};
  if (form.set_category) out.set_category = form.set_category;
  if (form.add_tags) out.add_tags = form.add_tags.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
  if (form.add_to_album) out.add_to_album = form.add_to_album;
  return out;
}

async function save() {
  const payload = {
    name: form.name || "未命名规则",
    priority: Number(form.priority) || 0,
    enabled: form.enabled,
    condition: condition(),
    action: action(),
  };
  if (!payload.action.set_category && !payload.action.add_tags?.length && !payload.action.add_to_album) {
    return notify("动作至少填一项", "warn");
  }
  try {
    if (editingId.value) {
      await api.patch(`/api/rules/${editingId.value}`, payload);
      notify("已更新");
    } else {
      await api.post("/api/rules", payload);
      notify("已创建");
    }
    reset();
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

function edit(r) {
  editingId.value = r.id;
  form.name = r.name;
  form.priority = r.priority;
  form.enabled = Boolean(r.enabled);
  form.target = r.condition?.target || "dir_prefix";
  form.op = r.condition?.op || "contains";
  form.value = r.condition?.value || "";
  form.set_category = r.action?.set_category || "";
  form.add_tags = (r.action?.add_tags || []).join(", ");
  form.add_to_album = r.action?.add_to_album || "";
}

function reset() {
  editingId.value = null;
  Object.assign(form, {
    name: "",
    priority: 0,
    enabled: true,
    target: "dir_prefix",
    op: "contains",
    value: "",
    set_category: "",
    add_tags: "",
    add_to_album: "",
  });
}

async function remove(r) {
  if (!window.confirm(`删除规则「${r.name}」？`)) return;
  try {
    await api.del(`/api/rules/${r.id}`);
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function tryRun() {
  try {
    trial.value = await api.post("/api/rules/try", { condition: condition(), limit: 50 });
  } catch (e) {
    notify(e.message, "error");
  }
}

async function recompute(phase) {
  try {
    const data = await api.post("/api/rules/recompute", { phase });
    notify(`${phase} 阶段补算命中 ${data.applied} 张`);
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
        <h1>分类规则</h1>
        <div class="sub">IF 条件 → THEN 动作，按优先级首条命中即停；改规则永不触发 AI 外发</div>
      </div>
      <div class="row">
        <button class="btn" @click="recompute('pre')">补算 pre 阶段</button>
        <button class="btn" @click="recompute('ocr')">补算 ocr 阶段</button>
      </div>
    </div>

    <div class="panel">
      <h3>{{ editingId ? "编辑规则" : "新建规则" }}</h3>
      <div class="row">
        <input v-model="form.name" placeholder="规则名" />
        <label class="small">优先级 <input v-model.number="form.priority" type="number" style="width: 70px" /></label>
        <label class="small"><input v-model="form.enabled" type="checkbox" /> 启用</label>
      </div>
      <div class="row" style="margin-top: 8px">
        <select v-model="form.target">
          <option value="dir_prefix">目录前缀</option>
          <option value="dir_suffix">路径包含</option>
          <option value="filename">文件名</option>
          <option value="ocr_text">OCR 文本</option>
          <option value="category">分类</option>
        </select>
        <select v-model="form.op">
          <option value="contains">包含</option>
          <option value="equals">等于</option>
          <option value="startswith">开头是</option>
          <option value="endswith">结尾是</option>
          <option value="regex">正则</option>
        </select>
        <input v-model="form.value" class="grow" placeholder="匹配值，如 screenshots 或 [Ss]creenshot" />
      </div>
      <div class="row" style="margin-top: 8px">
        <input v-model="form.set_category" placeholder="设分类为…" />
        <input v-model="form.add_tags" placeholder="追加标签，逗号分隔" />
        <input v-model="form.add_to_album" placeholder="加入相册 album:名" />
        <button class="btn" @click="tryRun">试跑预览</button>
        <button class="btn primary" @click="save">{{ editingId ? "保存" : "创建" }}</button>
        <button v-if="editingId" class="btn" @click="reset">取消</button>
      </div>

      <div v-if="trial" class="panel" style="background: var(--panel-2); margin-top: 10px">
        <div class="small">试跑命中 {{ trial.count }} 张（扫描 {{ trial.scanned }} 张，不落库）</div>
        <div class="small muted">
          <span v-for="m in trial.matches.slice(0, 12)" :key="m.id">#{{ m.id }} {{ m.path }}；</span>
        </div>
      </div>
    </div>

    <div class="panel">
      <h3>规则列表</h3>
      <table>
        <thead><tr><th>#</th><th>名称</th><th>条件</th><th>动作</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="r in rules" :key="r.id">
            <td>{{ r.priority }}</td>
            <td>{{ r.name }}</td>
            <td class="small">{{ r.condition?.target }} {{ r.condition?.op }} 「{{ r.condition?.value }}」</td>
            <td class="small">
              {{ r.action?.set_category ? "分类→" + r.action.set_category + " " : "" }}
              {{ r.action?.add_tags?.length ? "标签+" + r.action.add_tags.join("/") : "" }}
              {{ r.action?.add_to_album ? "相册→" + r.action.add_to_album : "" }}
            </td>
            <td><span class="tag" :class="r.enabled ? 'green' : 'red'">{{ r.enabled ? "启用" : "停用" }}</span></td>
            <td class="row">
              <button class="btn small" @click="edit(r)">编辑</button>
              <button class="btn small danger" @click="remove(r)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!rules.length" class="empty">暂无规则</div>
    </div>
  </div>
</template>

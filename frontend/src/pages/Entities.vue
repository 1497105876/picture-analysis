<script setup>
import { onMounted, reactive, ref } from "vue";
import { api, notify } from "../api.js";

const items = ref([]);
const detail = ref(null);
const form = reactive({ name: "", category: "", description: "", aliases: "" });
const editingId = ref(null);
const refPath = ref("");
const linkImageId = ref("");
const includeInactive = ref(0);

async function load() {
  items.value =
    (await api.get("/api/entities", { include_inactive: includeInactive.value })).items || [];
}

async function open(e) {
  detail.value = await api.get(`/api/entities/${e.id}`);
}

async function save() {
  const payload = {
    name: form.name,
    category: form.category,
    description: form.description,
    aliases: form.aliases.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
  };
  try {
    if (editingId.value) {
      await api.patch(`/api/entities/${editingId.value}`, payload);
      notify("已更新");
    } else {
      await api.post("/api/entities", payload);
      notify("已创建");
    }
    reset();
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

function edit(e) {
  editingId.value = e.id;
  form.name = e.name;
  form.category = e.category || "";
  form.description = e.description || "";
  form.aliases = (e.aliases || []).join(", ");
}

function reset() {
  editingId.value = null;
  Object.assign(form, { name: "", category: "", description: "", aliases: "" });
}

async function remove(e) {
  if (!window.confirm(`删除实体「${e.name}」？`)) return;
  try {
    await api.del(`/api/entities/${e.id}`);
    if (detail.value?.id === e.id) detail.value = null;
    await load();
  } catch (err) {
    notify(err.message, "error");
  }
}

async function addRef() {
  try {
    detail.value = await api.post(`/api/entities/${detail.value.id}/references`, {
      path: refPath.value,
    });
    refPath.value = "";
  } catch (e) {
    notify(e.message, "error");
  }
}

async function delRef(r) {
  try {
    detail.value = await api.del(`/api/entities/${detail.value.id}/references/${r.id}`);
  } catch (e) {
    notify(e.message, "error");
  }
}

async function link() {
  try {
    await api.post(`/api/entities/${detail.value.id}/link`, { image_id: Number(linkImageId.value) });
    linkImageId.value = "";
    detail.value = await api.get(`/api/entities/${detail.value.id}`);
  } catch (e) {
    notify(e.message, "error");
  }
}

async function unlink(id) {
  try {
    await api.del(`/api/entities/${detail.value.id}/link/${id}`);
    detail.value = await api.get(`/api/entities/${detail.value.id}`);
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
        <h1>实体资料库</h1>
        <div class="sub">识图提示词注入人物/宠物/地点信息（每图最多 3 个高相关实体）</div>
      </div>
      <label class="small"><input v-model.number="includeInactive" type="checkbox" :value="1" @change="load" /> 含停用</label>
    </div>

    <div class="panel">
      <h3>{{ editingId ? "编辑实体" : "新建实体" }}</h3>
      <div class="row">
        <input v-model="form.name" placeholder="名称（如：家里的猫）" />
        <input v-model="form.category" placeholder="分类（如：宠物）" />
        <input v-model="form.aliases" class="grow" placeholder="别名，逗号分隔" />
      </div>
      <label class="field" style="margin-top: 8px"
        ><span class="lab">描述（会注入识图提示词）</span>
        <textarea v-model="form.description" rows="2"></textarea>
      </label>
      <div class="row">
        <button class="btn primary" @click="save">{{ editingId ? "保存" : "创建" }}</button>
        <button v-if="editingId" class="btn" @click="reset">取消</button>
      </div>
    </div>

    <div class="panel">
      <h3>实体列表</h3>
      <table>
        <thead><tr><th>名称</th><th>分类</th><th>别名</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="e in items" :key="e.id">
            <td>{{ e.name }}</td>
            <td>{{ e.category || "—" }}</td>
            <td class="small">{{ (e.aliases || []).join("、") || "—" }}</td>
            <td>
              <span class="tag" :class="e.active ? 'green' : 'red'">{{ e.active ? "启用" : "停用" }}</span>
            </td>
            <td class="row">
              <button class="btn small" @click="open(e)">详情</button>
              <button class="btn small" @click="edit(e)">编辑</button>
              <button class="btn small danger" @click="remove(e)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!items.length" class="empty">还没有实体</div>
    </div>

    <div v-if="detail" class="panel">
      <h3>{{ detail.name }} 详情</h3>
      <p class="small muted">{{ detail.description || "（无描述）" }}</p>

      <div class="panel" style="background: var(--panel-2)">
        <h3>参考图路径（每实体 ≤5 张）</h3>
        <div v-for="r in detail.references || []" :key="r.id" class="row small">
          <span class="grow">{{ r.path }}</span>
          <button class="btn small danger" @click="delRef(r)">移除</button>
        </div>
        <div class="row" style="margin-top: 8px">
          <input v-model="refPath" class="grow" placeholder="绝对路径，如 D:\ref\cat1.jpg" />
          <button class="btn small" @click="addRef">添加参考图</button>
        </div>
      </div>

      <div class="panel" style="background: var(--panel-2)">
        <h3>已关联图片</h3>
        <div class="row">
          <span v-for="id in detail.linked_image_ids || []" :key="id" class="tag blue">
            #{{ id }}
            <a style="cursor: pointer" @click="unlink(id)">×</a>
          </span>
        </div>
        <div class="row" style="margin-top: 8px">
          <input v-model="linkImageId" placeholder="图片 ID" style="width: 110px" />
          <button class="btn small" @click="link">关联</button>
        </div>
      </div>
    </div>
  </div>
</template>

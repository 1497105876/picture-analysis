<script setup>
// 实体资料库：识别时按「手动关联 / 别名硬匹配 / 向量 Top3」三路注入人物、宠物、地点信息。
import { computed, onMounted, reactive, ref } from "vue";

import { api, thumbUrl } from "../app/api.js";
import { notify } from "../app/toast.js";
import { safe } from "../app/api.js";
import { datetime } from "../app/format.js";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import ImageDrawer from "../components/ImageDrawer.vue";
import Panel from "../components/Panel.vue";
import TagInput from "../components/TagInput.vue";

const items = ref([]);
const detail = ref(null);
const linkedImages = ref([]);
const includeInactive = ref(false);
const keyword = ref("");
const askDelete = ref(null);

const form = reactive({ name: "", category: "", description: "", aliases: [] });
const editingId = ref(null);
const refPath = ref("");
const linkId = ref("");
const busy = ref(false);
const openImageId = ref(null);

const filtered = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  const base = q
    ? items.value.filter(
        (e) =>
          e.name.toLowerCase().includes(q) ||
          (e.category || "").toLowerCase().includes(q) ||
          (e.aliases || []).some((a) => a.toLowerCase().includes(q)),
      )
    : items.value;
  return base;
});

async function load() {
  try {
    items.value = (await api.entities(includeInactive.value)).items || [];
  } catch (e) {
    notify(e.message, "error");
  }
}

async function openDetail(e) {
  try {
    detail.value = await api.entity(e.id);
    editingId.value = null;
    Object.assign(form, {
      name: detail.value.name || "",
      category: detail.value.category || "",
      description: detail.value.description || "",
      aliases: [...(detail.value.aliases || [])],
    });
    await loadLinked();
  } catch (err) {
    notify(err.message, "error");
  }
}

async function loadLinked() {
  const ids = (detail.value?.linked_image_ids || []).slice(0, 12);
  linkedImages.value = (
    await Promise.all(ids.map((id) => safe(() => api.imageDetail(id), null, { silent: true })))
  ).filter(Boolean);
}

async function save() {
  if (!form.name.trim()) return notify("名称不能为空", "warn");
  busy.value = true;
  try {
    const payload = {
      name: form.name.trim(),
      category: form.category,
      description: form.description,
      aliases: [...form.aliases],
    };
    if (editingId.value) {
      await api.patchEntity(editingId.value, payload);
      notify("实体已更新", "ok");
    } else {
      await api.addEntity(payload);
      notify("实体已创建", "ok");
    }
    reset();
    await load();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

function edit(e) {
  editingId.value = e.id;
  Object.assign(form, {
    name: e.name,
    category: e.category || "",
    description: e.description || "",
    aliases: [...(e.aliases || [])],
  });
  detail.value = null;
}

function reset() {
  editingId.value = null;
  Object.assign(form, { name: "", category: "", description: "", aliases: [] });
}

async function toggleActive(e) {
  try {
    await api.patchEntity(e.id, { active: e.active ? 0 : 1 });
    await load();
    if (detail.value?.id === e.id) detail.value = await api.entity(e.id);
  } catch (err) {
    notify(err.message, "error");
  }
}

async function confirmDelete() {
  const e = askDelete.value;
  try {
    await api.deleteEntity(e.id);
    notify(`实体「${e.name}」已删除`, "ok");
    askDelete.value = null;
    if (detail.value?.id === e.id) {
      detail.value = null;
      linkedImages.value = [];
    }
    await load();
  } catch (err) {
    notify(err.message, "error");
  }
}

async function addRef() {
  if (!refPath.value.trim()) return;
  try {
    detail.value = await api.addReference(detail.value.id, refPath.value.trim());
    refPath.value = "";
    notify("参考图已添加", "ok");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function delRef(r) {
  try {
    detail.value = await api.removeReference(detail.value.id, r.id);
  } catch (e) {
    notify(e.message, "error");
  }
}

async function link() {
  const id = Number(linkId.value);
  if (!id) return notify("填一个图片 ID", "warn");
  try {
    await api.linkEntity(detail.value.id, id);
    linkId.value = "";
    detail.value = await api.entity(detail.value.id);
    await loadLinked();
    notify("已关联", "ok");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function unlink(id) {
  try {
    await api.unlinkEntity(detail.value.id, id);
    detail.value = await api.entity(detail.value.id);
    await loadLinked();
    notify("已取消关联", "ok");
  } catch (e) {
    notify(e.message, "error");
  }
}

onMounted(load);
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>实体资料库</h1>
        <div class="sub">
          识图时把人物/宠物/地点的特征注入提示词：每图最多 3 个实体、每实体最多 2 张参考图、总计不超过 6 张
        </div>
      </div>
      <div class="head-actions">
        <input v-model="keyword" class="input input-sm" style="width: 170px" placeholder="搜索名称/别名" />
        <label class="lab-check small">
          <input v-model="includeInactive" class="checkbox" type="checkbox" @change="load" /> 含停用
        </label>
        <button class="btn btn-sm" @click="load"><Icon name="refresh" :size="13" /></button>
      </div>
    </div>

    <div class="entities">
      <!-- 列表 -->
      <Panel :count="filtered.length" title="实体列表">
        <EmptyState
          v-if="!filtered.length"
          compact
          icon="user"
          :title="keyword ? '没有匹配的实体' : '还没有实体'"
          :hint="keyword ? '换个关键词' : '建一个常出现的人物/宠物/地点，识别准确率会明显提高。'"
        />
        <div v-else class="table-wrap">
          <table class="table">
            <thead>
              <tr><th>名称</th><th>分类</th><th>别名</th><th style="width: 76px">状态</th><th style="width: 150px">操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="e in filtered" :key="e.id" :class="{ 'is-active': detail?.id === e.id }">
                <td class="strong">{{ e.name }}</td>
                <td class="small">{{ e.category || "—" }}</td>
                <td class="small">
                  <span v-for="a in e.aliases || []" :key="a" class="tag tag-outline" style="margin-right: 4px">{{ a }}</span>
                  <span v-if="!(e.aliases || []).length" class="dim">—</span>
                </td>
                <td>
                  <span class="tag" :class="e.active ? 'tag-ok' : 'tag-outline'">{{ e.active ? "启用" : "停用" }}</span>
                </td>
                <td>
                  <div class="row" style="gap: 4px">
                    <button class="btn btn-xs" @click="openDetail(e)">详情</button>
                    <button class="btn btn-xs" @click="edit(e)">编辑</button>
                    <button class="btn btn-xs" @click="toggleActive(e)">{{ e.active ? "停用" : "启用" }}</button>
                    <button class="btn btn-xs btn-danger" @click="askDelete = e">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>

      <!-- 表单 -->
      <Panel :title="editingId ? '编辑实体' : '新建实体'">
        <div class="stack-3">
          <div class="row" style="gap: 8px">
            <input v-model="form.name" class="input" style="flex: 1 1 180px" placeholder="名称，如：家里的猫" />
            <input v-model="form.category" class="input" style="flex: 0 1 130px" placeholder="分类，如：宠物" />
          </div>
          <div class="field">
            <span class="lab">别名（命中文件名/路径即注入）</span>
            <TagInput v-model="form.aliases" placeholder="回车添加，如：咪咪" />
          </div>
          <label class="field">
            <span class="lab">描述（会原文注入识图提示词）</span>
            <textarea v-model="form.description" class="textarea" rows="3" placeholder="橘猫，左耳有缺口，喜欢趴在键盘上"></textarea>
          </label>
          <div class="row">
            <button class="btn btn-primary" :disabled="busy" @click="save">
              <span v-if="busy" class="spin"></span>
              {{ editingId ? "保存修改" : "创建实体" }}
            </button>
            <button v-if="editingId" class="btn" @click="reset">取消</button>
          </div>
        </div>
      </Panel>
    </div>

    <!-- 详情 -->
    <Panel v-if="detail" :title="`${detail.name} · 详情`" :subtitle="`创建于 ${datetime(detail.created_at)}`">
      <div class="entities">
        <div class="stack-3">
          <div>
            <h4>参考图（≤ 2 张/实体）</h4>
            <div v-for="r in detail.reference_images || []" :key="r.id" class="row-between small" style="padding: 4px 0; border-bottom: 1px solid var(--line)">
              <span class="mono wrap-anywhere" style="flex: 1">{{ r.path }}</span>
              <button class="btn btn-xs btn-danger" @click="delRef(r)">移除</button>
            </div>
            <div v-if="!(detail.reference_images || []).length" class="small dim" style="padding: 6px 0">
              还没有参考图
            </div>
            <div class="row" style="margin-top: 8px">
              <input v-model="refPath" class="input input-sm grow" placeholder="绝对路径，如 D:\ref\cat1.jpg" />
              <button class="btn btn-sm" @click="addRef">添加</button>
            </div>
            <div class="tiny dim" style="margin-top: 6px">
              参考图只在本机读取，不会上传；路径必须是本机可访问的图片文件。
            </div>
          </div>
        </div>

        <div class="stack-3">
          <div>
            <h4>已关联图片（{{ (detail.linked_image_ids || []).length }}）</h4>
            <div v-if="linkedImages.length" class="grid-media" style="--card-min: 84px">
              <div
                v-for="img in linkedImages"
                :key="img.id"
                class="img-card"
                role="button"
                @click="openImageId = img.id"
              >
                <div class="thumb"><img :src="thumbUrl(img.id)" :alt="img.filename" loading="lazy" /></div>
                <div class="meta" style="padding: 6px 8px">
                  <div class="tiny clamp-1">{{ img.filename }}</div>
                  <button class="btn btn-xs" @click.stop="unlink(img.id)">取消关联</button>
                </div>
              </div>
            </div>
            <div v-else class="small dim">还没有关联任何图片</div>
            <div class="row" style="margin-top: 8px">
              <input v-model="linkId" class="input input-sm" style="width: 120px" placeholder="图片 ID" />
              <button class="btn btn-sm" @click="link">关联</button>
            </div>
            <div class="tiny dim" style="margin-top: 6px">
              手动关联的图会无条件注入该实体（第一路，优先级最高）。
            </div>
          </div>
        </div>
      </div>
    </Panel>

    <ImageDrawer v-if="openImageId" v-model:image-id="openImageId" :ids="linkedImages.map((i) => i.id)" @close="openImageId = null" />

    <ConfirmDialog
      :open="Boolean(askDelete)"
      title="删除实体"
      :message="`删除「${askDelete?.name}」？`"
      :details="['参考图与关联关系会一并删除', '已经完成的识别结果不会回退']"
      confirm-text="确认删除"
      danger
      @close="askDelete = null"
      @confirm="confirmDelete"
    />
  </div>
</template>

<style scoped>
.entities {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(300px, 1fr);
  gap: var(--sp-4);
  align-items: start;
}
.entities > .panel {
  margin-top: 0;
}
@media (max-width: 1080px) {
  .entities {
    grid-template-columns: 1fr;
  }
}
</style>

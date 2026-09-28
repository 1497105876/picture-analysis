<script setup>
import { computed, reactive, ref, watch } from "vue";
import { api, notify, thumbUrl } from "../api.js";

const props = defineProps({
  imageId: { type: Number, required: true },
  hiddenView: { type: Boolean, default: false },
});
const emit = defineEmits(["close", "changed"]);

const detail = ref(null);
const similar = ref([]);
const form = reactive({
  category: "",
  description: "",
  tags: "",
  rating: 0,
  favorite: false,
  notes: "",
});
const deleting = ref(false);
const deleteMode = ref("index");
const confirmWord = ref("");

async function load() {
  detail.value = await api.get(`/api/images/${props.imageId}`);
  const d = detail.value;
  form.category = d.category_manual || d.category_ai || "";
  form.description = d.description_manual || d.description_ai || "";
  form.tags = (d.manual_tags || []).join(", ");
  form.rating = d.rating || 0;
  form.favorite = Boolean(d.favorite);
  form.notes = d.notes || "";
  try {
    similar.value = (await api.get(`/api/images/${d.id}/similar`)).items || [];
  } catch {
    similar.value = [];
  }
}

watch(
  () => props.imageId,
  () => load(),
  { immediate: true }
);

const title = computed(() => detail.value?.filename || "详情");

async function save() {
  try {
    await api.patch(`/api/images/${props.imageId}`, {
      category: form.category || null,
      description: form.description || null,
      tags: form.tags
        .split(/[,，]/)
        .map((s) => s.trim())
        .filter(Boolean),
      rating: form.rating,
      favorite: form.favorite,
      notes: form.notes,
    });
    notify("已保存（人工字段优先，AI 不会覆盖）");
    await load();
    emit("changed");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function redo() {
  const feedback = window.prompt("打回重识别的纠正说明（可空）", "");
  if (feedback === null) return;
  try {
    await api.post(`/api/images/${props.imageId}/redo`, { feedback });
    notify("已加入重识别队列");
    emit("changed");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function toggleHide() {
  try {
    if (detail.value.hidden) {
      await api.post(`/api/images/${props.imageId}/unhide`);
      notify("已从隐藏区恢复");
    } else {
      await api.post(`/api/images/${props.imageId}/hide`);
      notify("已移入隐藏区（所有检索面不可见）");
    }
    emit("changed");
    emit("close");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function doDelete() {
  try {
    const params = { mode: deleteMode.value };
    if (deleteMode.value === "source") params.confirm = confirmWord.value;
    await api.del(`/api/images/${props.imageId}`, params);
    notify(deleteMode.value === "source" ? "源文件已移入回收站" : "已删除索引");
    emit("changed");
    emit("close");
  } catch (e) {
    notify(e.message, "error");
  }
}
</script>

<template>
  <div>
    <div class="drawer-mask" @click="emit('close')"></div>
    <aside class="drawer">
      <div class="row" style="justify-content: space-between">
        <h2>{{ title }}</h2>
        <button class="btn small" @click="emit('close')">关闭</button>
      </div>

      <template v-if="detail">
        <img class="preview" :src="thumbUrl(detail.id)" :alt="detail.filename" />

        <div class="row" style="margin: 10px 0">
          <span class="tag blue">{{ detail.category_manual || detail.category_ai || "未分类" }}</span>
          <span class="tag" :class="detail.analysis_state === 'done' ? 'green' : ''">{{
            detail.analysis_state
          }}</span>
          <span v-if="detail.hidden" class="tag red">隐藏中</span>
          <span v-if="detail.missing" class="tag red">文件丢失</span>
          <span class="tag">纠错 {{ detail.correction_count || 0 }} 次</span>
        </div>

        <div class="muted small" style="margin-bottom: 10px">
          {{ detail.path }}
        </div>

        <div class="panel">
          <h3>人工修正（优先级高于 AI）</h3>
          <label class="field"
            ><span class="lab">分类</span>
            <input v-model="form.category" class="grow" placeholder="如：风景" />
          </label>
          <label class="field"
            ><span class="lab">描述</span>
            <textarea v-model="form.description" rows="2"></textarea>
          </label>
          <label class="field"
            ><span class="lab">标签（逗号分隔）</span>
            <input v-model="form.tags" />
          </label>
          <div class="row">
            <label class="field grow"
              ><span class="lab">评分</span>
              <select v-model.number="form.rating">
                <option :value="0">无</option>
                <option v-for="n in 5" :key="n" :value="n">{{ n }} 星</option>
              </select>
            </label>
            <label class="field"
              ><span class="lab">收藏</span>
              <input v-model="form.favorite" type="checkbox" />
            </label>
          </div>
          <label class="field"
            ><span class="lab">备注</span>
            <input v-model="form.notes" />
          </label>
          <div class="row">
            <button class="btn primary" @click="save">保存</button>
            <button class="btn" @click="redo">打回重识别</button>
            <button class="btn" @click="toggleHide">
              {{ detail.hidden ? "从隐藏区恢复" : "移入隐藏区" }}
            </button>
          </div>
        </div>

        <div class="panel">
          <h3>识别结果</h3>
          <p v-if="detail.description_ai" class="small">
            AI 描述：{{ detail.description_ai }}
          </p>
          <div>
            <span v-for="t in detail.ai_tags || []" :key="t" class="tag blue">{{ t }}</span>
          </div>
          <div style="margin-top: 6px">
            <span v-for="e in detail.elements || []" :key="e" class="tag">{{ e }}</span>
          </div>
          <p v-if="detail.ocr_text" class="small muted">OCR：{{ detail.ocr_text }}</p>
          <p class="small muted">
            分析记录 {{ (detail.analyses || []).length }} 条 · 人工位：
            {{ detail.category_manual || "—" }} / {{ detail.description_manual || "—" }}
          </p>
        </div>

        <div v-if="similar.length" class="panel">
          <h3>相似图片</h3>
          <div class="cards">
            <div
              v-for="s in similar"
              :key="s.id"
              class="card"
              @click="emit('close'), $emit('open', s.id)"
            >
              <div class="ph"><img :src="thumbUrl(s.id)" :alt="s.filename" /></div>
              <div class="meta"><div class="name">{{ s.filename }}</div></div>
            </div>
          </div>
        </div>

        <div class="panel">
          <h3>危险操作</h3>
          <div class="row">
            <select v-model="deleteMode">
              <option value="index">只删索引（源文件保留）</option>
              <option value="source">删除源文件（进回收站）</option>
            </select>
            <template v-if="deleteMode === 'source'">
              <input
                v-model="confirmWord"
                :placeholder="`输入 ${detail.filename} 确认`"
              />
            </template>
            <button
              class="btn danger"
              :disabled="deleteMode === 'source' && confirmWord !== detail.filename"
              @click="doDelete"
            >
              删除
            </button>
          </div>
        </div>
      </template>
    </aside>
  </div>
</template>

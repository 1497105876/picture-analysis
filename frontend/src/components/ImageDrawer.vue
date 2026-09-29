<script setup>
// 图片详情抽屉。
// 承载：预览 / 元信息 / 人工修正（含自定义字段）/ AI 结果 / 识别历史 / 相似图 /
//       改名 / 移动 / 隐藏 / 打回重识别 / 删除（索引 or 源文件）
// 键盘：Esc 关闭，← / → 在 ids 列表里翻图
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

import { api, thumbUrl } from "../app/api.js";
import { catalog, loadCatalog } from "../app/catalog.js";
import { notify } from "../app/toast.js";
import { bytes, datetimeAny, datetime, stateMeta, ago } from "../app/format.js";
import ConfirmDialog from "./ConfirmDialog.vue";
import EmptyState from "./EmptyState.vue";
import Icon from "./Icon.vue";
import Skeleton from "./Skeleton.vue";
import StarRating from "./StarRating.vue";
import TagInput from "./TagInput.vue";

const props = defineProps({
  imageId: { type: Number, required: true },
  ids: { type: Array, default: () => [] },
  dirs: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:imageId", "close", "changed"]);

const detail = ref(null);
const loading = ref(false);
const similar = ref([]);
const similarDegraded = ref(false);

const form = reactive({
  category: "",
  description: "",
  tags: [],
  rating: 0,
  favorite: false,
  notes: "",
  custom: {},
});
const saving = ref(false);
const busy = ref(false);

// ---- 删除 / 改名 / 移动 / 打回 的对话框状态 ----
const dlg = reactive({
  kind: "", // "" | delete | rename | redo
  open: false,
  mode: "index",
  value: "",
  message: "",
  details: [],
  confirmWord: "",
  busy: false,
});

const indexInList = computed(() => props.ids.indexOf(props.imageId));
const hasPrev = computed(() => indexInList.value > 0);
const hasNext = computed(() => indexInList.value >= 0 && indexInList.value < props.ids.length - 1);

const meta = computed(() => stateMeta(detail.value?.analysis_state));

async function load() {
  loading.value = true;
  try {
    await loadCatalog();
    detail.value = await api.imageDetail(props.imageId);
    const d = detail.value;
    form.category = d.category_manual ?? "";
    form.description = d.description_manual ?? "";
    form.tags = [...(d.manual_tags || [])];
    form.rating = Number(d.rating) || 0;
    form.favorite = Boolean(d.favorite);
    form.notes = d.notes ?? "";
    form.custom = { ...(d.custom_fields || {}) };
    loadSimilar();
  } catch (e) {
    notify(e.message, "error");
    emit("close");
  } finally {
    loading.value = false;
  }
}

async function loadSimilar() {
  try {
    const data = await api.similar(props.imageId, 12);
    similar.value = data.items || [];
    similarDegraded.value = Boolean(data.degraded);
  } catch {
    similar.value = [];
  }
}

watch(() => props.imageId, load, { immediate: true });

async function save() {
  saving.value = true;
  try {
    const payload = {
      category: form.category || null,
      description: form.description || null,
      tags: form.tags,
      rating: form.rating,
      favorite: form.favorite,
      notes: form.notes,
      ...form.custom,
    };
    detail.value = await api.patchImage(props.imageId, payload);
    notify("已保存：人工字段优先，AI 不会覆盖", "ok");
    emit("changed");
  } catch (e) {
    notify(e.message, "error");
  } finally {
    saving.value = false;
  }
}

async function toggleHide() {
  busy.value = true;
  try {
    if (detail.value.hidden) {
      await api.unhideImage(props.imageId);
      notify("已从隐藏区恢复", "ok");
    } else {
      await api.hideImage(props.imageId);
      notify("已移入隐藏区：图库 / 检索 / 相册全部不可见", "ok");
    }
    emit("changed");
    emit("close");
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

async function toggleFavorite() {
  try {
    const next = !form.favorite;
    await api.patchImage(props.imageId, { favorite: next });
    form.favorite = next;
    emit("changed");
  } catch (e) {
    notify(e.message, "error");
  }
}

// ---------- 对话框类操作 ----------
function askRedo() {
  dlg.kind = "redo";
  dlg.message = "打回重识别：带上你的纠正说明，AI 会重新识别这张图（计入人工纠错次数）。";
  dlg.value = detail.value.last_feedback || "";
  dlg.confirmWord = "";
  dlg.details = ["重识别会重新消耗一次 API 调用", "人工填写的分类/描述不会被覆盖"];
  dlg.open = true;
}

function askRename() {
  dlg.kind = "rename";
  dlg.message = "修改磁盘上的真实文件名（索引同步更新，只限于已登记目录内）。";
  dlg.value = detail.value.filename;
  dlg.confirmWord = "";
  dlg.details = ["同名文件已存在会被拒绝", "不能包含路径分隔符"];
  dlg.open = true;
}

function askDelete() {
  dlg.kind = "delete";
  dlg.mode = "index";
  dlg.confirmWord = "";
  dlg.open = true;
}

function deleteMessage() {
  return dlg.mode === "index"
    ? "只从索引里删除这张图：源文件保留在原处，但会被登记为「仅移除索引」，后续增量扫描不再收录。"
    : "删除源文件：文件被移入回收站（可在回收站页恢复），索引一并移除。此操作不可通过界面直接还原到原位以外的路径。";
}
function deleteDetails() {
  return dlg.mode === "index"
    ? ["源文件不会被改动", "可重新登记该目录把它找回来"]
    : ["文件进入 data/trash，可恢复", `需要输入文件名「${detail.value.filename}」确认`];
}
const deleteConfirmWord = computed(() => (dlg.mode === "source" ? detail.value?.filename || "" : ""));

async function onDialogConfirm(value) {
  dlg.busy = true;
  try {
    if (dlg.kind === "redo") {
      await api.redoImage(props.imageId, value);
      notify("已加入重识别队列", "ok");
    } else if (dlg.kind === "rename") {
      detail.value = await api.renameImage(props.imageId, value);
      notify("已改名并同步索引", "ok");
    } else if (dlg.kind === "delete") {
      await api.deleteImage(props.imageId, { mode: dlg.mode, confirm: deleteConfirmWord.value });
      notify(dlg.mode === "source" ? "源文件已移入回收站" : "已删除索引", "ok");
    }
    dlg.open = false;
    if (dlg.kind === "delete") {
      emit("changed");
      emit("close");
    } else {
      emit("changed");
      await load();
    }
  } catch (e) {
    notify(e.message, "error");
  } finally {
    dlg.busy = false;
  }
}

async function moveTo(dirId) {
  busy.value = true;
  try {
    detail.value = await api.moveImage(props.imageId, dirId);
    notify("已移动到目标目录", "ok");
    emit("changed");
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

async function copyText(text, label = "内容") {
  try {
    await navigator.clipboard.writeText(text);
    notify(`已复制${label}`, "ok");
  } catch {
    notify(`复制失败，请手动选择：${text}`, "warn");
  }
}

function goto(delta) {
  const next = props.ids[indexInList.value + delta];
  if (next) emit("update:imageId", next);
}

function onKey(e) {
  if (e.key === "Escape") {
    if (dlg.open) return; // 对话框自己处理 Esc
    emit("close");
  } else if (e.key === "ArrowLeft" && hasPrev.value) {
    goto(-1);
  } else if (e.key === "ArrowRight" && hasNext.value) {
    goto(1);
  }
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));

const moveTargets = computed(() => props.dirs.filter((d) => d.id !== detail.value?.dir_id && d.enabled));
</script>

<template>
  <Teleport to="body">
    <div class="mask" @click="emit('close')"></div>
    <aside class="drawer" role="dialog" aria-modal="true">
      <header class="drawer-head">
        <div class="stack" style="gap: 2px; min-width: 0; flex: 1">
          <h3 class="clamp-1" :title="detail?.filename || ''">{{ detail?.filename || "图片详情" }}</h3>
          <div class="tiny dim">
            <template v-if="ids.length">第 {{ indexInList + 1 }} / {{ ids.length }} 张 · </template>
            <span class="mono">#{{ imageId }}</span>
          </div>
        </div>
        <div class="drawer-nav">
          <button class="btn btn-sm btn-icon" :disabled="!hasPrev" title="上一张（←）" @click="goto(-1)">
            <Icon name="chevronLeft" :size="14" />
          </button>
          <button class="btn btn-sm btn-icon" :disabled="!hasNext" title="下一张（→）" @click="goto(1)">
            <Icon name="chevronRight" :size="14" />
          </button>
          <button class="btn btn-sm" @click="emit('close')">关闭</button>
        </div>
      </header>

      <div class="drawer-body stack-4">
        <Skeleton v-if="loading && !detail" variant="lines" :count="6" />

        <template v-else-if="detail">
          <!-- 预览 -->
          <div class="thumb-preview">
            <img :src="thumbUrl(detail.id)" :alt="detail.filename" />
            <span v-if="detail.hidden" class="tag tag-danger overlay-tag">隐藏中</span>
            <span v-if="detail.missing" class="tag tag-danger overlay-tag" style="right: 76px">
              文件丢失
            </span>
          </div>

          <div class="row" style="gap: 6px">
            <span class="tag tag-accent">{{ detail.category_manual || detail.category_ai || "未分类" }}</span>
            <span class="tag" :class="`tag-${meta.tone}`">{{ meta.text }}</span>
            <span class="tag tag-outline">纠错 {{ detail.correction_count || 0 }} 次</span>
            <span v-if="detail.has_text" class="tag tag-outline">含文字</span>
          </div>

          <!-- 元信息 -->
          <div class="panel-inset">
            <dl class="kv">
              <dt>路径</dt>
              <dd class="row" style="gap: 6px">
                <span class="mono wrap-anywhere">{{ detail.path }}</span>
                <button class="btn btn-xs" @click="copyText(detail.path, '路径')">
                  <Icon name="copy" :size="12" />
                </button>
              </dd>
              <dt>尺寸</dt>
              <dd>{{ detail.width && detail.height ? `${detail.width}×${detail.height}` : "—" }} · {{ bytes(detail.bytes) }} · {{ detail.ext }}</dd>
              <dt>时间</dt>
              <dd>
                拍摄 {{ datetime(detail.exif_taken_at) || "—" }} · 入库 {{ datetime(detail.created_at) }} · 更新
                {{ ago(detail.updated_at) }}
              </dd>
              <dt>MD5</dt>
              <dd class="mono wrap-anywhere small">{{ detail.md5 || "—" }}</dd>
            </dl>
          </div>

          <!-- 人工修正 -->
          <section class="panel">
            <div class="panel-head">
              <div>
                <h3>人工修正</h3>
                <div class="panel-sub">优先级高于 AI 结果，AI 永远不会覆盖这一栏</div>
              </div>
            </div>
            <div class="stack-3">
              <label class="field">
                <span class="lab">分类</span>
                <select v-model="form.category" class="select">
                  <option value="">（不指定，回落到 AI 分类）</option>
                  <option v-for="c in catalog.categories" :key="c.id" :value="c.name">{{ c.emoji }} {{ c.name }}</option>
                  <option v-if="form.category && !catalog.categories.some((c) => c.name === form.category)" :value="form.category">
                    {{ form.category }}（字典外）
                  </option>
                </select>
              </label>
              <label class="field">
                <span class="lab">描述</span>
                <textarea v-model="form.description" class="textarea" rows="2" placeholder="给这张图一句人话描述"></textarea>
              </label>
              <div class="field">
                <span class="lab">标签</span>
                <TagInput v-model="form.tags" :suggestions="detail.ai_tags || []" placeholder="回车添加" />
              </div>
              <div class="row" style="gap: var(--sp-4)">
                <div class="field">
                  <span class="lab">评分</span>
                  <StarRating v-model="form.rating" />
                </div>
                <label class="field">
                  <span class="lab">收藏</span>
                  <span class="switch">
                    <input v-model="form.favorite" type="checkbox" />
                    <span class="track"></span>
                    <span class="knob"></span>
                  </span>
                </label>
              </div>
              <label class="field">
                <span class="lab">备注</span>
                <input v-model="form.notes" class="input" placeholder="只有你自己看得见" />
              </label>

              <div v-if="catalog.customFields.length" class="stack-3">
                <div class="small muted strong">自定义字段</div>
                <label v-for="f in catalog.customFields" :key="f.id" class="field">
                  <span class="lab">{{ f.name }} <span class="tiny dim">{{ f.type }}</span></span>
                  <select
                    v-if="f.type === 'select'"
                    v-model="form.custom[f.name]"
                    class="select"
                  >
                    <option value="">（空）</option>
                    <option v-for="o in f.options || []" :key="o" :value="o">{{ o }}</option>
                  </select>
                  <input
                    v-else
                    v-model="form.custom[f.name]"
                    class="input"
                    :type="f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text'"
                  />
                </label>
              </div>

              <div class="row">
                <button class="btn btn-primary" :disabled="saving" @click="save">
                  <span v-if="saving" class="spin"></span>
                  保存修正
                </button>
                <button class="btn" :disabled="busy" @click="askRedo">打回重识别</button>
                <button class="btn" :disabled="busy" @click="toggleFavorite">
                  {{ detail.favorite ? "取消收藏" : "收藏" }}
                </button>
                <button class="btn" :disabled="busy" @click="toggleHide">
                  {{ detail.hidden ? "从隐藏区恢复" : "移入隐藏区" }}
                </button>
              </div>
            </div>
          </section>

          <!-- AI 结果 -->
          <section class="panel">
            <div class="panel-head">
              <div>
                <h3>AI 识别结果</h3>
                <div class="panel-sub">
                  AI 分类 {{ detail.category_ai || "—" }} · 分析记录 {{ (detail.analyses || []).length }} 条
                </div>
              </div>
            </div>
            <div class="stack-3">
              <p v-if="detail.description_ai" class="small">{{ detail.description_ai }}</p>
              <p v-else class="small muted">还没有 AI 描述（未识别或识别失败）。</p>
              <div v-if="(detail.ai_tags || []).length" class="row" style="gap: 4px">
                <span v-for="t in detail.ai_tags" :key="t" class="tag tag-accent">{{ t }}</span>
              </div>
              <div v-if="(detail.elements || []).length" class="row" style="gap: 4px">
                <span v-for="e in detail.elements" :key="e" class="tag tag-outline">{{ e }}</span>
              </div>
              <div v-if="detail.ocr_text" class="panel-inset small">
                <div class="dim tiny" style="margin-bottom: 4px">OCR 文本</div>
                {{ detail.ocr_text }}
              </div>
              <details v-if="(detail.analyses || []).length">
                <summary class="small muted" style="cursor: pointer">
                  识别历史 {{ (detail.analyses || []).length }} 条
                </summary>
                <div class="timeline" style="margin-top: 8px">
                  <div v-for="a in detail.analyses" :key="a.id" class="ev ev-ok">
                    <div class="wrap-anywhere">
                      {{ a.category || "无分类" }}｜{{ a.description ? a.description.slice(0, 40) : "无描述" }}
                    </div>
                    <div class="tiny dim">
                      {{ a.model || "未知模型" }} · in {{ a.tokens_in }} / out {{ a.tokens_out }} ·
                      {{ datetimeAny(a.created_at) }}
                    </div>
                  </div>
                </div>
              </details>
            </div>
          </section>

          <!-- 相似图 -->
          <section class="panel">
            <div class="panel-head">
              <div>
                <h3>相似图片</h3>
                <div class="panel-sub">按向量相似度召回，隐藏区不参与</div>
              </div>
              <button class="btn btn-xs" @click="loadSimilar">
                <Icon name="refresh" :size="12" />
              </button>
            </div>
            <div v-if="similar.length" class="grid-media" style="--card-min: 84px">
              <div
                v-for="s in similar"
                :key="s.id"
                class="img-card"
                role="button"
                tabindex="0"
                @click="emit('update:imageId', s.id)"
                @keyup.enter="emit('update:imageId', s.id)"
              >
                <div class="thumb"><img :src="thumbUrl(s.id)" :alt="s.filename" loading="lazy" /></div>
                <div class="meta" style="padding: 6px 8px">
                  <div class="tiny clamp-1">{{ s.filename }}</div>
                </div>
              </div>
            </div>
            <EmptyState
              v-else
              compact
              icon="sparkle"
              title="没有相似图"
              :hint="similarDegraded ? '嵌入向量不可用，以图搜图暂时无法工作' : '这张图还没有可用的向量，或者库里没有相近的图'"
            />
          </section>

          <!-- 文件操作 -->
          <section class="panel panel-danger">
            <div class="panel-head">
              <div>
                <h3>
                  <Icon name="warning" :size="14" />
                  文件操作
                </h3>
                <div class="panel-sub">改名/移动会真实改动磁盘上的文件，删除源文件先进回收站</div>
              </div>
            </div>
            <div class="stack-3">
              <div class="row">
                <button class="btn btn-sm" @click="askRename">
                  <Icon name="file" :size="13" /> 改名
                </button>
                <select
                  class="select select-sm grow"
                  :value="''"
                  @change="
                    (e) => {
                      if (e.target.value) moveTo(Number(e.target.value));
                      e.target.value = '';
                    }
                  "
                  :disabled="!moveTargets.length"
                >
                  <option value="">
                    {{ moveTargets.length ? "移动到目录…" : "没有其他登记目录" }}
                  </option>
                  <option v-for="d in moveTargets" :key="d.id" :value="d.id">{{ d.path }}</option>
                </select>
              </div>
              <div class="row">
                <select v-model="dlg.mode" class="select select-sm" style="width: 190px">
                  <option value="index">只删索引（源文件保留）</option>
                  <option value="source">删除源文件（进回收站）</option>
                </select>
                <button class="btn btn-sm btn-danger" @click="askDelete">
                  <Icon name="trash" :size="13" /> 删除
                </button>
              </div>
            </div>
          </section>
        </template>
      </div>
    </aside>

    <ConfirmDialog
      :open="dlg.open"
      :title="
        dlg.kind === 'redo'
          ? '打回重识别'
          : dlg.kind === 'rename'
            ? '修改文件名'
            : dlg.mode === 'source'
              ? '删除源文件'
              : '删除索引'
      "
      :message="dlg.kind === 'delete' ? deleteMessage() : dlg.message"
      :details="dlg.kind === 'delete' ? deleteDetails() : dlg.details"
      :confirm-word="dlg.kind === 'delete' ? deleteConfirmWord : ''"
      :prompt-label="dlg.kind === 'delete' ? '' : dlg.kind === 'rename' ? '新文件名' : '纠正说明（可留空）'"
      :prompt-value="dlg.value"
      :confirm-text="dlg.kind === 'delete' ? '确认删除' : '提交'"
      :danger="dlg.kind === 'delete'"
      :busy="dlg.busy"
      icon="warning"
      @close="dlg.open = false"
      @confirm="onDialogConfirm"
    />
  </Teleport>
</template>

<style scoped>
.thumb-preview {
  position: relative;
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  max-height: 42vh;
}
.thumb-preview img {
  max-width: 100%;
  max-height: 42vh;
  display: block;
}
.overlay-tag {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 2;
  box-shadow: var(--shadow-1);
}
details summary::-webkit-details-marker {
  display: none;
}
</style>

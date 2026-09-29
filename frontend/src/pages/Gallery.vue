<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { api, notify } from "../api.js";
import ImageCard from "../components/ImageCard.vue";
import ImageDrawer from "../components/ImageDrawer.vue";

const dirs = ref([]);
const images = ref([]);
const cursor = ref(null);
const loading = ref(false);
const selected = ref(new Set());
const openId = ref(null);

const filters = reactive({ dir_id: "", category: "", analysis_state: "", rating_min: "", favorite: "" });
const sort = ref("mtime");
const order = ref("desc");

const showWizard = ref(false);
const wizard = reactive({ path: "", recursive: true, estimate: null });
const globalWatcher = ref(false);

async function loadDirs() {
  dirs.value = (await api.get("/api/directories")).items || [];
}

async function load(reset = true) {
  loading.value = true;
  try {
    const params = {
      dir_id: filters.dir_id || undefined,
      category: filters.category || undefined,
      analysis_state: filters.analysis_state || undefined,
      rating_min: filters.rating_min || undefined,
      favorite: filters.favorite === "" ? undefined : filters.favorite,
      sort: sort.value,
      order: order.value,
      limit: 40,
    };
    if (!reset && cursor.value) params.cursor = cursor.value;
    const data = await api.get("/api/images", params);
    images.value = reset ? data.items : [...images.value, ...data.items];
    cursor.value = data.next_cursor || null;
  } catch (e) {
    notify(e.message, "error");
  } finally {
    loading.value = false;
  }
}

async function estimate() {
  try {
    const data = await api.post("/api/directories", {
      path: wizard.path,
      recursive: wizard.recursive,
    });
    wizard.estimate = data.estimate;
  } catch (e) {
    notify(e.message, "error");
  }
}

async function register() {
  const est = wizard.estimate;
  try {
    let scan = null;
    if (est?.registered_id) {
      await api.post(`/api/scan/${est.registered_id}`, {});
      notify("该目录已登记，已执行增量扫描");
    } else {
      const data = await api.post("/api/directories?confirm=1", {
        path: wizard.path,
        recursive: wizard.recursive,
        estimate: est,
      });
      scan = data.scan || {};
      notify(
        `已登记并扫描完成：新增 ${scan.added ?? 0}、更新 ${scan.updated ?? 0}、跳过 ${scan.skipped ?? 0}`,
      );
    }
    showWizard.value = false;
    wizard.path = "";
    wizard.estimate = null;
    await loadDirs();
    await load();
  } catch (e) {
    if (e.status === 409) {
      // 估算与确认之间被登记（重复点击等）：降级为增量扫描
      await loadDirs();
      const hit = dirs.value.find((d) => d.path === wizard.path);
      if (hit) {
        await api.post(`/api/scan/${hit.id}`, {});
        notify("该目录已登记，已执行增量扫描");
        showWizard.value = false;
        wizard.path = "";
        wizard.estimate = null;
        await load();
        return;
      }
    }
    notify(e.message, "error");
  }
}

async function toggleWatcher(d) {
  try {
    const next = !d.watcher;
    await api.patch(`/api/directories/${d.id}`, { watcher: next });
    d.watcher = next;
    notify(
      next
        ? `已切换自动跟踪：${d.path}（30 秒轮询增量扫描${globalWatcher.value ? "" : "，需先在设置 G4 开启全局开关"}）`
        : `已切换手动模式：${d.path}（只在点「增量扫描」时更新）`,
    );
  } catch (e) {
    notify(e.message, "error");
  }
}

async function removeDir(d) {
  if (!window.confirm(`删除登记「${d.path}」？索引移除，源文件不动。`)) return;
  try {
    await api.del(`/api/directories/${d.id}`);
    await loadDirs();
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function startScan(d) {
  try {
    const res = await api.post(`/api/scan/${d.id}`, {});
    notify(
      `扫描完成：新增 ${res.added ?? 0}、更新 ${res.updated ?? 0}、跳过 ${res.skipped ?? 0}、丢失 ${res.missing ?? 0}`,
    );
    await loadDirs();
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

function toggle(id) {
  if (selected.value.has(id)) selected.value.delete(id);
  else selected.value.add(id);
}

async function batch(op) {
  if (!selected.value.size) return notify("未选择图片", "warn");
  const ids = [...selected.value];
  try {
    if (op === "delete" && !window.confirm(`删除 ${ids.length} 张的索引？源文件不动。`)) return;
    await api.post("/api/images/batch", { op, ids });
    notify(`批量完成（${ids.length} 张）`);
    selected.value.clear();
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function exportSel() {
  if (!selected.value.size) return notify("未选择图片", "warn");
  try {
    const data = await api.post("/api/export", {
      ids: [...selected.value],
      format: "json",
    });
    notify(`已导出 ${data.count} 条到 ${data.path}`);
  } catch (e) {
    notify(e.message, "error");
  }
}

async function onUpload(ev) {
  const files = [...ev.target.files];
  for (const f of files) {
    try {
      await api.upload(f);
    } catch (e) {
      notify(e.message, "error");
    }
  }
  notify(`上传完成（${files.length} 个）`);
  await load();
}

const categories = computed(() => [...new Set(images.value.map((i) => i.category).filter(Boolean))]);

onMounted(async () => {
  try {
    const cfg = await api.get("/api/settings");
    globalWatcher.value = !!cfg?.values?.watcher_enabled;
  } catch {
    globalWatcher.value = false;
  }
  await loadDirs();
  await load();
});
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>图库</h1>
        <div class="sub">已选 {{ selected.size }} 张</div>
      </div>
      <div class="row">
        <button class="btn" @click="showWizard = !showWizard">登记目录</button>
        <label class="btn">
          上传图片
          <input type="file" accept="image/*" multiple hidden @change="onUpload" />
        </label>
      </div>
    </div>

    <div v-if="showWizard" class="panel">
      <h3>两阶段登记（先估数、后确认；未登记目录零扫描）</h3>
      <div class="row">
        <input v-model="wizard.path" class="grow" placeholder="绝对路径，如 D:\Photos" />
        <label class="small"><input v-model="wizard.recursive" type="checkbox" /> 递归子目录</label>
        <button class="btn" :disabled="!wizard.path" @click="estimate">第一步：估算</button>
        <button class="btn primary" :disabled="!wizard.estimate" @click="register">
          {{ wizard.estimate?.registered_id ? "第二步：增量扫描" : "第二步：确认登记" }}
        </button>
      </div>
      <div v-if="wizard.estimate" class="small muted" style="margin-top: 8px">
        发现 {{ wizard.estimate.count }} 个文件（{{ (wizard.estimate.bytes / 1048576).toFixed(1) }}
        MB），预计 {{ wizard.estimate.est_minutes }} 分钟 · 估算 token {{ wizard.estimate.est_tokens }}
        （今日剩余 {{ wizard.estimate.tokens_left ?? "不限" }}）·
        <span :class="wizard.estimate.within_budget ? '' : 'tag red'">{{
          wizard.estimate.within_budget ? "在日预算内" : "超出日预算"
        }}</span>
        <div v-if="wizard.estimate.registered_id" class="tag" style="display: inline-block">
          该目录已登记，确认后执行增量扫描
        </div>
        <div v-if="wizard.estimate.overlap" class="tag red">{{ wizard.estimate.overlap }}</div>
        <div v-for="p in wizard.estimate.phases" :key="p">· {{ p }}</div>
      </div>
    </div>

    <div class="panel">
      <div class="row">
        <select v-model="filters.dir_id" @change="load()">
          <option value="">全部目录</option>
          <option v-for="d in dirs" :key="d.id" :value="d.id">{{ d.path }}</option>
        </select>
        <select v-model="filters.category" @change="load()">
          <option value="">全部分类</option>
          <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
        </select>
        <select v-model="filters.analysis_state" @change="load()">
          <option value="">全部状态</option>
          <option value="unanalyzed">未识别</option>
          <option value="done">已识别</option>
          <option value="failed">失败</option>
          <option value="skipped">跳过（超大图/隐私）</option>
        </select>
        <select v-model="filters.rating_min" @change="load()">
          <option value="">任意评分</option>
          <option v-for="n in 5" :key="n" :value="n">{{ n }} 星以上</option>
        </select>
        <select v-model="filters.favorite" @change="load()">
          <option value="">收藏不限</option>
          <option value="true">仅收藏</option>
          <option value="false">未收藏</option>
        </select>
        <select v-model="sort" @change="load()">
          <option value="mtime">修改时间</option>
          <option value="taken">拍摄时间</option>
          <option value="created">入库时间</option>
          <option value="filename">文件名</option>
          <option value="rating">评分</option>
          <option value="id">编号</option>
        </select>
        <select v-model="order" @change="load()">
          <option value="desc">降序</option>
          <option value="asc">升序</option>
        </select>
        <span class="grow"></span>
        <button class="btn small" :disabled="!selected.size" @click="exportSel">导出</button>
        <button class="btn small" :disabled="!selected.size" @click="batch('hide')">批量隐藏</button>
        <button class="btn small danger" :disabled="!selected.size" @click="batch('delete')">批量删除索引</button>
      </div>
    </div>

    <div v-if="dirs.length" class="panel">
      <h3>
        已登记目录
        <span v-if="!globalWatcher" class="tag red" style="margin-left: 8px">
          全局自动导入未开启（设置 → G4 目录策略）
        </span>
        <span v-else class="tag green" style="margin-left: 8px">全局自动导入已开启（30 秒轮询）</span>
      </h3>
      <table>
        <thead>
          <tr><th>路径</th><th>递归</th><th>状态</th><th>跟踪</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="d in dirs" :key="d.id">
            <td>{{ d.path }}</td>
            <td>{{ d.recursive ? "是" : "否" }}</td>
            <td>
              <span class="tag" :class="d.enabled ? 'green' : 'red'">{{ d.enabled ? "启用" : "停用" }}</span>
            </td>
            <td>
              <button
                class="btn small"
                :class="d.watcher ? 'primary' : ''"
                :title="d.watcher ? '自动：30 秒轮询增量扫描' : '手动：仅点击「增量扫描」时更新'"
                @click="toggleWatcher(d)"
              >
                {{ d.watcher ? "自动" : "手动" }}
              </button>
            </td>
            <td class="row">
              <button class="btn small" @click="startScan(d)">增量扫描</button>
              <button class="btn small danger" @click="removeDir(d)">删除登记</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="images.length" class="cards">
      <ImageCard
        v-for="img in images"
        :key="img.id"
        :image="img"
        :selected="selected.has(img.id)"
        @toggle="toggle"
        @open="(i) => (openId = i.id)"
      />
    </div>
    <div v-else class="empty">没有图片。先登记目录或上传图片。</div>

    <div v-if="cursor" class="row" style="justify-content: center; margin-top: 12px">
      <button class="btn" :disabled="loading" @click="load(false)">加载更多</button>
    </div>

    <ImageDrawer v-if="openId" :image-id="openId" @close="openId = null" @changed="load()" />
  </div>
</template>

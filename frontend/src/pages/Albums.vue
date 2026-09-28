<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { api, notify } from "../api.js";
import ImageCard from "../components/ImageCard.vue";
import ImageDrawer from "../components/ImageDrawer.vue";

const route = useRoute();
const albums = ref([]);
const active = ref(null);
const images = ref([]);
const openId = ref(null);
const form = reactive({ name: "", query: '{"category": "风景"}' });

async function load() {
  albums.value = (await api.get("/api/albums")).items || [];
  if (route.params.id) {
    const found = albums.value.find((a) => String(a.id) === String(route.params.id));
    if (found) await open(found);
  }
}

async function create() {
  let query;
  try {
    query = JSON.parse(form.query || "{}");
  } catch {
    return notify("query 必须是合法 JSON 对象", "warn");
  }
  try {
    await api.post("/api/albums", { name: form.name, query });
    notify("相册已创建（识别后自动回放）");
    form.name = "";
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function open(a) {
  active.value = a;
  try {
    const data = await api.get(`/api/albums/${a.id}/images`, { limit: 60 });
    images.value = data.items || [];
  } catch (e) {
    notify(e.message, "error");
  }
}

async function remove(a) {
  if (!window.confirm(`删除相册「${a.name}」？`)) return;
  try {
    await api.del(`/api/albums/${a.id}`);
    if (active.value?.id === a.id) {
      active.value = null;
      images.value = [];
    }
    await load();
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
        <h1>智能相册</h1>
        <div class="sub">按查询条件动态回放，图片变化相册自动更新</div>
      </div>
    </div>

    <div class="panel">
      <h3>新建相册</h3>
      <div class="row">
        <input v-model="form.name" placeholder="相册名" />
        <input v-model="form.query" class="grow" placeholder='query JSON，如 {"category": "风景", "rating_min": 4}' />
        <button class="btn primary" :disabled="!form.name" @click="create">创建</button>
      </div>
    </div>

    <div class="panel">
      <h3>相册列表</h3>
      <table>
        <thead><tr><th>名称</th><th>查询条件</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="a in albums" :key="a.id" :style="active?.id === a.id ? 'background: var(--brand-soft)' : ''">
            <td>{{ a.name }}</td>
            <td class="small muted">{{ JSON.stringify(a.query) }}</td>
            <td class="row">
              <button class="btn small" @click="open(a)">查看</button>
              <button class="btn small danger" @click="remove(a)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!albums.length" class="empty">还没有相册</div>
    </div>

    <template v-if="active">
      <div class="page-head"><h1>{{ active.name }}（{{ images.length }}）</h1></div>
      <div v-if="images.length" class="cards">
        <ImageCard
          v-for="img in images"
          :key="img.id"
          :image="img"
          :selectable="false"
          @open="(i) => (openId = i.id)"
        />
      </div>
      <div v-else class="empty">暂无匹配图片</div>
    </template>

    <ImageDrawer v-if="openId" :image-id="openId" @close="openId = null" />
  </div>
</template>

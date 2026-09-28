<script setup>
import { onMounted, ref } from "vue";
import { api, notify } from "../api.js";
import ImageCard from "../components/ImageCard.vue";
import ImageDrawer from "../components/ImageDrawer.vue";

const items = ref([]);
const selected = ref(new Set());
const openId = ref(null);
const cursor = ref(null);

async function load(reset = true) {
  const params = { limit: 60 };
  if (!reset && cursor.value) params.cursor = cursor.value;
  const data = await api.get("/api/hidden", params);
  items.value = reset ? data.items : [...items.value, ...data.items];
  cursor.value = data.next_cursor || null;
}

function toggle(id) {
  if (selected.value.has(id)) selected.value.delete(id);
  else selected.value.add(id);
}

async function unhide(ids) {
  try {
    await api.post("/api/images/batch", { op: "unhide", ids });
    notify(`已恢复 ${ids.length} 张`);
    selected.value.clear();
    await load();
  } catch (e) {
    notify(e.message, "error");
  }
}

onMounted(() => load());
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>隐藏区</h1>
        <div class="sub">已选 {{ selected.size }} 张</div>
      </div>
      <button class="btn primary" :disabled="!selected.size" @click="unhide([...selected])">
        批量恢复
      </button>
    </div>

    <div class="notice-bar">
      此处为持久隐藏状态：图片在图库、搜索、智能相册与 SQLite 直读中全部不可见，也没有任何参数可以绕过。
      与隐私模式不同（隐私只是临时 UI 遮罩）。文件仍在原处，识别与备份照常进行。
    </div>

    <div v-if="items.length" class="cards">
      <ImageCard
        v-for="img in items"
        :key="img.id"
        :image="img"
        :selected="selected.has(img.id)"
        @toggle="toggle"
        @open="(i) => (openId = i.id)"
      />
    </div>
    <div v-else class="empty">隐藏区是空的</div>

    <div v-if="cursor" class="row" style="justify-content: center; margin-top: 12px">
      <button class="btn" @click="load(false)">加载更多</button>
    </div>

    <ImageDrawer v-if="openId" :image-id="openId" hidden-view @close="openId = null" @changed="load()" />
  </div>
</template>

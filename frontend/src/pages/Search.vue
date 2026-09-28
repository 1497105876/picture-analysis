<script setup>
import { onMounted, reactive, ref } from "vue";
import { api, notify } from "../api.js";
import ImageCard from "../components/ImageCard.vue";
import ImageDrawer from "../components/ImageDrawer.vue";

const form = reactive({ q: "", mode: "", category: "", rating_min: "", date_from: "", date_to: "" });
const result = ref(null);
const history = ref([]);
const openId = ref(null);
const searching = ref(false);

async function run() {
  searching.value = true;
  try {
    result.value = await api.get("/api/search", {
      q: form.q || undefined,
      mode: form.mode || undefined,
      category: form.category || undefined,
      rating_min: form.rating_min || undefined,
      date_from: form.date_from || undefined,
      date_to: form.date_to || undefined,
      limit: 60,
    });
    if (form.q) history.value = (await api.get("/api/search/history")).items || [];
  } catch (e) {
    notify(e.message, "error");
  } finally {
    searching.value = false;
  }
}

function useHistory(q) {
  form.q = q;
  run();
}

async function clearHistory() {
  await api.del("/api/search/history");
  history.value = [];
}

onMounted(async () => {
  try {
    history.value = (await api.get("/api/search/history")).items || [];
  } catch {
    /* 忽略 */
  }
  run();
});
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>检索</h1>
        <div class="sub">混合（关键词+向量 RRF）/ 关键词 / 向量 三模式</div>
      </div>
      <button class="btn small" @click="clearHistory">清空历史</button>
    </div>

    <div class="panel">
      <div class="row">
        <input
          v-model="form.q"
          class="grow"
          placeholder="描述你想找的图，如：海边 日落"
          @keyup.enter="run"
        />
        <select v-model="form.mode">
          <option value="">默认模式</option>
          <option value="hybrid">混合</option>
          <option value="keyword">关键词</option>
          <option value="vector">向量</option>
        </select>
        <input v-model="form.category" placeholder="分类" style="width: 110px" />
        <select v-model="form.rating_min">
          <option value="">任意评分</option>
          <option v-for="n in 5" :key="n" :value="n">{{ n }} 星以上</option>
        </select>
        <input v-model="form.date_from" type="date" />
        <input v-model="form.date_to" type="date" />
        <button class="btn primary" :disabled="searching" @click="run">检索</button>
      </div>
      <div v-if="history.length" class="row" style="margin-top: 8px">
        <span v-for="q in history" :key="q" class="tag" style="cursor: pointer" @click="useHistory(q)">{{
          q
        }}</span>
      </div>
    </div>

    <div v-if="result" class="panel">
      <div class="row small muted">
        <span>命中 {{ result.items.length }} 条</span>
        <span>模式 {{ result.mode }}</span>
        <span>总耗时 {{ result.timings.total_ms }}ms（关键词 {{ result.timings.keyword_ms }}ms /
          向量 {{ result.timings.vector_ms }}ms）</span>
        <span v-if="result.degraded" class="tag red">已降级（无嵌入或失败，走关键词）</span>
      </div>
    </div>

    <div v-if="result?.items.length" class="cards">
      <ImageCard
        v-for="img in result.items"
        :key="img.id"
        :image="img"
        :selectable="false"
        @open="(i) => (openId = i.id)"
      />
    </div>
    <div v-else-if="result" class="empty">没有匹配结果</div>

    <ImageDrawer v-if="openId" :image-id="openId" @close="openId = null" />
  </div>
</template>

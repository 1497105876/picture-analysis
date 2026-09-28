<script setup>
import { onMounted, ref } from "vue";
import { api, notify, thumbUrl } from "../api.js";

const question = ref("");
const busy = ref(false);
const messages = ref([]);
const openId = ref(null);

async function send() {
  const q = question.value.trim();
  if (!q || busy.value) return;
  busy.value = true;
  messages.value.push({ role: "me", text: q });
  question.value = "";
  try {
    const data = await api.post("/api/chat", { question: q });
    messages.value.push({
      role: "bot",
      text: data.answer,
      degraded: data.degraded,
      items: data.items || [],
    });
  } catch (e) {
    messages.value.push({ role: "bot", text: `出错了：${e.message}`, degraded: true, items: [] });
  } finally {
    busy.value = false;
  }
}

onMounted(() => {
  messages.value.push({
    role: "bot",
    text: "你好，我可以按自然语言找图，例如「去年夏天在海边拍的照片」。对话不可用时会自动降级为关键词检索。",
    items: [],
  });
});
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>对话</h1>
        <div class="sub">自然语言问图（软失败：不可用时引导去检索页，主链路不受影响）</div>
      </div>
    </div>

    <div class="panel">
      <div class="chat-thread">
        <div v-for="(m, i) in messages" :key="i" class="bubble" :class="{ me: m.role === 'me' }">
          <div>{{ m.text }}</div>
          <div v-if="m.degraded" class="small" style="opacity: 0.75">（已降级）</div>
          <div v-if="m.items?.length" class="cards" style="grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); margin-top: 8px">
            <div v-for="it in m.items" :key="it.id" class="card" @click="openId = it.id">
              <div class="ph"><img :src="thumbUrl(it.id)" :alt="it.filename" /></div>
              <div class="meta"><div class="name">{{ it.filename }}</div></div>
            </div>
          </div>
        </div>
      </div>
      <div class="row">
        <input
          v-model="question"
          class="grow"
          placeholder="想找回什么图？"
          @keyup.enter="send"
        />
        <button class="btn primary" :disabled="busy || !question.trim()" @click="send">
          {{ busy ? "思考中…" : "发送" }}
        </button>
      </div>
    </div>

    <div v-if="openId" class="drawer-mask" @click="openId = null"></div>
    <aside v-if="openId" class="drawer">
      <div class="row" style="justify-content: space-between">
        <h2>图片 #{{ openId }}</h2>
        <button class="btn small" @click="openId = null">关闭</button>
      </div>
      <img class="preview" :src="thumbUrl(openId)" alt="" />
    </aside>
  </div>
</template>

<script setup>
// 对话问图：软失败设计——不可用时返回引导语，不会把主链路拖死。
import { nextTick, onMounted, ref } from "vue";

import { api, thumbUrl } from "../app/api.js";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import ImageDrawer from "../components/ImageDrawer.vue";
import Panel from "../components/Panel.vue";

const question = ref("");
const busy = ref(false);
const messages = ref([]);
const openId = ref(null);
const threadEl = ref(null);

async function scrollDown() {
  await nextTick();
  if (threadEl.value) threadEl.value.scrollTop = threadEl.value.scrollHeight;
}

async function send() {
  const q = question.value.trim();
  if (!q || busy.value) return;
  busy.value = true;
  messages.value.push({ role: "me", text: q });
  question.value = "";
  await scrollDown();
  try {
    const data = await api.chat(q);
    messages.value.push({
      role: "bot",
      text: data.answer,
      degraded: data.degraded,
      items: data.items || [],
      parsed: data.parsed || null,
    });
  } catch (e) {
    messages.value.push({ role: "bot", text: `出错啦：${e.message}`, degraded: true, items: [] });
  } finally {
    busy.value = false;
    await scrollDown();
  }
}

function useSuggestion(text) {
  question.value = text;
  send();
}

const SUGGESTIONS = [
  "帮我找去年海边拍的照片",
  "有哪些截图",
  "四星以上的人物照片",
];

onMounted(() => {
  messages.value.push({
    role: "bot",
    text: "我可以按自然语言找图，例如「去年夏天在海边拍的照片」。解析出来的关键词、分类、时间范围都会显示在气泡下面，方便你看它到底理解了什么。",
    items: [],
  });
});
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>对话问图</h1>
        <div class="sub">一句话找图；对话不可用时自动降级为关键词检索</div>
      </div>
    </div>

    <Panel flush>
      <div ref="threadEl" class="thread">
        <EmptyState
          v-if="!messages.length"
          compact
          icon="chat"
          title="换个说法问它"
          hint="例如「找找有猫的图片」「上周拍的截图」"
        />
        <div v-for="(m, i) in messages" :key="i" class="stack" style="gap: 6px">
          <div class="bubble" :class="m.role === 'me' ? 'bubble-me' : 'bubble-bot'">
            <div>{{ m.text }}</div>
            <div v-if="m.degraded" class="small" style="margin-top: 4px; opacity: 0.8">
              （已降级：走的关键词检索）
            </div>

            <div v-if="m.parsed" class="parsed">
              <span class="tiny dim">它理解成：</span>
              <span v-for="k in m.parsed.keywords || []" :key="k" class="tag tag-accent">{{ k }}</span>
              <span v-if="m.parsed.category" class="tag tag-outline">分类 {{ m.parsed.category }}</span>
              <span v-if="m.parsed.date_from || m.parsed.date_to" class="tag tag-outline">
                {{ m.parsed.date_from || "不限" }} ~ {{ m.parsed.date_to || "不限" }}
              </span>
              <span v-if="m.parsed.rating_min" class="tag tag-outline">{{ m.parsed.rating_min }} 星以上</span>
            </div>

            <div v-if="m.items?.length" class="grid-media" style="--card-min: 96px; margin-top: 8px">
              <div
                v-for="it in m.items"
                :key="it.id"
                class="img-card"
                role="button"
                tabindex="0"
                @click="openId = it.id"
                @keyup.enter="openId = it.id"
              >
                <div class="thumb"><img :src="thumbUrl(it.id)" :alt="it.filename" loading="lazy" /></div>
                <div class="meta" style="padding: 6px 8px">
                  <div class="tiny clamp-1">{{ it.filename }}</div>
                </div>
              </div>
            </div>
          </div>
          <div v-if="m.role === 'bot' && m.items?.length" class="tiny dim">
            共 {{ m.items.length }} 张候选，点图片可以打开详情做人工修正
          </div>
        </div>
      </div>

      <div class="composer">
        <input
          v-model="question"
          class="input"
          placeholder="想找回什么图？"
          :disabled="busy"
          @keyup.enter="send"
        />
        <button class="btn btn-primary" :disabled="busy || !question.trim()" @click="send">
          <span v-if="busy" class="spin"></span>
          <Icon v-else name="chat" :size="14" />
          {{ busy ? "思考中…" : "发送" }}
        </button>
      </div>
    </Panel>

    <div class="row small dim">
      <span>试试：</span>
      <span v-for="s in SUGGESTIONS" :key="s" class="tag tag-outline tag-click" @click="useSuggestion(s)">
        {{ s }}
      </span>
    </div>

    <ImageDrawer
      v-if="openId"
      v-model:image-id="openId"
      :ids="messages.flatMap((m) => (m.items || []).map((i) => i.id))"
      @close="openId = null"
    />
  </div>
</template>

<style scoped>
.thread {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: var(--sp-4) var(--panel-pad);
  max-height: min(62vh, 640px);
  overflow: auto;
}
.bubble {
  max-width: 78%;
  padding: 10px 13px;
  border-radius: 14px;
  font-size: var(--fs-base);
  line-height: var(--lh);
}
.bubble-bot {
  align-self: flex-start;
  background: var(--surface-2);
  border-bottom-left-radius: 4px;
}
.bubble-me {
  align-self: flex-end;
  background: var(--accent);
  color: var(--accent-contrast);
  border-bottom-right-radius: 4px;
}
.parsed {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed color-mix(in srgb, currentColor 28%, transparent);
}
.composer {
  display: flex;
  gap: var(--sp-2);
  padding: 12px var(--panel-pad);
  border-top: 1px solid var(--line);
  background: var(--surface-inset);
}
</style>

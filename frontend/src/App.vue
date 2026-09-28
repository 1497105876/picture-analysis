<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { api, toast } from "./api.js";

const route = useRoute();
const settings = ref(null);
const jobsBadge = ref(0);
const proposalsBadge = ref(0);

const MODULES = {
  gallery: { to: "/gallery", label: "图库" },
  search: { to: "/search", label: "检索" },
  dashboard: { to: "/dashboard", label: "仪表盘" },
  entities: { to: "/entities", label: "实体" },
  rules: { to: "/rules", label: "规则" },
  albums: { to: "/albums", label: "相册" },
  chat: { to: "/chat", label: "对话" },
  hidden: { to: "/hidden", label: "隐藏区" },
  trash: { to: "/trash", label: "回收站" },
  jobs: { to: "/jobs", label: "任务" },
  proposals: { to: "/proposals", label: "提案" },
};

const navItems = computed(() => {
  const raw = settings.value?.values?.sidebar_modules;
  let keys;
  if (Array.isArray(raw)) keys = raw;
  else if (typeof raw === "string") keys = raw.split(",");
  else keys = Object.keys(MODULES);
  return keys.map((k) => MODULES[k.trim()]).filter(Boolean);
});

const theme = computed(() => settings.value?.values?.theme || "system");
const privacy = computed(() => Boolean(settings.value?.values?.privacy_mode));

async function refresh() {
  try {
    settings.value = await api.get("/api/settings");
  } catch (e) {
    console.error(e);
  }
}

async function refreshBadges() {
  try {
    const jobs = await api.get("/api/jobs");
    jobsBadge.value = (jobs.counts?.pending || 0) + (jobs.counts?.paused || 0);
  } catch {
    /* 忽略 */
  }
  try {
    const props = await api.get("/api/proposals", { status: "pending" });
    proposalsBadge.value = props.items?.length || 0;
  } catch {
    /* 忽略 */
  }
}

function applyTheme() {
  const t = theme.value;
  const dark =
    t === "dark" ||
    (t === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

onMounted(() => {
  refresh();
  refreshBadges();
  applyTheme();
  setInterval(refreshBadges, 5000);
  window.addEventListener("settings-saved", () => {
    refresh().then(applyTheme);
  });
});

function isActive(to) {
  return route.path === to || route.path.startsWith(to + "/");
}
</script>

<template>
  <div class="layout" :class="{ masked: privacy }">
    <aside class="sidebar">
      <div class="brand"><span class="dot"></span>图库分析</div>
      <router-link
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="nav-item"
        :class="{ active: isActive(item.to) }"
      >
        <span>{{ item.label }}</span>
        <span v-if="item.to === '/jobs' && jobsBadge" class="badge">{{ jobsBadge }}</span>
        <span v-if="item.to === '/proposals' && proposalsBadge" class="badge">{{
          proposalsBadge
        }}</span>
      </router-link>
      <div class="nav-item" :class="{ active: isActive('/settings') }" @click="$router.push('/settings')">
        <span>设置</span>
      </div>
    </aside>

    <main class="main">
      <router-view :settings="settings" @saved="refresh().then(applyTheme)" />
    </main>

    <div class="toasts">
      <div
        v-for="t in toast.items"
        :key="t.id"
        class="toast"
        :class="t.level"
      >
        {{ t.message }}
      </div>
    </div>
  </div>
</template>

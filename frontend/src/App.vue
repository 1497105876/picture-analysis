<script setup>
// 应用外壳：侧栏 + 顶栏 + 内容 + 全局浮层。
// 这里也是唯一的全局轮询点（健康 / 通知 / 角标计数），页面自己不再起定时器。
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api, safe } from "./app/api.js";
import { backend, clearNotices, loadNotices, notices, unreadCount, markAllSeen, checkHealth } from "./app/notices.js";
import {
  ACCENTS,
  MODULE_GROUPS,
  applyAppearance,
  loadSettings,
  setSetting,
  settings,
  sidebarModules,
  privacyMode,
} from "./app/settings.js";
import { notify } from "./app/toast.js";
import { datetime } from "./app/format.js";
import { loadCatalog } from "./app/catalog.js";
import Icon from "./components/Icon.vue";
import ToastHost from "./components/ToastHost.vue";

const route = useRoute();
const router = useRouter();

const counts = ref({ jobs: 0, proposals: 0 });
const booted = ref(false);
const query = ref("");
const searchEl = ref(null);

const showPop = ref(""); // "" | notices | appearance
const busyingHealth = ref(false);

const navGroups = computed(() =>
  MODULE_GROUPS.map((g) => ({
    group: g,
    items: sidebarModules.value.filter((m) => m.group === g),
  })).filter((g) => g.items.length),
);

const title = computed(() => route.meta.title || "");
const inFlight = ref(false);

function isActive(to) {
  return route.path === to || route.path.startsWith(`${to}/`);
}

function badgeFor(key) {
  if (key === "jobs") return counts.value.jobs;
  if (key === "proposals") return counts.value.proposals;
  if (key === "ops") return unreadCount.value;
  return 0;
}

// ---------------------------------------------------------------- 轮询
async function refreshBadges() {
  if (inFlight.value || document.hidden) return;
  inFlight.value = true;
  try {
    const [jobs, props] = await Promise.all([
      safe(() => api.jobs(), null),
      safe(() => api.proposals("pending"), null),
    ]);
    if (jobs?.counts) counts.value.jobs = (jobs.counts.pending || 0) + (jobs.counts.paused || 0);
    if (props?.items) counts.value.proposals = props.items.length;
  } finally {
    inFlight.value = false;
  }
}

let timer = null;
function startPolling() {
  const tick = async () => {
    if (document.hidden) return;
    await Promise.all([checkHealth(), loadNotices(30), refreshBadges()]);
  };
  tick();
  timer = setInterval(tick, 12000);
}

async function boot() {
  try {
    await loadSettings();
  } catch {
    notify("读不到后端设置：先把服务跑起来再刷新", "error");
  }
  await Promise.all([checkHealth(), loadNotices(30), loadCatalog(), refreshBadges()]);
  booted.value = true;
  startPolling();
}

onMounted(boot);
onBeforeUnmount(() => timer && clearInterval(timer));

// ---------------------------------------------------------------- 交互
function togglePop(which) {
  if (showPop.value === which) {
    showPop.value = "";
    return;
  }
  showPop.value = which;
  if (which === "notices") loadNotices(30);
  if (which === "") return;
  setTimeout(() => {
    const close = (e) => {
      if (!e.target.closest?.(".pop") && !e.target.closest?.(".icon-btn")) {
        showPop.value = "";
        document.removeEventListener("click", close);
      }
    };
    document.addEventListener("click", close);
  });
}

async function onClearNotices() {
  try {
    await clearNotices();
    notify("通知已清空", "ok");
  } catch (e) {
    notify(e.message, "error");
  }
}

function submitSearch() {
  const q = query.value.trim();
  router.push(q ? { path: "/search", query: { q } } : { path: "/search" });
  showPop.value = "";
}

async function pickMode(mode) {
  try {
    await setSetting("theme", mode);
    applyAppearance();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function pickAccent(accent) {
  const hit = ACCENTS.find((a) => a.name === accent);
  try {
    await setSetting("accent", hit ? hit.color : accent);
    applyAppearance();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function pickDensity(density) {
  try {
    await setSetting("card_density", density);
    applyAppearance();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function retryHealth() {
  busyingHealth.value = true;
  await checkHealth();
  await loadNotices(30);
  busyingHealth.value = false;
  notify(backend.online ? "已连上后端" : "仍然连不上，检查服务是否在运行", backend.online ? "ok" : "error");
}

function onGlobalKey(e) {
  const tag = e.target?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  if (e.key === "/") {
    e.preventDefault();
    searchEl.value?.focus();
  }
}
onMounted(() => window.addEventListener("keydown", onGlobalKey, true));
onBeforeUnmount(() => window.removeEventListener("keydown", onGlobalKey, true));

const currentAccent = computed(() => String(settings.values.accent || "").toLowerCase());
const currentMode = computed(() => String(settings.values.theme || "system"));
const currentDensity = computed(() => String(settings.values.card_density || "comfortable"));
</script>

<template>
  <div class="shell" :class="{ masked: privacyMode }">
    <!-- 侧栏 -->
    <aside class="sidebar">
      <div class="brand">
        <span class="logo"><Icon name="image" :size="15" /></span>
        <span class="stack" style="gap: 0">
          <span>picture-analysis</span>
          <span class="tiny dim" style="font-weight: 400">本地图片索引库</span>
        </span>
      </div>

      <nav class="nav">
        <template v-for="g in navGroups" :key="g.group">
          <div class="nav-group-title">{{ g.group }}</div>
          <router-link
            v-for="m in g.items"
            :key="m.key"
            :to="m.to"
            class="nav-item"
            :class="{ 'is-active': isActive(m.to) }"
          >
            <Icon :name="m.icon" :size="15" />
            <span class="clamp-1">{{ m.label }}</span>
            <span v-if="badgeFor(m.key)" class="count">{{ badgeFor(m.key) }}</span>
            <span v-else-if="m.fresh" class="count count-dim">新</span>
          </router-link>
        </template>
      </nav>

      <div class="sidebar-foot">
        <router-link to="/settings" class="nav-item" style="padding: 6px 8px">
          <Icon name="gear" :size="14" /> 设置
        </router-link>
        <span class="mono">v{{ backend.version || "—" }}</span>
      </div>
    </aside>

    <!-- 右侧 -->
    <div class="stack" style="flex: 1; min-width: 0">
      <header class="topbar">
        <div class="crumb">
          <span>picture-analysis</span>
          <Icon name="chevronRight" :size="12" />
          <b>{{ title }}</b>
        </div>

        <div class="spacer"></div>

        <div class="searchbox">
          <Icon name="search" :size="14" />
          <input
            ref="searchEl"
            v-model="query"
            placeholder="找图（按 / 聚焦）"
            @keyup.enter="submitSearch"
          />
          <kbd v-if="!query" class="tiny dim">/</kbd>
        </div>

        <!-- 连接状态 -->
        <button
          class="icon-btn"
          :title="backend.online ? '后端在线' : '后端未连接，点击重试'"
          @click="retryHealth"
        >
          <Icon name="cpu" :size="16" :style="backend.online ? {} : { color: 'var(--danger)' }" />
        </button>

        <!-- 通知 -->
        <div style="position: relative">
          <button class="icon-btn" :class="{ 'is-on': showPop === 'notices' }" title="通知" @click="togglePop('notices')">
            <Icon name="bell" :size="16" />
            <span v-if="unreadCount" class="dot">{{ unreadCount > 99 ? "99+" : unreadCount }}</span>
          </button>
          <div v-if="showPop === 'notices'" class="pop" style="right: 0; top: 38px; width: 360px">
            <div class="pop-head">
              <span>通知</span>
              <button class="btn btn-xs" @click="onClearNotices">清空</button>
            </div>
            <div class="pop-body" @mouseleave="markAllSeen">
              <template v-if="notices.items.length">
                <div v-for="n in notices.items" :key="n.id" class="notice-item" :class="`lv-${n.level}`">
                  <span class="pin"></span>
                  <div class="stack" style="gap: 2px; min-width: 0">
                    <div class="wrap-anywhere">{{ n.message }}</div>
                    <div class="tiny dim">{{ n.kind }} · {{ datetime(n.created_at) }}</div>
                  </div>
                </div>
              </template>
              <div v-else class="empty" style="padding: 26px 12px">
                <div class="small dim">没有通知</div>
              </div>
            </div>
            <div class="pop-sep"></div>
            <router-link to="/ops" class="pop-item small" @click="showPop = ''">
              <Icon name="gear" :size="13" /> 去运维页看日志与全部通知
            </router-link>
          </div>
        </div>

        <!-- 外观 -->
        <div style="position: relative">
          <button class="icon-btn" :class="{ 'is-on': showPop === 'appearance' }" title="外观" @click="togglePop('appearance')">
            <Icon name="palette" :size="16" />
          </button>
          <div v-if="showPop === 'appearance'" class="pop" style="right: 0; top: 38px; width: 300px">
            <div class="modal-body stack-3" style="padding: 12px">
              <div class="field">
                <span class="lab">模式</span>
                <div class="seg">
                  <button :class="{ 'is-on': currentMode === 'light' }" @click="pickMode('light')">亮色</button>
                  <button :class="{ 'is-on': currentMode === 'dark' }" @click="pickMode('dark')">暗色</button>
                  <button :class="{ 'is-on': currentMode === 'system' }" @click="pickMode('system')">跟随系统</button>
                </div>
              </div>
              <div class="field">
                <span class="lab">强调色</span>
                <div class="row" style="gap: 6px">
                  <button
                    v-for="a in ACCENTS"
                    :key="a.name"
                    class="swatch"
                    :class="{ 'is-on': currentAccent === a.color.toLowerCase() }"
                    :style="{ background: a.color }"
                    :title="a.label"
                    @click="pickAccent(a.name)"
                  ></button>
                </div>
              </div>
              <div class="field">
                <span class="lab">密度</span>
                <div class="seg">
                  <button :class="{ 'is-on': currentDensity === 'comfortable' }" @click="pickDensity('comfortable')">宽松</button>
                  <button :class="{ 'is-on': currentDensity === 'compact' }" @click="pickDensity('compact')">紧凑</button>
                </div>
              </div>
              <router-link to="/settings" class="btn btn-sm btn-block" @click="showPop = ''">
                更多外观与全局设置
              </router-link>
            </div>
          </div>
        </div>
      </header>

      <!-- 断连横幅 -->
      <div v-if="booted && !backend.online" class="banner banner-danger" style="margin: 12px var(--sp-5) 0; border-radius: var(--radius)">
        <Icon name="warning" :size="16" style="margin-top: 2px" />
        <div class="stack" style="gap: 2px">
          <div class="strong">连不上后端服务</div>
          <div class="small">在项目根目录执行 <code>python server.py</code>，然后点右上角处理器图标重试。</div>
        </div>
        <button class="btn btn-sm" style="margin-left: auto" :disabled="busyingHealth" @click="retryHealth">重试</button>
      </div>

      <main class="app-main">
        <router-view v-slot="{ Component }">
          <component :is="Component" />
        </router-view>
      </main>
    </div>

    <ToastHost />
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: 100%;
}
.swatch {
  width: 22px;
  height: 22px;
  border-radius: 7px;
  border: 2px solid transparent;
  box-shadow: 0 0 0 1px var(--line-strong);
  cursor: pointer;
  padding: 0;
}
.swatch.is-on {
  border-color: var(--surface);
  box-shadow: 0 0 0 2px var(--accent);
}
.masked .app-main :deep(.img-card .thumb img) {
  filter: blur(20px);
  transform: scale(1.06);
}
@media (max-width: 720px) {
  .sidebar {
    width: 60px;
  }
  .sidebar .brand span.stack,
  .sidebar .nav-group-title,
  .nav-item span.clamp-1 {
    display: none;
  }
  .sidebar .nav-item {
    justify-content: center;
  }
}
</style>

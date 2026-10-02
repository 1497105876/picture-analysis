import { createRouter, createWebHistory } from "vue-router";

const routes = [
  { path: "/", redirect: "/gallery" },
  { path: "/gallery", component: () => import("./pages/Gallery.vue"), meta: { title: "图库", icon: "image" } },
  { path: "/search", component: () => import("./pages/Search.vue"), meta: { title: "检索", icon: "search" } },
  { path: "/dashboard", component: () => import("./pages/Dashboard.vue"), meta: { title: "仪表盘", icon: "chart" } },
  { path: "/albums", component: () => import("./pages/Albums.vue"), meta: { title: "智能相册", icon: "album" } },
  { path: "/albums/:id", component: () => import("./pages/Albums.vue"), meta: { title: "智能相册", icon: "album" } },
  { path: "/entities", component: () => import("./pages/Entities.vue"), meta: { title: "实体资料库", icon: "user" } },
  { path: "/categories", component: () => import("./pages/Categories.vue"), meta: { title: "分类与字段", icon: "tag" } },
  { path: "/rules", component: () => import("./pages/Rules.vue"), meta: { title: "分类规则", icon: "rule" } },
  { path: "/proposals", component: () => import("./pages/Proposals.vue"), meta: { title: "提案", icon: "inbox" } },
  { path: "/chat", component: () => import("./pages/Chat.vue"), meta: { title: "对话问图", icon: "chat" } },
  { path: "/jobs", component: () => import("./pages/Jobs.vue"), meta: { title: "任务队列", icon: "task" } },
  { path: "/ops", component: () => import("./pages/Ops.vue"), meta: { title: "运维", icon: "gear" } },
  { path: "/hidden", component: () => import("./pages/Hidden.vue"), meta: { title: "隐藏区", icon: "eye-off" } },
  { path: "/trash", component: () => import("./pages/Trash.vue"), meta: { title: "回收站", icon: "trash" } },
  { path: "/health", component: () => import("./pages/Health.vue"), meta: { title: "断链体检", icon: "unlink" } },
  { path: "/settings", component: () => import("./pages/Settings.vue"), meta: { title: "设置", icon: "gear" } },
  { path: "/:pathMatch(.*)*", redirect: "/gallery" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});

router.afterEach((to) => {
  const title = to.meta?.title;
  document.title = title ? `${title} · picture-analysis` : "picture-analysis";
});

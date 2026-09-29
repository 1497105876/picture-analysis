import { createApp } from "vue";

import App from "./App.vue";
import { router } from "./router.js";

import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components.css";

// 页面大多会自己处理错误；这里兜住没人接管的异步异常，避免静默失败。
window.addEventListener("unhandledrejection", (e) => {
  console.error("[pa] 未接管的异步异常：", e.reason);
});

createApp(App).use(router).mount("#app");

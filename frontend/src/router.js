import { createRouter, createWebHistory } from "vue-router";

import Gallery from "./pages/Gallery.vue";
import Search from "./pages/Search.vue";
import Dashboard from "./pages/Dashboard.vue";
import Entities from "./pages/Entities.vue";
import Rules from "./pages/Rules.vue";
import Albums from "./pages/Albums.vue";
import Chat from "./pages/Chat.vue";
import Hidden from "./pages/Hidden.vue";
import Trash from "./pages/Trash.vue";
import Jobs from "./pages/Jobs.vue";
import Proposals from "./pages/Proposals.vue";
import Settings from "./pages/Settings.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/gallery" },
    { path: "/gallery", component: Gallery },
    { path: "/search", component: Search },
    { path: "/dashboard", component: Dashboard },
    { path: "/entities", component: Entities },
    { path: "/rules", component: Rules },
    { path: "/albums", component: Albums },
    { path: "/albums/:id", component: Albums },
    { path: "/chat", component: Chat },
    { path: "/hidden", component: Hidden },
    { path: "/trash", component: Trash },
    { path: "/jobs", component: Jobs },
    { path: "/proposals", component: Proposals },
    { path: "/settings", component: Settings },
    { path: "/:pathMatch(.*)*", redirect: "/gallery" },
  ],
});

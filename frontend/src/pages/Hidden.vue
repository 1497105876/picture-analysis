<script setup>
// 隐藏区：持久隐藏状态。在图库/检索/相册/SQLite 直读里全部不可见，且没有任何参数能绕过。
import { computed, onMounted, ref } from "vue";

import { api } from "../app/api.js";
import { notify } from "../app/toast.js";
import { privacyMode } from "../app/settings.js";
import { useList } from "../app/useList.js";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import ImageDrawer from "../components/ImageDrawer.vue";
import ImageGrid from "../components/ImageGrid.vue";

const selected = ref(new Set());
const openId = ref(null);
const view = ref("grid");
const sort = ref("mtime");
const busy = ref(false);

const list = useList(api.hidden, { pageSize: 60 });
const ids = computed(() => list.items.value.map((i) => i.id));

const params = computed(() => ({ sort: sort.value, order: "desc" }));

function reload() {
  selected.value = new Set();
  return list.reload(params.value);
}

function toggleSelect(id) {
  const next = new Set(selected.value);
  next.has(id) ? next.delete(id) : next.add(id);
  selected.value = next;
}

const picked = computed(() => [...selected.value]);

async function unhide(ids) {
  busy.value = true;
  try {
    const res = await api.batch("unhide", ids);
    notify(`已恢复 ${res.count ?? ids.length} 张到正常索引`, "ok");
    selected.value = new Set();
    await reload();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

async function deleteForever() {
  busy.value = true;
  try {
    await api.batch("delete", picked.value);
    notify(`已删除 ${picked.value.length} 张的索引`, "ok");
    selected.value = new Set();
    await reload();
  } catch (e) {
    notify(e.message, "error");
  } finally {
    busy.value = false;
  }
}

onMounted(reload);
</script>

<template>
  <div class="stack-4">
    <div class="page-head">
      <div class="stack" style="gap: 3px">
        <h1>隐藏区</h1>
        <div class="sub">{{ list.items.value.length }} 张处于隐藏状态</div>
      </div>
      <div class="head-actions">
        <select v-model="sort" class="select select-sm" style="width: 120px" @change="reload">
          <option value="mtime">修改时间</option>
          <option value="created">入库时间</option>
          <option value="filename">文件名</option>
        </select>
        <div class="seg">
          <button :class="{ 'is-on': view === 'grid' }" @click="view = 'grid'">
            <Icon name="grid" :size="13" />
          </button>
          <button :class="{ 'is-on': view === 'list' }" @click="view = 'list'">
            <Icon name="list" :size="13" />
          </button>
        </div>
        <button class="btn btn-primary btn-sm" :disabled="!picked.length || busy" @click="unhide(picked)">
          <Icon name="eye" :size="13" /> 批量恢复
        </button>
        <button class="btn btn-sm btn-danger" :disabled="!picked.length || busy" @click="deleteForever">
          <Icon name="trash" :size="13" /> 删索引
        </button>
      </div>
    </div>

    <div class="banner banner-dashed">
      <Icon name="eye-off" :size="16" style="margin-top: 2px" />
      <div class="stack" style="gap: 3px">
        <div class="strong">这是持久隐藏，不是临时遮罩</div>
        <div class="small">
          图片在图库、检索、智能相册与 SQLite 直读中全部不可见，也没有任何查询参数能绕过——服务端会直接拒绝
          <code>hidden</code> 之类的参数。与「隐私模式」不同，隐私模式只是在界面上打码。
          文件仍在原处，识别与备份照常进行，随时可以从这里恢复。
        </div>
      </div>
    </div>

    <ImageGrid
      :items="list.items.value"
      :loading="list.loading.value"
      :loading-more="list.loadingMore.value"
      :has-more="Boolean(list.cursor.value)"
      :error="list.error.value"
      :view="view"
      :selected="selected"
      :masked="privacyMode"
      empty-title="隐藏区是空的"
      empty-hint="在图片详情里点「移入隐藏区」，这张图就会从所有检索面消失。"
      @open="(img) => (openId = img.id)"
      @toggle="toggleSelect"
      @select-all="(list) => (selected = new Set([...selected, ...list]))"
      @clear-selection="selected = new Set()"
      @load-more="list.more(params)"
    />

    <ImageDrawer
      v-if="openId"
      v-model:image-id="openId"
      :ids="ids"
      @close="openId = null"
      @changed="reload"
    />
  </div>
</template>

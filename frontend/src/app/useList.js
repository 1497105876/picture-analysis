// 列表加载器：统一处理「首屏 / 翻页 / 出错」三态。
// 页面只需要提供一个返回 { items, next_cursor } 的取数函数。
import { ref } from "vue";

export function useList(fetcher, { pageSize = 48 } = {}) {
  const items = ref([]);
  const cursor = ref(null);
  const loading = ref(false);
  const loadingMore = ref(false);
  const error = ref("");
  const total = ref(null);

  async function reload(params = {}) {
    loading.value = true;
    error.value = "";
    try {
      const data = await fetcher({ ...params, limit: pageSize });
      items.value = data?.items || [];
      cursor.value = data?.next_cursor || null;
      total.value = data?.total ?? null;
      return data;
    } catch (e) {
      items.value = [];
      cursor.value = null;
      error.value = e.message;
      return null;
    } finally {
      loading.value = false;
    }
  }

  async function more(params = {}) {
    if (!cursor.value || loadingMore.value || loading.value) return;
    loadingMore.value = true;
    try {
      const data = await fetcher({ ...params, cursor: cursor.value, limit: pageSize });
      const fresh = data?.items || [];
      const seen = new Set(items.value.map((i) => i.id));
      items.value = [...items.value, ...fresh.filter((i) => !seen.has(i.id))];
      cursor.value = data?.next_cursor || null;
      return data;
    } catch (e) {
      error.value = e.message;
      return null;
    } finally {
      loadingMore.value = false;
    }
  }

  function reset() {
    items.value = [];
    cursor.value = null;
    error.value = "";
  }

  /** 把某一项替换为最新值（保存后局部刷新，避免整页回弹） */
  function replace(row) {
    const i = items.value.findIndex((x) => x.id === row.id);
    if (i >= 0) items.value[i] = { ...items.value[i], ...row };
  }

  function remove(id) {
    items.value = items.value.filter((x) => x.id !== id);
  }

  return { items, cursor, loading, loadingMore, error, total, reload, more, reset, replace, remove };
}

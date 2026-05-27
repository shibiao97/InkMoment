import { computed, onBeforeUnmount, ref } from "vue";
import {
  confirmPrescreen,
  getAutoRejected,
  getGroupingProgress,
  getStatus,
  restoreRejected,
} from "../api/inkmoment";

const GROUPING_POLL_MS = 900;

function itemKey(item) {
  return item?.original_path || item?.path || item?.name || "";
}

function normalizeItem(item) {
  const key = itemKey(item);
  return {
    ...item,
    key,
    name: item?.name || key.split("/").pop() || "未命名照片",
    path: item?.path || item?.original_path || key,
    reason: item?.reason || "智能初筛",
    restored: Boolean(item?.restored),
  };
}

export function usePrescreenReview() {
  const status = ref(null);
  const items = ref([]);
  const activeReason = ref("all");
  const loading = ref(false);
  const error = ref("");
  const confirming = ref(false);
  const confirmResult = ref(null);
  const grouping = ref(null);
  const groupingSamples = ref([]);
  const restoringKeys = ref([]);
  let groupingTimer = null;
  let groupingSince = 0;

  const restoringKeySet = computed(() => new Set(restoringKeys.value));
  const pendingItems = computed(() => items.value.filter((item) => !item.restored));

  const stats = computed(() => {
    const restored = items.value.filter((item) => item.restored).length;
    const rejected = items.value.length || status.value?.prescreen_auto_rejected_count || 0;
    return {
      totalPhotos: status.value?.image_count || 0,
      rejected,
      restored,
      pending: Math.max(0, rejected - restored),
    };
  });

  const reasonFilters = computed(() => {
    const counts = new Map();
    for (const item of items.value) {
      counts.set(item.reason, (counts.get(item.reason) || 0) + 1);
    }
    const filters = [{ id: "all", label: "全部", count: items.value.length }];
    for (const [reason, count] of counts.entries()) {
      filters.push({ id: reason, label: reason, count });
    }
    return filters;
  });

  const filteredItems = computed(() => {
    if (activeReason.value === "all") return items.value;
    return items.value.filter((item) => item.reason === activeReason.value);
  });

  function setRestoring(key, isRestoring) {
    const next = new Set(restoringKeys.value);
    if (isRestoring) {
      next.add(key);
    } else {
      next.delete(key);
    }
    restoringKeys.value = [...next];
  }

  function isRestoring(item) {
    return restoringKeySet.value.has(itemKey(item));
  }

  function updateItemRestored(key) {
    items.value = items.value.map((item) => {
      if (itemKey(item) !== key) return item;
      return { ...item, restored: true };
    });
  }

  function stopGroupingPolling() {
    if (groupingTimer) {
      window.clearInterval(groupingTimer);
      groupingTimer = null;
    }
  }

  async function refreshStatusOnly() {
    status.value = await getStatus();
  }

  async function load() {
    loading.value = true;
    error.value = "";
    try {
      const [nextStatus, rejectedData] = await Promise.all([
        getStatus(),
        getAutoRejected(),
      ]);
      status.value = nextStatus;
      items.value = (rejectedData?.items || []).map(normalizeItem);
      const hasActiveReason = reasonFilters.value.some((item) => item.id === activeReason.value);
      if (!hasActiveReason) activeReason.value = "all";
    } catch (err) {
      error.value = err.message || "读取初筛列表失败";
    } finally {
      loading.value = false;
    }
  }

  async function restoreOne(item) {
    const key = itemKey(item);
    if (!key || item.restored || isRestoring(item)) return false;

    error.value = "";
    setRestoring(key, true);
    try {
      await restoreRejected({
        group_id: item.group_id,
        path: item.original_path || item.path,
      });
      updateItemRestored(key);
      await refreshStatusOnly();
      return true;
    } catch (err) {
      error.value = err.message || "恢复照片失败";
      return false;
    } finally {
      setRestoring(key, false);
    }
  }

  async function restoreAllPending() {
    for (const item of pendingItems.value) {
      const ok = await restoreOne(item);
      if (!ok) return false;
    }
    return true;
  }

  async function refreshGrouping() {
    try {
      const data = await getGroupingProgress(groupingSince);
      const nextGroups = data?.groups || [];
      if (nextGroups.length) {
        groupingSamples.value = [...groupingSamples.value, ...nextGroups];
        groupingSince += nextGroups.length;
      }
      grouping.value = {
        ...data,
        groups: groupingSamples.value,
      };
      if (data?.status === "done" || data?.status === "error") {
        stopGroupingPolling();
        await refreshStatusOnly();
      }
    } catch (err) {
      grouping.value = {
        status: "error",
        error: err.message || "读取分组进度失败",
        groups: groupingSamples.value,
      };
      stopGroupingPolling();
    }
  }

  function startGroupingPolling() {
    stopGroupingPolling();
    groupingSince = 0;
    groupingSamples.value = [];
    grouping.value = {
      status: "running",
      groups: [],
      total: 0,
      multi: 0,
      error: null,
    };
    refreshGrouping();
    groupingTimer = window.setInterval(refreshGrouping, GROUPING_POLL_MS);
  }

  async function confirmReview() {
    confirming.value = true;
    error.value = "";
    confirmResult.value = null;
    try {
      const result = await confirmPrescreen();
      confirmResult.value = result;
      if (result?.async) {
        startGroupingPolling();
      } else {
        await refreshStatusOnly();
      }
      return result;
    } catch (err) {
      error.value = err.message || "确认初筛失败";
      return null;
    } finally {
      confirming.value = false;
    }
  }

  onBeforeUnmount(stopGroupingPolling);

  return {
    status,
    items,
    activeReason,
    filteredItems,
    pendingItems,
    reasonFilters,
    stats,
    loading,
    error,
    confirming,
    confirmResult,
    grouping,
    isRestoring,
    load,
    restoreOne,
    restoreAllPending,
    confirmReview,
    refreshGrouping,
  };
}

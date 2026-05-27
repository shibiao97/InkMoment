import { computed, ref } from "vue";
import { getPreviewGroups, getStatus, regroup } from "../api/inkmoment";

function dateLabel(value) {
  if (!value) return "未标注时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10) || "未标注时间";
  return date.toLocaleDateString("zh-CN", {
    month: "long",
    day: "numeric",
  });
}

function halfDayLabel(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const hour = date.getHours();
  if (hour < 6) return "凌晨";
  if (hour < 11) return "上午";
  if (hour < 14) return "中午";
  if (hour < 17) return "下午";
  if (hour < 20) return "傍晚";
  return "夜间";
}

function chapterKey(group) {
  if (!group?.earliest_dt) return "未标注时间";
  const period = halfDayLabel(group.earliest_dt);
  return period ? `${dateLabel(group.earliest_dt)} · ${period}` : dateLabel(group.earliest_dt);
}

export function formatBurstSpan(seconds) {
  if (!seconds || seconds <= 0) return "";
  if (seconds < 5) return `约 ${seconds.toFixed(1)} 秒内`;
  if (seconds < 60) return `${Math.round(seconds)} 秒内`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟内`;
  return `${(seconds / 3600).toFixed(1)} 小时内`;
}

export function usePreviewGroups() {
  const status = ref(null);
  const groups = ref([]);
  const loading = ref(false);
  const regrouping = ref(false);
  const error = ref("");
  const thresholdNear = ref(10);
  const thresholdFar = ref(6);
  const nearMinutes = ref(5);

  const sections = computed(() => {
    const byChapter = new Map();
    for (const group of groups.value) {
      const key = chapterKey(group);
      if (!byChapter.has(key)) byChapter.set(key, []);
      byChapter.get(key).push(group);
    }
    return [...byChapter.entries()].map(([title, sectionGroups]) => ({
      title,
      groups: sectionGroups,
    }));
  });

  const title = computed(() => {
    const multi = status.value?.multi_groups || 0;
    const count = status.value?.image_count || 0;
    return `${multi.toLocaleString()} 组连拍 · ${count.toLocaleString()} 张待选`;
  });

  const statusLabel = computed(() => {
    if (error.value) return "分组需要处理";
    if (regrouping.value) return "重新分组中";
    if (loading.value) return "读取分组";
    return `${(status.value?.multi_groups || 0).toLocaleString()} 组待决`;
  });

  const statusState = computed(() => {
    if (error.value) return "error";
    if (loading.value || regrouping.value) return "busy";
    return "idle";
  });

  function syncThresholds(nextStatus) {
    thresholdNear.value = Number(nextStatus?.threshold_near ?? thresholdNear.value);
    thresholdFar.value = Number(nextStatus?.threshold_far ?? thresholdFar.value);
    nearMinutes.value = Math.round(Number(nextStatus?.near_seconds ?? 300) / 60);
  }

  async function load() {
    loading.value = true;
    error.value = "";
    try {
      const [nextStatus, previewData] = await Promise.all([
        getStatus(),
        getPreviewGroups(),
      ]);
      status.value = nextStatus;
      syncThresholds(nextStatus);
      groups.value = previewData?.groups || [];
    } catch (err) {
      error.value = err.message || "读取分组预览失败";
    } finally {
      loading.value = false;
    }
  }

  async function applyRegroup() {
    regrouping.value = true;
    error.value = "";
    try {
      await regroup({
        threshold_near: Number(thresholdNear.value),
        threshold_far: Number(thresholdFar.value),
        near_seconds: Number(nearMinutes.value) * 60,
      });
      await load();
      return true;
    } catch (err) {
      error.value = err.message || "重新分组失败";
      return false;
    } finally {
      regrouping.value = false;
    }
  }

  return {
    status,
    groups,
    sections,
    title,
    statusLabel,
    statusState,
    thresholdNear,
    thresholdFar,
    nearMinutes,
    loading,
    regrouping,
    error,
    load,
    applyRegroup,
  };
}

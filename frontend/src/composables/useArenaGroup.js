import { computed, ref } from "vue";
import {
  chooseGroup,
  getGroup,
  getStatus,
  skipGroup,
  undoGroup,
} from "../api/inkmoment";

function pickMetaValue(meta, key) {
  const value = meta?.[key];
  if (value == null || value === "") return "";
  return String(value);
}

export function formatMeta(meta, otherMeta = null) {
  if (!meta) return [];
  const fields = [
    ["camera", pickMetaValue(meta, "camera")],
    ["lens", pickMetaValue(meta, "lens")],
    ["focal_length", pickMetaValue(meta, "focal_length")],
    ["aperture", pickMetaValue(meta, "aperture")],
    ["shutter", pickMetaValue(meta, "shutter")],
    ["iso", meta.iso ? `ISO ${meta.iso}` : ""],
  ];

  return fields
    .filter(([, value]) => value)
    .map(([key, value]) => {
      const otherValue = key === "iso"
        ? (otherMeta?.iso ? `ISO ${otherMeta.iso}` : "")
        : pickMetaValue(otherMeta, key);
      return {
        key,
        value,
        different: Boolean(otherValue && otherValue !== value),
      };
    });
}

export function useArenaGroup() {
  const status = ref(null);
  const group = ref(null);
  const done = ref(false);
  const loading = ref(false);
  const busy = ref(false);
  const error = ref("");

  const totalMultiGroups = computed(() => status.value?.multi_groups || 0);
  const finishedMultiGroups = computed(() => status.value?.finished_multi_groups || 0);
  const overallPercent = computed(() => {
    if (!totalMultiGroups.value) return 0;
    return Math.min(100, Math.round((finishedMultiGroups.value / totalMultiGroups.value) * 100));
  });
  const groupPercent = computed(() => {
    const total = group.value?.total_images || 0;
    if (!total) return 0;
    return Math.min(100, Math.round(((group.value?.decided || 0) / total) * 100));
  });
  const statusLabel = computed(() => {
    if (error.value) return "选片需要处理";
    if (done.value) return "选片完成";
    if (loading.value) return "读取当前组";
    if (busy.value) return "记录选择中";
    return `${finishedMultiGroups.value} / ${totalMultiGroups.value} 组`;
  });
  const statusState = computed(() => {
    if (error.value) return "error";
    if (loading.value || busy.value) return "busy";
    if (done.value) return "done";
    return "idle";
  });

  async function refreshStatusOnly() {
    status.value = await getStatus();
  }

  async function load() {
    loading.value = true;
    error.value = "";
    try {
      const [groupData, nextStatus] = await Promise.all([
        getGroup(),
        getStatus(),
      ]);
      status.value = nextStatus;
      done.value = Boolean(groupData?.done);
      group.value = groupData?.group || null;
    } catch (err) {
      error.value = err.message || "读取当前选片组失败";
    } finally {
      loading.value = false;
    }
  }

  async function applyPayload(action) {
    busy.value = true;
    error.value = "";
    try {
      const groupData = await action();
      done.value = Boolean(groupData?.done);
      group.value = groupData?.group || null;
      try {
        await refreshStatusOnly();
      } catch (statusError) {
        error.value = statusError.message || "选择已记录，但刷新进度失败";
      }
      return true;
    } catch (err) {
      error.value = err.message || "操作失败";
      return false;
    } finally {
      busy.value = false;
    }
  }

  function choose(loser) {
    if (busy.value || loading.value) return false;
    return applyPayload(() => chooseGroup(loser));
  }

  function skip() {
    if (busy.value || loading.value) return false;
    return applyPayload(skipGroup);
  }

  function undo() {
    if (busy.value || loading.value) return false;
    return applyPayload(undoGroup);
  }

  return {
    status,
    group,
    done,
    loading,
    busy,
    error,
    overallPercent,
    groupPercent,
    statusLabel,
    statusState,
    load,
    choose,
    skip,
    undo,
  };
}

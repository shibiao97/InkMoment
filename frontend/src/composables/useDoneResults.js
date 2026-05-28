import { computed, ref } from "vue";
import { getSkipped, getStatus, getWinners, openFolder, reopenGroup } from "../api/inkmoment";
import { openDesktopPath } from "../api/runtime";

function groupBySize(winners) {
  const buckets = new Map();
  for (const item of winners) {
    const key = item.group_size > 1 ? "连拍中胜出" : "独张保留";
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(item);
  }
  return [...buckets.entries()].map(([title, items]) => ({ title, items }));
}

export function useDoneResults() {
  const status = ref(null);
  const winners = ref([]);
  const skipped = ref([]);
  const loading = ref(false);
  const opening = ref(false);
  const reopeningGroupId = ref("");
  const error = ref("");

  const total = computed(() => {
    return status.value?.image_count || ((status.value?.winner_count || 0) + (status.value?.loser_count || 0));
  });

  const kept = computed(() => status.value?.winner_count || winners.value.length || 0);
  const rejected = computed(() => status.value?.loser_count || 0);
  const singles = computed(() => {
    return Math.max(0, (status.value?.total_groups || 0) - (status.value?.multi_groups || 0));
  });

  const sections = computed(() => groupBySize(winners.value));

  const subtitle = computed(() => {
    if (!status.value?.ready) return "没有可展示的完成结果。";
    const modeWord = status.value.mode === "move" ? "移动" : "复制";
    const base = status.value.dry_run
      ? "试运行模式，没有实际搬运文件。"
      : `胜出以「${modeWord}」归到 winners/，淘汰归到 losers/。`;
    if (singles.value > 0) {
      return `${base} 其中 ${singles.value} 张无相似副本，直接保留。`;
    }
    return base;
  });

  const statusLabel = computed(() => {
    if (error.value) return "结果需要处理";
    if (loading.value) return "读取结果";
    return `留下 ${kept.value.toLocaleString()} 张`;
  });

  const statusState = computed(() => {
    if (error.value) return "error";
    if (loading.value || opening.value || reopeningGroupId.value) return "busy";
    return "done";
  });

  async function load() {
    loading.value = true;
    error.value = "";
    try {
      const [nextStatus, winnerData, skippedData] = await Promise.all([
        getStatus(),
        getWinners(),
        getSkipped(),
      ]);
      status.value = nextStatus;
      winners.value = winnerData?.winners || [];
      skipped.value = skippedData?.skipped || [];
    } catch (err) {
      error.value = err.message || "读取完成结果失败";
    } finally {
      loading.value = false;
    }
  }

  async function openOutputFolder() {
    opening.value = true;
    error.value = "";
    let desktopError = null;
    try {
      if (status.value?.folder) {
        try {
          if (await openDesktopPath(status.value.folder)) {
            return true;
          }
        } catch (err) {
          desktopError = err;
        }
      }
      await openFolder();
      return true;
    } catch (err) {
      error.value = err.message || desktopError?.message || "打开文件夹失败";
      return false;
    } finally {
      opening.value = false;
    }
  }

  async function reopenWinnerGroup(groupId) {
    if (!groupId) return false;
    reopeningGroupId.value = groupId;
    error.value = "";
    try {
      await reopenGroup(groupId);
      return true;
    } catch (err) {
      error.value = err.message || "重新打开该组失败";
      return false;
    } finally {
      reopeningGroupId.value = "";
    }
  }

  return {
    status,
    winners,
    skipped,
    sections,
    total,
    kept,
    rejected,
    singles,
    subtitle,
    statusLabel,
    statusState,
    loading,
    opening,
    reopeningGroupId,
    error,
    load,
    openOutputFolder,
    reopenWinnerGroup,
  };
}

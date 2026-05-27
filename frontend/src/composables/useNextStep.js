import { computed, ref } from "vue";
import { getStatus } from "../api/inkmoment";

function shouldShowPrescreen(status) {
  return Boolean(
    status?.prescreen_enabled &&
    !status.prescreen_reviewed &&
    !status.selection_started,
  );
}

function resolveNextStep(status) {
  if (!status?.ready) {
    return {
      kind: "home",
      title: "没有可继续的会话",
      description: "后台还没有生成选片会话，可以回到首页重新开始。",
    };
  }

  if (shouldShowPrescreen(status)) {
    if ((status.prescreen_pending_count || 0) === 0) {
      return {
        kind: "confirm-prescreen",
        title: "初筛无需复核",
        description: "本轮没有待复核的自动拒片，下一步可以直接进入分组预览。",
      };
    }
    return {
      kind: "prescreen",
      title: "进入初筛复核",
      description: `${status.prescreen_pending_count} 张照片建议放手，后续会迁移复核列表。`,
    };
  }

  if (status.finished_groups >= status.total_groups) {
    return {
      kind: "done",
      title: "查看完成结果",
      description: `已完成 ${status.finished_groups} 组，留下 ${status.winner_count} 张。`,
    };
  }

  if (status.selection_started) {
    return {
      kind: "arena",
      title: "继续选片",
      description: `还有 ${status.unfinished_groups} 组未完成，后续会迁移擂台视图。`,
    };
  }

  return {
    kind: "preview",
    title: "进入分组预览",
    description: `${status.total_groups} 个分组，其中 ${status.multi_groups} 组需要人工确认。`,
  };
}

export function useNextStep() {
  const status = ref(null);
  const loading = ref(false);
  const error = ref("");

  const nextStep = computed(() => resolveNextStep(status.value));

  async function refreshStatus() {
    loading.value = true;
    error.value = "";
    try {
      status.value = await getStatus();
    } catch (err) {
      error.value = err.message || "读取后续状态失败";
      status.value = null;
    } finally {
      loading.value = false;
    }
  }

  return {
    status,
    nextStep,
    loading,
    error,
    refreshStatus,
  };
}

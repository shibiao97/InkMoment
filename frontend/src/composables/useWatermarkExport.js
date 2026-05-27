import { computed, onBeforeUnmount, ref } from "vue";
import {
  cancelWatermark,
  getWatermarkStatus,
  getWatermarkTemplates,
  openWatermarkOutputFolder,
  previewWatermark,
  startWatermark,
} from "../api/inkmoment";

const POLL_RUNNING_MS = 500;
const POLL_RETRY_MS = 1500;

function buildConfig(template, previewIndex) {
  return {
    template: template || "A",
    preview_index: previewIndex || 0,
  };
}

export function useWatermarkExport() {
  const templates = ref([]);
  const selectedTemplate = ref("A");
  const previewIndex = ref(0);
  const totalWinners = ref(0);
  const preview = ref(null);
  const job = ref({ status: "idle" });
  const loadingTemplates = ref(false);
  const previewing = ref(false);
  const starting = ref(false);
  const cancelling = ref(false);
  const opening = ref(false);
  const error = ref("");
  let previewSeq = 0;
  let pollHandle = null;

  const isRunning = computed(() => job.value?.status === "running");
  const hasOutput = computed(() => Boolean(job.value?.out_dir));
  const progressPercent = computed(() => {
    const done = job.value?.done || 0;
    const total = job.value?.total || 0;
    if (!total) return 0;
    return Math.max(0, Math.min(100, Math.round((done / total) * 100)));
  });

  function stopPolling() {
    if (pollHandle) {
      window.clearTimeout(pollHandle);
      pollHandle = null;
    }
  }

  function schedulePoll(delay = POLL_RUNNING_MS) {
    stopPolling();
    pollHandle = window.setTimeout(refreshStatus, delay);
  }

  async function loadTemplates() {
    if (templates.value.length) return templates.value;
    loadingTemplates.value = true;
    error.value = "";
    try {
      const data = await getWatermarkTemplates();
      templates.value = data?.templates || [];
      if (!templates.value.some((item) => item.id === selectedTemplate.value)) {
        selectedTemplate.value = templates.value[0]?.id || "A";
      }
      return templates.value;
    } catch (err) {
      error.value = err.message || "加载水印样式失败";
      templates.value = [];
      return [];
    } finally {
      loadingTemplates.value = false;
    }
  }

  async function refreshPreview(nextIndex = previewIndex.value) {
    const seq = ++previewSeq;
    previewing.value = true;
    error.value = "";
    try {
      const data = await previewWatermark(buildConfig(selectedTemplate.value, nextIndex));
      if (seq !== previewSeq) return null;
      preview.value = data;
      previewIndex.value = data?.preview_index || 0;
      totalWinners.value = data?.total_winners || 0;
      return data;
    } catch (err) {
      if (seq === previewSeq) {
        error.value = err.message || "生成水印预览失败";
      }
      return null;
    } finally {
      if (seq === previewSeq) previewing.value = false;
    }
  }

  async function selectTemplate(templateId) {
    if (!templateId || templateId === selectedTemplate.value) return;
    selectedTemplate.value = templateId;
    await refreshPreview(0);
  }

  function nextPreview(delta) {
    if (totalWinners.value <= 1) return;
    const next = (previewIndex.value + delta + totalWinners.value) % totalWinners.value;
    refreshPreview(next);
  }

  async function refreshStatus() {
    try {
      const data = await getWatermarkStatus();
      job.value = data || { status: "idle" };
      if (job.value.status === "running") {
        schedulePoll(POLL_RUNNING_MS);
      } else {
        stopPolling();
      }
      return job.value;
    } catch (err) {
      error.value = err.message || "读取水印导出状态失败";
      schedulePoll(POLL_RETRY_MS);
      return null;
    }
  }

  async function startExport() {
    starting.value = true;
    error.value = "";
    try {
      const data = await startWatermark(buildConfig(selectedTemplate.value, previewIndex.value));
      job.value = {
        status: "running",
        done: 0,
        total: data?.total || 0,
        out_dir: data?.out_dir || "",
      };
      schedulePoll(0);
      return true;
    } catch (err) {
      error.value = err.message || "启动水印导出失败";
      return false;
    } finally {
      starting.value = false;
    }
  }

  async function cancelExport() {
    cancelling.value = true;
    error.value = "";
    try {
      await cancelWatermark();
      await refreshStatus();
      return true;
    } catch (err) {
      error.value = err.message || "中止水印导出失败";
      return false;
    } finally {
      cancelling.value = false;
    }
  }

  async function openOutputFolder() {
    opening.value = true;
    error.value = "";
    try {
      await openWatermarkOutputFolder();
      return true;
    } catch (err) {
      error.value = err.message || "打开水印导出目录失败";
      return false;
    } finally {
      opening.value = false;
    }
  }

  async function initialize() {
    await Promise.all([loadTemplates(), refreshStatus()]);
    if (!isRunning.value) {
      await refreshPreview(previewIndex.value);
    }
  }

  onBeforeUnmount(stopPolling);

  return {
    templates,
    selectedTemplate,
    previewIndex,
    totalWinners,
    preview,
    job,
    loadingTemplates,
    previewing,
    starting,
    cancelling,
    opening,
    error,
    isRunning,
    hasOutput,
    progressPercent,
    initialize,
    loadTemplates,
    refreshPreview,
    selectTemplate,
    nextPreview,
    refreshStatus,
    startExport,
    cancelExport,
    openOutputFolder,
  };
}

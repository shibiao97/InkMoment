import { computed, ref, unref } from "vue";
import {
  downloadDependencies,
  getDependencyDownloadStatus,
  preflightDependencies,
  startJob,
} from "../api/inkmoment";
import { pickDesktopFolder } from "../api/runtime";
import {
  canContinueLandingStartPayload,
  hasSameLandingStartPayload,
} from "./useLandingStartPayload";

const DOWNLOAD_BUSY_STATUSES = new Set(["pending", "running"]);
const DEFAULT_DOWNLOAD_WAIT_MS = 60 * 60 * 1000;
const DEFAULT_DOWNLOAD_POLL_MS = 1500;

export function useLandingDependencyFlow({
  buildStartPayload,
  validateStartInputs,
  selectedEngineLabel,
  onJobStarted,
  sleep = defaultSleep,
  downloadWaitMs = DEFAULT_DOWNLOAD_WAIT_MS,
  downloadPollMs = DEFAULT_DOWNLOAD_POLL_MS,
} = {}) {
  const startError = ref("");
  const isStarting = ref(false);
  const isCheckingDependencies = ref(false);
  const isDownloadingDependencies = ref(false);
  const lastStartPayload = ref(null);
  const dependencyReport = ref(null);
  const dependencyDownloadDir = ref("");
  const dependencyMessage = ref("");
  const dependencyError = ref("");
  const dependencyDownloadStatus = ref(null);
  const dependencyCopied = ref(false);
  const pendingStartPayload = ref(null);
  let dependencyPreflightSeq = 0;
  let dependencyDownloadSeq = 0;

  const dependencyMissingCount = computed(() => dependencyReport.value?.missing?.length || 0);
  const dependencyDownloadableCount = computed(() => (
    dependencyReport.value?.missing || []
  ).filter((item) => item.downloadable).length);
  const dependencyManualCount = computed(() => (
    dependencyReport.value?.missing || []
  ).filter((item) => !item.downloadable).length);
  const canDownloadDependencies = computed(() => {
    if (!dependencyReport.value) return false;
    return dependencyDownloadableCount.value > 0;
  });
  const dependencyPrimaryActionHint = computed(() => {
    if (!dependencyReport.value) return "先检查当前模式需要的运行资源。";
    if (dependencyReport.value.ok) return "当前模式可以直接开始。";
    if (dependencyDownloadableCount.value > 0 && dependencyManualCount.value > 0) {
      return "可以先下载模型资源，剩余 Python 依赖需要重新安装或重新打包。";
    }
    if (dependencyDownloadableCount.value > 0) return "可自动下载缺失模型资源。";
    return "当前缺失项无法自动下载，需要按提示处理后重新检查。";
  });
  const downloadStatusText = computed(() => {
    const status = dependencyDownloadStatus.value?.status || "";
    if (status === "pending") return "排队中";
    if (status === "running") return "下载中";
    if (status === "done") return "下载完成";
    if (status === "error") return "下载失败";
    return "下载中";
  });
  const downloadButtonText = computed(() => {
    if (isDownloadingDependencies.value) return downloadStatusText.value;
    if (dependencyDownloadStatus.value?.status === "error") return "重试下载";
    return pendingStartPayload.value ? "下载并继续" : "下载缺失资源";
  });
  const dependencyReportText = computed(() => {
    const report = dependencyReport.value;
    if (!report) return "";
    const lines = [
      `engine=${report.engine_label || report.engine || ""}`,
      `download_dir=${dependencyDownloadDir.value || report.download_dir || ""}`,
      `missing=${dependencyMissingCount.value}`,
      `downloadable=${dependencyDownloadableCount.value}`,
      `manual=${dependencyManualCount.value}`,
    ];
    for (const item of report.missing || []) {
      lines.push(`- ${item.label}: ${item.detail}${item.hint ? ` (${item.hint})` : ""}`);
    }
    if (dependencyError.value) {
      lines.push(`error=${dependencyError.value}`);
    }
    return lines.join("\n");
  });
  const dependencyPanelTitle = computed(() => {
    if (!dependencyReport.value) return `${unref(selectedEngineLabel) || "当前模式"}依赖检查`;
    if (dependencyReport.value.ok) return `${dependencyReport.value.engine_label}资源已就绪`;
    if (dependencyReport.value.manual_required) return `${dependencyReport.value.engine_label}需要手动处理`;
    if (dependencyReport.value.can_download) return `${dependencyReport.value.engine_label}缺少可下载资源`;
    return `${dependencyReport.value.engine_label}资源未就绪`;
  });
  const resourceState = computed(() => {
    if (isDownloadingDependencies.value) {
      return {
        state: "busy",
        label: downloadStatusText.value,
      };
    }
    if (isCheckingDependencies.value) {
      return { state: "busy", label: "检查中" };
    }
    if (!dependencyReport.value) {
      return { state: "pending", label: "待检查" };
    }
    if (dependencyReport.value.ok) {
      return { state: "ready", label: "已就绪" };
    }
    if (dependencyReport.value.manual_required) {
      return { state: "blocked", label: "需手动处理" };
    }
    if (dependencyReport.value.can_download) {
      return { state: "warning", label: "可下载" };
    }
    return { state: "blocked", label: "未就绪" };
  });
  const startButtonText = computed(() => {
    if (isDownloadingDependencies.value) return "下载中";
    if (isCheckingDependencies.value) return "检查中";
    if (isStarting.value) return "启动中";
    return "开始";
  });

  async function runDependencyPreflight(payload, options = {}) {
    const requestSeq = ++dependencyPreflightSeq;
    isCheckingDependencies.value = true;
    dependencyError.value = "";
    dependencyCopied.value = false;
    try {
      const report = await preflightDependencies({
        ...payload,
        include_folder: options.includeFolder !== false,
        model_dir: dependencyDownloadDir.value,
      });
      if (requestSeq !== dependencyPreflightSeq) return null;
      dependencyReport.value = report;
      if (report?.download_dir && !dependencyDownloadDir.value) {
        dependencyDownloadDir.value = report.download_dir;
      }
      return report;
    } catch (error) {
      if (requestSeq !== dependencyPreflightSeq) return null;
      throw error;
    } finally {
      if (requestSeq === dependencyPreflightSeq) {
        isCheckingDependencies.value = false;
      }
    }
  }

  async function handleDependencyCheckOnly() {
    startError.value = "";
    dependencyMessage.value = "";
    dependencyError.value = "";
    dependencyDownloadStatus.value = null;
    dependencyCopied.value = false;
    pendingStartPayload.value = null;

    try {
      const report = await runDependencyPreflight(buildStartPayload(), { includeFolder: false });
      if (!report) return;
      if (report.ok) {
        dependencyMessage.value = "当前模式运行资源已就绪";
      } else if ((report.missing || []).some((item) => item.downloadable)) {
        dependencyMessage.value = "发现可自动下载的缺失资源";
      } else {
        dependencyMessage.value = "当前模式仍有依赖未就绪";
      }
    } catch (error) {
      dependencyError.value = friendlyDependencyError(error, "依赖检查失败");
    }
  }

  async function launchJob(payload) {
    await startJob(payload);
    lastStartPayload.value = payload;
    pendingStartPayload.value = null;
    dependencyReport.value = null;
    dependencyDownloadStatus.value = null;
    if (typeof onJobStarted === "function") {
      onJobStarted(payload);
    }
  }

  async function handleStart() {
    startError.value = "";
    dependencyError.value = "";
    dependencyMessage.value = "";
    lastStartPayload.value = null;

    if (!validateStartInputs()) return;

    isStarting.value = true;
    try {
      const payload = buildStartPayload();
      pendingStartPayload.value = payload;
      const report = await runDependencyPreflight(payload);
      if (!report) return;
      if (!report.ok) {
        startError.value = "当前模式缺少运行资源，请先处理后再开始";
        return;
      }
      if (!hasSamePayload(payload, buildStartPayload())) {
        pendingStartPayload.value = null;
        dependencyMessage.value = "启动参数已变化，请重新点击开始以使用最新设置。";
        return;
      }
      await launchJob(payload);
    } catch (error) {
      startError.value = friendlyDependencyError(error, "启动失败");
    } finally {
      isStarting.value = false;
    }
  }

  async function handlePickDependencyFolder() {
    startError.value = "";
    dependencyError.value = "";
    try {
      const selected = await pickDesktopFolder("选择模型下载文件夹");
      if (selected) {
        dependencyDownloadDir.value = selected;
      }
    } catch (error) {
      dependencyError.value = friendlyDependencyError(error, "选择模型目录失败");
    }
  }

  async function handleDependencyRecheck() {
    startError.value = "";
    dependencyMessage.value = "";
    dependencyError.value = "";
    dependencyCopied.value = false;
    const payload = pendingStartPayload.value || buildStartPayload();
    if (pendingStartPayload.value && !canContinuePendingStartPayload(payload)) {
      dependencyMessage.value = "启动参数已变化，请重新点击开始以使用最新设置。";
      return;
    }
    try {
      const report = await runDependencyPreflight(payload);
      if (!report) return;
      if (report.ok) {
        if (pendingStartPayload.value && !canContinuePendingStartPayload(payload)) {
          dependencyMessage.value = "启动参数已变化，请重新点击开始以使用最新设置。";
          return;
        }
        dependencyMessage.value = "当前模式运行资源已就绪，正在开始处理";
        await launchJob(payload);
      } else {
        startError.value = "当前模式仍缺少运行资源";
      }
    } catch (error) {
      dependencyError.value = friendlyDependencyError(error, "检查或启动失败");
    }
  }

  async function handleDependencyDownload() {
    const downloadSeq = ++dependencyDownloadSeq;
    const shouldLaunchAfterDownload = Boolean(pendingStartPayload.value);
    const payload = pendingStartPayload.value || buildStartPayload();
    startError.value = "";
    dependencyError.value = "";
    dependencyMessage.value = "";
    dependencyCopied.value = false;
    isStarting.value = shouldLaunchAfterDownload;
    isDownloadingDependencies.value = true;

    try {
      const result = await startOrAttachDependencyDownload(payload);
      if (downloadSeq !== dependencyDownloadSeq) return;
      if (result?.download_dir) {
        dependencyDownloadDir.value = result.download_dir;
      }
      dependencyDownloadStatus.value = result || null;
      dependencyMessage.value = result?.message || "已开始下载资源";
      const finalStatus = await waitForDependencyDownload(result?.id, downloadSeq);
      if (downloadSeq !== dependencyDownloadSeq || !finalStatus) return;
      if (finalStatus?.download_dir) {
        dependencyDownloadDir.value = finalStatus.download_dir;
      }
      dependencyMessage.value = finalStatus?.message || "下载完成";
      if (shouldLaunchAfterDownload && !canContinuePendingStartPayload(payload)) {
        dependencyMessage.value = "下载完成，但启动参数已变化，请重新点击开始以使用最新设置。";
        return;
      }
      const report = await runDependencyPreflight(payload, { includeFolder: shouldLaunchAfterDownload });
      if (downloadSeq !== dependencyDownloadSeq || !report) return;
      if (!report.ok) {
        startError.value = shouldLaunchAfterDownload
          ? "下载完成，但仍有资源未就绪"
          : "";
        dependencyMessage.value = "下载完成，但当前模式仍有资源未就绪";
        return;
      }
      if (shouldLaunchAfterDownload) {
        if (!canContinuePendingStartPayload(payload)) {
          dependencyMessage.value = "下载完成，但启动参数已变化，请重新点击开始以使用最新设置。";
          return;
        }
        await launchJob(payload);
      } else {
        dependencyMessage.value = "下载完成，当前模式运行资源已就绪";
      }
    } catch (error) {
      if (downloadSeq === dependencyDownloadSeq) {
        dependencyError.value = friendlyDependencyError(error, "下载失败");
      }
    } finally {
      if (downloadSeq === dependencyDownloadSeq) {
        isDownloadingDependencies.value = false;
        isStarting.value = false;
      }
    }
  }

  async function startOrAttachDependencyDownload(payload) {
    try {
      return await downloadDependencies({
        engine: payload.engine,
        model_dir: dependencyDownloadDir.value,
      });
    } catch (error) {
      if (error.status === 409 && DOWNLOAD_BUSY_STATUSES.has(error.data?.status)) {
        dependencyMessage.value = error.data.message || "已有下载任务正在运行，已接入当前任务";
        return error.data;
      }
      throw error;
    }
  }

  async function waitForDependencyDownload(jobId, downloadSeq) {
    const startedAt = Date.now();
    while (Date.now() - startedAt < downloadWaitMs) {
      const status = await getDependencyDownloadStatus();
      if (downloadSeq !== dependencyDownloadSeq) return null;
      dependencyDownloadStatus.value = status || null;
      if (jobId && status?.id && status.id !== jobId) {
        throw new Error("下载任务状态不匹配，请重新点击下载");
      }
      if (status?.message) {
        dependencyMessage.value = status.message;
      }
      if (status?.status === "done") {
        return status;
      }
      if (status?.status === "error") {
        throw new Error(status.error || status.message || "资源下载失败");
      }
      await sleep(downloadPollMs);
    }
    throw new Error("资源下载超时，请检查网络后重试");
  }

  async function copyDependencyReport() {
    dependencyCopied.value = false;
    try {
      await navigator.clipboard.writeText(dependencyReportText.value || "");
      dependencyCopied.value = true;
    } catch (error) {
      dependencyError.value = error.message || "复制检查结果失败";
    }
  }

  function clearDependencyState() {
    dependencyPreflightSeq += 1;
    dependencyDownloadSeq += 1;
    isCheckingDependencies.value = false;
    isDownloadingDependencies.value = false;
    isStarting.value = false;
    dependencyReport.value = null;
    dependencyMessage.value = "";
    dependencyError.value = "";
    dependencyDownloadStatus.value = null;
    dependencyCopied.value = false;
    pendingStartPayload.value = null;
  }

  function clearStalePendingStartPayload() {
    if (!pendingStartPayload.value) return;
    if (hasSamePayload(pendingStartPayload.value, buildStartPayload())) return;
    pendingStartPayload.value = null;
    dependencyMessage.value = "启动参数已变化，请重新点击开始以使用最新设置。";
  }

  function canContinuePendingStartPayload(payload) {
    return canContinueLandingStartPayload(pendingStartPayload.value, buildStartPayload(), payload);
  }

  return {
    startError,
    isStarting,
    isCheckingDependencies,
    isDownloadingDependencies,
    lastStartPayload,
    dependencyReport,
    dependencyDownloadDir,
    dependencyMessage,
    dependencyError,
    dependencyDownloadStatus,
    dependencyCopied,
    pendingStartPayload,
    dependencyMissingCount,
    dependencyDownloadableCount,
    dependencyManualCount,
    canDownloadDependencies,
    dependencyPrimaryActionHint,
    dependencyPanelTitle,
    dependencyReportText,
    downloadStatusText,
    downloadButtonText,
    resourceState,
    startButtonText,
    handleDependencyCheckOnly,
    handleDependencyDownload,
    handleDependencyRecheck,
    handlePickDependencyFolder,
    handleStart,
    copyDependencyReport,
    clearDependencyState,
    clearStalePendingStartPayload,
    runDependencyPreflight,
  };
}

export function friendlyDependencyError(error, fallback) {
  const code = error?.code || "";
  const message = error?.message || fallback;
  const status = Number(error?.status || 0);
  if (code === "unauthenticated") {
    return "登录已失效，请重新登录后再检查或下载资源。";
  }
  if (code === "not_activated") {
    return "账号已登录但尚未开通。资源下载可继续，开始打卡前需要兑换 CDK。";
  }
  if (["expired", "revoked", "disabled", "device_mismatch"].includes(code)) {
    return `${message} 请处理授权状态后再继续。`;
  }
  if (status === 409) {
    return error?.data?.message || message || "已有资源下载任务正在运行。";
  }
  if (/PermissionError|denied|权限|Operation not permitted/i.test(message)) {
    return `${message} 请换一个有写入权限的下载目录。`;
  }
  if (/No space left|磁盘|空间/i.test(message)) {
    return `${message} 请清理磁盘空间或指定其他下载位置。`;
  }
  if (/timed out|timeout|Connection|网络|SSL|EOF|NameResolution|Temporary failure/i.test(message)) {
    return `${message} 请检查网络，或稍后重试下载。`;
  }
  if (status >= 500) {
    return `${message} 可打开日志复制详细错误。`;
  }
  return message;
}

function hasSamePayload(left, right) {
  return hasSameLandingStartPayload(left, right);
}

function defaultSleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

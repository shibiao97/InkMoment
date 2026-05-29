<script setup>
import { computed, ref, watch } from "vue";
import {
  downloadDependencies,
  getDependencyDownloadStatus,
  preflightDependencies,
  startJob,
} from "../api/inkmoment";
import { isTauriRuntime, pickDesktopFolder } from "../api/runtime";
import EngineSwitch from "../components/EngineSwitch.vue";
import FolderSnapshot from "../components/FolderSnapshot.vue";
import ThemePicker from "../components/ThemePicker.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useBranding } from "../composables/useBranding";
import { useFolderPeek } from "../composables/useFolderPeek";
import { useLlmConfig } from "../composables/useLlmConfig";
import { useTheme } from "../composables/useTheme";

const emit = defineEmits(["job-started"]);

const ENGINE_META = {
  fast: {
    label: "极速模式",
    resource: "本地依赖",
  },
  expert: {
    label: "专家模式",
    resource: "本地模型",
  },
  tycoon: {
    label: "土豪模式",
    resource: "模型服务",
  },
};
const DOWNLOAD_BUSY_STATUSES = new Set(["pending", "running"]);

const { branding, loadingBranding } = useBranding();
const { themes, selectedTheme, theme } = useTheme();

const folder = ref("");
const engine = ref("fast");
const mode = ref("move");
const prescreenEnabled = ref(true);
const prescreenStrength = ref("advanced");
const faceAware = ref(true);
const thresholdNear = ref(10);
const thresholdFar = ref(6);
const nearMinutes = ref(5);
const startError = ref("");
const isStarting = ref(false);
const isPickingFolder = ref(false);
const isCheckingDependencies = ref(false);
const isDownloadingDependencies = ref(false);
const lastStartPayload = ref(null);
const showLlmConfig = ref(false);
const dependencyReport = ref(null);
const dependencyDownloadDir = ref("");
const dependencyMessage = ref("");
const dependencyError = ref("");
const dependencyDownloadStatus = ref(null);
const dependencyCopied = ref(false);
const pendingStartPayload = ref(null);
const canPickFolder = isTauriRuntime();

const {
  snapshot,
  statusText,
  statusState,
} = useFolderPeek(folder);

const {
  status: llmStatus,
  models: llmModels,
  selectedModel: selectedLlmModel,
  concurrency: llmConcurrency,
  diagnostics: llmDiagnostics,
  baseUrlInput: llmBaseUrlInput,
  keyInput: llmKeyInput,
  loading: llmLoading,
  checkingModels,
  saving: llmSaving,
  error: llmError,
  message: llmMessage,
  configured: llmConfigured,
  modelReady: llmModelReady,
  refresh: refreshLlm,
  saveConfig: saveLlmConfig,
  clearConfig: clearLlmConfig,
  refreshModels,
} = useLlmConfig();
const faceAwareDisabled = computed(() => !prescreenEnabled.value || engine.value === "fast");
const llmPanelVisible = computed(() => engine.value === "tycoon" || showLlmConfig.value);
const tycoonReady = computed(() => engine.value !== "tycoon" || llmModelReady.value);
const selectedEngineMeta = computed(() => ENGINE_META[engine.value] || ENGINE_META.fast);
const selectedEngineLabel = computed(() => selectedEngineMeta.value.label);
const folderSummary = computed(() => folder.value.trim() || "未选择");
const modelSummary = computed(() => {
  if (engine.value !== "tycoon") return "无需配置";
  if (!llmConfigured.value) return "未配置 Key";
  return selectedLlmModel.value || "未选择模型";
});
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
const flowItems = computed(() => {
  const items = [
    {
      id: "engine",
      label: "模式",
      value: selectedEngineLabel.value,
      state: "ready",
    },
    {
      id: "folder",
      label: "照片文件夹",
      value: folderSummary.value,
      state: folder.value.trim() ? "ready" : "pending",
    },
  ];
  if (engine.value === "tycoon") {
    items.push({
      id: "model",
      label: "视觉模型",
      value: modelSummary.value,
      state: llmModelReady.value ? "ready" : "blocked",
    });
  }
  items.push({
    id: "resource",
    label: "运行资源",
    value: resourceState.value.label,
    state: resourceState.value.state,
  });
  return items;
});
const dependencyPanelTitle = computed(() => {
  if (!dependencyReport.value) return `${selectedEngineLabel.value}依赖检查`;
  if (dependencyReport.value.ok) return `${dependencyReport.value.engine_label}资源已就绪`;
  if (dependencyReport.value.manual_required) return `${dependencyReport.value.engine_label}需要手动处理`;
  if (dependencyReport.value.can_download) return `${dependencyReport.value.engine_label}缺少可下载资源`;
  return `${dependencyReport.value.engine_label}资源未就绪`;
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
const startButtonText = computed(() => {
  if (isDownloadingDependencies.value) return "下载中";
  if (isCheckingDependencies.value) return "检查中";
  if (isStarting.value) return "启动中";
  return "开始";
});

watch(engine, () => {
  clearDependencyState();
});

watch(folder, () => {
  pendingStartPayload.value = null;
});

watch(engine, (nextEngine) => {
  if (nextEngine === "tycoon") {
    refreshLlm({ includeModels: true, includeDiagnostics: true });
  }
});

async function handlePickFolder() {
  startError.value = "";
  isPickingFolder.value = true;

  try {
    const selected = await pickDesktopFolder();
    if (selected) {
      folder.value = selected;
    }
  } catch (error) {
    startError.value = error.message || "选择文件夹失败";
  } finally {
    isPickingFolder.value = false;
  }
}

function validateStartInputs() {
  if (!folder.value.trim()) {
    startError.value = "请填写文件夹路径";
    return false;
  }

  if (engine.value === "tycoon" && !llmModelReady.value) {
    showLlmConfig.value = true;
    startError.value = "请先配置模型服务，并选择一个可用视觉模型";
    return false;
  }

  return true;
}

function buildStartPayload() {
  return {
    folder: folder.value.trim(),
    dry_run: false,
    wipe_cache: true,
    mode: mode.value,
    engine: engine.value,
    threshold_near: Number(thresholdNear.value),
    threshold_far: Number(thresholdFar.value),
    near_seconds: Number(nearMinutes.value) * 60,
    prescreen_enabled: prescreenEnabled.value,
    prescreen_strength: prescreenStrength.value,
    face_aware: engine.value === "expert" && faceAware.value,
    llm_model: engine.value === "tycoon" ? selectedLlmModel.value : "",
  };
}

async function runDependencyPreflight(payload, options = {}) {
  isCheckingDependencies.value = true;
  dependencyError.value = "";
  dependencyCopied.value = false;
  try {
    const report = await preflightDependencies({
      ...payload,
      include_folder: options.includeFolder !== false,
      model_dir: dependencyDownloadDir.value,
    });
    dependencyReport.value = report;
    if (report?.download_dir && !dependencyDownloadDir.value) {
      dependencyDownloadDir.value = report.download_dir;
    }
    return report;
  } finally {
    isCheckingDependencies.value = false;
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
  emit("job-started", payload);
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
    if (!report.ok) {
      startError.value = "当前模式缺少运行资源，请先处理后再开始";
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
  try {
    const report = await runDependencyPreflight(payload);
    if (report.ok) {
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
    if (result?.download_dir) {
      dependencyDownloadDir.value = result.download_dir;
    }
    dependencyDownloadStatus.value = result || null;
    dependencyMessage.value = result?.message || "已开始下载资源";
    const finalStatus = await waitForDependencyDownload(result?.id);
    if (finalStatus?.download_dir) {
      dependencyDownloadDir.value = finalStatus.download_dir;
    }
    dependencyMessage.value = finalStatus?.message || "下载完成";
    const report = await runDependencyPreflight(payload, { includeFolder: shouldLaunchAfterDownload });
    if (!report.ok) {
      startError.value = shouldLaunchAfterDownload
        ? "下载完成，但仍有资源未就绪"
        : "";
      dependencyMessage.value = "下载完成，但当前模式仍有资源未就绪";
      return;
    }
    if (shouldLaunchAfterDownload) {
      await launchJob(payload);
    } else {
      dependencyMessage.value = "下载完成，当前模式运行资源已就绪";
    }
  } catch (error) {
    dependencyError.value = friendlyDependencyError(error, "下载失败");
  } finally {
    isDownloadingDependencies.value = false;
    isStarting.value = false;
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

async function waitForDependencyDownload(jobId) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < 60 * 60 * 1000) {
    const status = await getDependencyDownloadStatus();
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
    await sleep(1500);
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
  dependencyReport.value = null;
  dependencyMessage.value = "";
  dependencyError.value = "";
  dependencyDownloadStatus.value = null;
  dependencyCopied.value = false;
  pendingStartPayload.value = null;
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function friendlyDependencyError(error, fallback) {
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
</script>

<template>
  <main class="app-shell" :style="{ '--accent': theme.accent }">
    <StatusBadge :label="statusText" :state="statusState" />

    <header class="topbar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true"></span>
        <span class="brand-name">{{ branding.app_name }}</span>
      </div>

      <div class="top-actions">
        <ThemePicker v-model="selectedTheme" :themes="themes" />
        <span class="site-tag">{{ branding.tagline }}</span>
      </div>
    </header>

    <section class="hero hero-compact">
      <div>
        <p class="eyebrow">{{ loadingBranding ? "加载中" : branding.hero_eyebrow }}</p>
        <h1>{{ branding.hero_title }}</h1>
      </div>
      <p class="subtitle">{{ branding.hero_subtitle }}</p>
    </section>

    <form class="start-form" @submit.prevent="handleStart">
      <section class="flow-panel" aria-label="启动状态">
        <div
          v-for="item in flowItems"
          :key="item.id"
          class="flow-item"
          :class="`is-${item.state}`"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </section>

      <EngineSwitch v-model="engine" />

      <section v-if="llmPanelVisible" class="llm-panel">
        <div class="llm-head">
          <div>
            <div class="option-label">模型服务</div>
            <h2>土豪模式配置</h2>
          </div>
          <button class="btn-ghost" type="button" :disabled="llmLoading" @click="refreshLlm({ forceModels: true })">
            {{ llmLoading ? "检查中" : "刷新状态" }}
          </button>
        </div>

        <div class="llm-status-grid">
          <div>
            <span>Key</span>
            <strong>{{ llmConfigured ? llmStatus?.masked || "已配置" : "未配置" }}</strong>
          </div>
          <div>
            <span>并发</span>
            <strong>{{ llmConcurrency?.limit ?? "—" }}</strong>
          </div>
          <div>
            <span>可用模型</span>
            <strong>{{ llmModels.length }}</strong>
          </div>
        </div>

        <div class="llm-config-grid">
          <label>
            <span>服务地址</span>
            <input
              v-model="llmBaseUrlInput"
              type="url"
              placeholder="https://api.openai.com/v1"
              spellcheck="false"
            >
          </label>
          <label>
            <span>API Key</span>
            <input
              v-model="llmKeyInput"
              type="password"
              placeholder="粘贴新的 Key 后保存"
              autocomplete="off"
              spellcheck="false"
            >
          </label>
        </div>

        <div class="llm-actions">
          <button class="btn-primary" type="button" :disabled="llmSaving || !llmKeyInput.trim()" @click="saveLlmConfig">
            {{ llmSaving ? "保存中" : "保存并验证" }}
          </button>
          <button class="btn-ghost" type="button" :disabled="checkingModels || !llmConfigured" @click="refreshModels">
            {{ checkingModels ? "刷新中" : "刷新模型" }}
          </button>
          <button class="btn-ghost" type="button" :disabled="llmSaving || !llmConfigured" @click="clearLlmConfig">
            清除 Key
          </button>
        </div>

        <label class="llm-model-select">
          <span>视觉模型</span>
          <select v-model="selectedLlmModel" :disabled="!llmModels.length">
            <option value="">请选择模型</option>
            <option v-for="model in llmModels" :key="model.id" :value="model.id">
              {{ model.label || model.id }}
            </option>
          </select>
        </label>

        <p v-if="llmStatus?.base_url" class="llm-note">
          当前地址：{{ llmStatus.base_url }} · 来源：{{ llmStatus.base_url_source || "default" }}
        </p>
        <p v-if="llmDiagnostics?.llm" class="llm-note">
          诊断：{{ llmDiagnostics.llm.configured ? "已读取到 Key" : "未读取到 Key" }}
        </p>
        <p v-if="llmMessage" class="start-note">{{ llmMessage }}</p>
        <p v-if="llmError" class="form-error">{{ llmError }}</p>
      </section>

      <label class="field-label" for="folder-input">照片文件夹</label>
      <div class="field-row">
        <input
          id="folder-input"
          v-model="folder"
          type="text"
          placeholder="粘贴照片文件夹绝对路径"
          spellcheck="false"
          required
        >
        <button
          v-if="canPickFolder"
          class="btn-ghost"
          type="button"
          :disabled="isPickingFolder || isStarting"
          @click="handlePickFolder"
        >
          {{ isPickingFolder ? "选择中" : "选择文件夹" }}
        </button>
        <button
          class="btn-primary"
          type="submit"
          :disabled="isStarting || isCheckingDependencies || isDownloadingDependencies || !tycoonReady"
        >
          {{ startButtonText }}
        </button>
      </div>

      <FolderSnapshot :snapshot="snapshot" />

      <section class="dependency-panel">
        <div class="dependency-head">
          <div>
            <div class="option-label">运行资源</div>
            <h2>{{ dependencyPanelTitle }}</h2>
          </div>
          <button
            class="btn-primary"
            type="button"
            :disabled="isCheckingDependencies || isDownloadingDependencies"
            @click="handleDependencyCheckOnly"
          >
            {{ isCheckingDependencies ? "检查中" : "检查当前模式" }}
          </button>
        </div>

        <label class="dependency-dir">
          <span>模型 / 资源下载位置</span>
          <input
            v-model="dependencyDownloadDir"
            type="text"
            placeholder="留空则使用默认资源目录"
            spellcheck="false"
          >
        </label>

        <div v-if="dependencyReport" class="dependency-summary">
          <div>
            <span>缺失项</span>
            <strong>{{ dependencyMissingCount }}</strong>
          </div>
          <div>
            <span>可下载</span>
            <strong>{{ dependencyDownloadableCount }}</strong>
          </div>
          <div>
            <span>需手动处理</span>
            <strong>{{ dependencyManualCount }}</strong>
          </div>
        </div>

        <ul v-if="dependencyReport?.missing?.length" class="dependency-list">
          <li v-for="item in dependencyReport.missing" :key="item.id">
            <div>
              <strong>{{ item.label }}</strong>
              <span>{{ item.detail }}</span>
              <small v-if="item.hint">{{ item.hint }}</small>
            </div>
            <em :class="{ 'is-downloadable': item.downloadable }">
              {{ item.downloadable ? "可自动下载" : "需手动处理" }}
            </em>
          </li>
        </ul>

        <p v-else-if="dependencyReport?.ok" class="start-note">
          当前模式运行资源已就绪。
        </p>

        <p v-if="dependencyReport?.manual_required" class="dependency-blocker">
          {{ pendingStartPayload ? "存在无法自动下载的依赖，需要处理后再点击“检查并继续”。" : "存在无法自动下载的依赖，需要处理后重新检查。" }}
        </p>
        <p v-if="dependencyReport" class="dependency-hint">
          {{ dependencyPrimaryActionHint }}
        </p>

        <div v-if="isDownloadingDependencies || dependencyDownloadStatus" class="dependency-progress">
          <span :class="`is-${dependencyDownloadStatus?.status || 'running'}`"></span>
          <div>
            <strong>{{ downloadStatusText }}</strong>
            <small>{{ dependencyDownloadStatus?.message || dependencyMessage || "正在处理下载任务" }}</small>
          </div>
        </div>

        <div class="dependency-actions">
          <button
            v-if="canPickFolder"
            class="btn-ghost"
            type="button"
            :disabled="isDownloadingDependencies"
            @click="handlePickDependencyFolder"
          >
            指定下载位置
          </button>
          <button
            v-if="pendingStartPayload"
            class="btn-ghost"
            type="button"
            :disabled="isCheckingDependencies || isDownloadingDependencies"
            @click="handleDependencyRecheck"
          >
            {{ isCheckingDependencies ? "检查中" : "检查并继续" }}
          </button>
          <button
            class="btn-primary"
            type="button"
            :disabled="!canDownloadDependencies || isDownloadingDependencies"
            @click="handleDependencyDownload"
          >
            {{ downloadButtonText }}
          </button>
          <button
            class="btn-ghost"
            type="button"
            :disabled="!dependencyReportText"
            @click="copyDependencyReport"
          >
            {{ dependencyCopied ? "已复制" : "复制检查结果" }}
          </button>
        </div>

        <p v-if="dependencyMessage" class="start-note">{{ dependencyMessage }}</p>
        <p v-if="dependencyError" class="form-error">{{ dependencyError }}</p>
      </section>

      <details class="advanced">
        <summary>更多选项</summary>
        <div class="advanced-body">
          <section class="option-section">
            <div class="option-label">归档方式</div>
            <label class="radio-row">
              <input v-model="mode" type="radio" value="move">
              <span><strong>移动</strong> · 原片直接归入 winners/ losers/</span>
            </label>
            <label class="radio-row">
              <input v-model="mode" type="radio" value="copy">
              <span><strong>复制</strong> · 原片保留，winners/ 为副本</span>
            </label>
          </section>

          <section class="option-section">
            <label class="check-row">
              <input v-model="prescreenEnabled" type="checkbox">
              <span>智能初筛 · 先自动淘汰明显的失焦 / 闭眼 / 过曝</span>
            </label>
            <label class="check-row" :class="{ 'is-disabled': faceAwareDisabled }">
              <input v-model="faceAware" type="checkbox" :disabled="faceAwareDisabled">
              <span>人脸感知 · 极速模式下自动关闭</span>
            </label>
          </section>

          <section class="option-section" :class="{ 'is-disabled': !prescreenEnabled }">
            <div class="option-label">初筛力度</div>
            <label class="radio-row">
              <input
                v-model="prescreenStrength"
                type="radio"
                value="standard"
                :disabled="!prescreenEnabled"
              >
              <span><strong>标准</strong> · 识别主体糊/严重歪斜/曝光问题</span>
            </label>
            <label class="radio-row">
              <input
                v-model="prescreenStrength"
                type="radio"
                value="advanced"
                :disabled="!prescreenEnabled"
              >
              <span><strong>进阶</strong> · 推荐档位，阈值更严</span>
            </label>
          </section>

          <section class="option-section sliders">
            <label>
              <span>同场景宽容度</span>
              <input v-model="thresholdNear" type="range" min="4" max="16" step="1">
              <output>{{ thresholdNear }}</output>
            </label>
            <label>
              <span>跨场景严格度</span>
              <input v-model="thresholdFar" type="range" min="3" max="12" step="1">
              <output>{{ thresholdFar }}</output>
            </label>
            <label>
              <span>同场景时间窗（分钟）</span>
              <input v-model="nearMinutes" type="range" min="1" max="30" step="1">
              <output>{{ nearMinutes }}</output>
            </label>
          </section>
        </div>
      </details>

      <p class="form-error">{{ startError }}</p>
      <p v-if="lastStartPayload" class="start-note">
        已向 Flask API 发起任务，正在进入 Vue 处理页。
      </p>
    </form>
  </main>
</template>

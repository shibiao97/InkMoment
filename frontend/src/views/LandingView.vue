<script setup>
import { computed, ref, watch } from "vue";
import { isTauriRuntime, pickDesktopFolder } from "../api/runtime";
import EngineSwitch from "../components/EngineSwitch.vue";
import FolderSnapshot from "../components/FolderSnapshot.vue";
import ThemePicker from "../components/ThemePicker.vue";
import StatusBadge from "../components/StatusBadge.vue";
import WorkflowSidebar from "../components/WorkflowSidebar.vue";
import LandingAdvancedOptions from "../components/landing/LandingAdvancedOptions.vue";
import LandingDependencyPanel from "../components/landing/LandingDependencyPanel.vue";
import LandingFlowPanel from "../components/landing/LandingFlowPanel.vue";
import LandingLlmPanel from "../components/landing/LandingLlmPanel.vue";
import { useBranding } from "../composables/useBranding";
import { useLandingDependencyFlow } from "../composables/useLandingDependencyFlow";
import { useFolderPeek } from "../composables/useFolderPeek";
import {
  buildLandingStartPayload,
  landingStartPayloadSignature,
} from "../composables/useLandingStartPayload";
import { useLlmConfig } from "../composables/useLlmConfig";
import { useTheme } from "../composables/useTheme";

const emit = defineEmits(["job-started"]);

const ENGINE_META = {
  fast: {
    label: "轻量快选",
    resource: "基础运行包",
  },
  expert: {
    label: "质感优选",
    resource: "本地评估资源",
  },
  tycoon: {
    label: "云端精评",
    resource: "云端模型服务",
  },
};
const { branding, loadingBranding } = useBranding();
const { themes, selectedTheme } = useTheme();

const folder = ref("");
const engine = ref("fast");
const mode = ref("copy");
const prescreenEnabled = ref(true);
const prescreenStrength = ref("advanced");
const faceAware = ref(true);
const thresholdNear = ref(10);
const thresholdFar = ref(6);
const nearMinutes = ref(5);
const isPickingFolder = ref(false);
const showLlmConfig = ref(false);
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
const {
  startError,
  isStarting,
  isCheckingDependencies,
  isDownloadingDependencies,
  lastStartPayload,
  dependencyReport,
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
  dependencyManualCommands,
  downloadStatusText,
  downloadButtonText,
  resourceState,
  startButtonText,
  handleDependencyCheckOnly,
  handleDependencyDownload,
  handleDependencyRecheck,
  handleStart,
  copyDependencyReport,
  clearDependencyState,
  clearStalePendingStartPayload,
} = useLandingDependencyFlow({
  buildStartPayload,
  validateStartInputs,
  selectedEngineLabel,
  onJobStarted: (payload) => emit("job-started", payload),
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
const startPayloadSignature = computed(() => landingStartPayloadSignature(buildStartPayload()));

watch(engine, () => {
  clearDependencyState();
});

watch(startPayloadSignature, clearStalePendingStartPayload);

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
  return buildLandingStartPayload({
    folder: folder.value,
    mode: mode.value,
    engine: engine.value,
    thresholdNear: thresholdNear.value,
    thresholdFar: thresholdFar.value,
    nearMinutes: nearMinutes.value,
    prescreenEnabled: prescreenEnabled.value,
    prescreenStrength: prescreenStrength.value,
    faceAware: faceAware.value,
    selectedLlmModel: selectedLlmModel.value,
  });
}
</script>

<template>
  <main class="app-shell studio-shell landing-workbench">
    <StatusBadge :label="statusText" :state="statusState" />

    <WorkflowSidebar
      active-step="landing"
      :summary-value="selectedEngineLabel"
      :summary-detail="folderSummary"
    />

    <form class="studio-main start-form" @submit.prevent="handleStart">
      <header class="topbar studio-topbar">
        <div>
          <p class="eyebrow">{{ loadingBranding ? "加载中" : branding.hero_eyebrow }}</p>
          <h1>{{ branding.hero_title }}</h1>
          <p class="subtitle">{{ branding.hero_subtitle }}</p>
        </div>

        <div class="top-actions">
          <ThemePicker v-model="selectedTheme" :themes="themes" />
        </div>
      </header>

      <section class="studio-panel import-panel">
        <div class="panel-title">
          <div>
            <p class="eyebrow">导入照片</p>
            <h2>选择这次要处理的照片文件夹</h2>
          </div>
          <span>{{ selectedEngineMeta.resource }}</span>
        </div>

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
      </section>

      <section class="studio-panel analysis-mode-panel">
        <div class="panel-title">
          <div>
            <p class="eyebrow">筛选方案</p>
            <h2>{{ selectedEngineLabel }}</h2>
          </div>
          <span>{{ modelSummary }}</span>
        </div>

        <EngineSwitch
          v-model="engine"
          :disabled="isStarting || isCheckingDependencies || isDownloadingDependencies"
        />

        <LandingLlmPanel
          v-if="llmPanelVisible"
          v-model:base-url="llmBaseUrlInput"
          v-model:api-key="llmKeyInput"
          v-model:selected-model="selectedLlmModel"
          :status="llmStatus"
          :models="llmModels"
          :concurrency="llmConcurrency"
          :diagnostics="llmDiagnostics"
          :loading="llmLoading"
          :checking-models="checkingModels"
          :saving="llmSaving"
          :configured="llmConfigured"
          :message="llmMessage"
          :error="llmError"
          @refresh="refreshLlm({ forceModels: true })"
          @save="saveLlmConfig"
          @clear="clearLlmConfig"
          @refresh-models="refreshModels"
        />
      </section>
    </form>

    <aside class="studio-inspector">
      <LandingFlowPanel :items="flowItems" />
      <LandingAdvancedOptions
        v-model:mode="mode"
        v-model:prescreen-enabled="prescreenEnabled"
        v-model:face-aware="faceAware"
        v-model:prescreen-strength="prescreenStrength"
        v-model:threshold-near="thresholdNear"
        v-model:threshold-far="thresholdFar"
        v-model:near-minutes="nearMinutes"
        :face-aware-disabled="faceAwareDisabled"
      />

      <LandingDependencyPanel
        :is-checking="isCheckingDependencies"
        :is-downloading="isDownloadingDependencies"
        :report="dependencyReport"
        :title="dependencyPanelTitle"
        :missing-count="dependencyMissingCount"
        :downloadable-count="dependencyDownloadableCount"
        :manual-count="dependencyManualCount"
        :has-pending-start="Boolean(pendingStartPayload)"
        :action-hint="dependencyPrimaryActionHint"
        :download-status="dependencyDownloadStatus"
        :message="dependencyMessage"
        :error="dependencyError"
        :download-status-text="downloadStatusText"
        :can-download="canDownloadDependencies"
        :download-button-text="downloadButtonText"
        :report-text="dependencyReportText"
        :manual-commands="dependencyManualCommands"
        :copied="dependencyCopied"
        @check="handleDependencyCheckOnly"
        @recheck="handleDependencyRecheck"
        @download="handleDependencyDownload"
        @copy="copyDependencyReport"
      />

      <p class="form-error">{{ startError }}</p>
      <p v-if="lastStartPayload" class="start-note">
        已向 Flask API 发起任务，正在进入 Vue 处理页。
      </p>
    </aside>
  </main>
</template>

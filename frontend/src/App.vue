<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { AUTH_INVALID_EVENT } from "./api/http";
import { getJob, getStatus } from "./api/inkmoment";
import { initDesktopBackend, isTauriRuntime } from "./api/runtime";
import AppViewHost from "./components/AppViewHost.vue";
import DebugLogOverlay from "./components/DebugLogOverlay.vue";
import AuthView from "./views/AuthView.vue";
import { useAuthSession } from "./composables/useAuthSession";
import { useDebugLogs } from "./composables/useDebugLogs";
import { useDesktopBackendMonitor } from "./composables/useDesktopBackendMonitor";
import { useFlowState } from "./composables/useFlowState";
import { resolveNextStep } from "./composables/useNextStep";
import { useSessionReset } from "./composables/useSessionReset";

const ACTIVE_JOB_STATUSES = new Set(["pending", "scanning", "hashing", "grouping", "checking"]);

const booting = ref(true);
const bootMessage = ref("正在启动本地服务...");
const bootError = ref("");
const { resetting, resetError, resetCurrentSession } = useSessionReset();
const auth = useAuthSession();
const { currentView, startedPayload, enterProcessing, clearStartedPayload, resumeStep, enterPreview, enterArena, enterDone, enterHome } = useFlowState();
const { desktopBackendError, startDesktopBackendMonitor, stopDesktopBackendMonitor } = useDesktopBackendMonitor();

const bannerText = computed(() => {
  if (booting.value) return bootMessage.value || "正在启动";
  if (resetting.value) return "正在回首页...";
  return resetError.value || desktopBackendError.value || bootError.value || auth.error.value;
});

const bannerError = computed(() => Boolean(
  resetError.value || desktopBackendError.value || bootError.value || auth.error.value,
));

const { debugOpen, debugLoading, debugError, debugLogText, debugCopied, openDebugLogs, refreshDebugLogs, copyDebugLogs } = useDebugLogs({
  currentView,
  booting,
  bannerText,
  auth,
  desktopBackendError,
});

async function backHome() {
  if (resetting.value) return;
  if (currentView.value !== "landing") {
    const ok = await resetCurrentSession();
    if (!ok) console.warn("reset_session failed; returning to landing anyway");
  }
  clearStartedPayload();
  enterHome();
}

async function resumeFromBackend() {
  booting.value = true;
  bootMessage.value = "正在启动本地服务...";
  bootError.value = "";
  try {
    const backend = await initDesktopBackend({
      onStatus: (status) => {
        if (status?.starting) bootMessage.value = "正在启动本地服务...";
      },
    });
    if (backend) startDesktopBackendMonitor();
    bootMessage.value = "正在检查登录状态...";
    const authStatus = await auth.refresh(true);
    if (!authStatus?.authorized) {
      enterHome();
      return;
    }
    bootMessage.value = "正在恢复上次进度...";
    await restoreAuthorizedWorkflow();
  } catch (err) {
    bootError.value = err.message || "恢复进度失败";
    enterHome();
  } finally {
    booting.value = false;
  }
}

async function restoreAuthorizedWorkflow() {
  auth.startPolling(handleAuthInvalid);
  const job = await getJob();
  if (ACTIVE_JOB_STATUSES.has(job?.status)) {
    enterProcessing({ folder: job.folder, mode: job.mode, engine: job.engine, dry_run: job.dry_run });
    return;
  }
  const status = await getStatus();
  resumeStep(resolveNextStep(status).kind);
}

async function handleAuthAuthorized() {
  booting.value = true;
  bootError.value = "";
  try {
    await restoreAuthorizedWorkflow();
  } catch (err) {
    bootError.value = err.message || "授权后恢复进度失败";
    enterHome();
  } finally {
    booting.value = false;
  }
}

function handleAuthInvalid(nextStatus = null) {
  if (nextStatus && typeof nextStatus === "object") {
    auth.applyStatus(nextStatus);
  } else {
    auth.markInvalid({ reason: "unauthenticated" });
  }
  auth.stopPolling();
  resetError.value = "";
  clearStartedPayload();
  enterHome();
}

function handleAuthInvalidEvent(event) {
  const code = event?.detail?.code || "unauthenticated";
  handleAuthInvalid(event?.detail?.auth || {
    reason: code,
    license: { authorized: false, reason: code },
  });
}

onMounted(() => {
  window.addEventListener(AUTH_INVALID_EVENT, handleAuthInvalidEvent);
  resumeFromBackend();
});

onUnmounted(() => {
  window.removeEventListener(AUTH_INVALID_EVENT, handleAuthInvalidEvent);
  auth.stopPolling();
  stopDesktopBackendMonitor();
});
</script>

<template>
  <AuthView
    v-if="!booting && !auth.authorized.value"
    :auth="auth"
    @authorized="handleAuthAuthorized"
  />
  <AppViewHost
    v-else-if="!booting"
    :current-view="currentView"
    :started-payload="startedPayload"
    :returning-home="resetting"
    @job-started="enterProcessing"
    @back-home="backHome"
    @continue-step="resumeStep"
    @enter-preview="enterPreview"
    @enter-arena="enterArena"
    @enter-done="enterDone"
  />
  <main v-else class="app-shell app-boot-shell">
    <div class="app-boot-panel">
      <p class="eyebrow">InkMoment</p>
      <h1>{{ bootMessage }}</h1>
    </div>
  </main>

  <div v-if="bannerText" class="session-reset-banner" :class="{ error: bannerError }">
    {{ bannerText }}
  </div>

  <DebugLogOverlay
    v-if="isTauriRuntime()"
    :open="debugOpen"
    :loading="debugLoading"
    :error="debugError"
    :log-text="debugLogText"
    :copied="debugCopied"
    @open="openDebugLogs"
    @close="debugOpen = false"
    @refresh="refreshDebugLogs"
    @copy="copyDebugLogs"
  />
</template>

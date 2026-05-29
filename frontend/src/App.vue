<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import ArenaView from "./views/ArenaView.vue";
import AuthView from "./views/AuthView.vue";
import DoneView from "./views/DoneView.vue";
import LandingView from "./views/LandingView.vue";
import PrescreenView from "./views/PrescreenView.vue";
import PreviewView from "./views/PreviewView.vue";
import ProcessingView from "./views/ProcessingView.vue";
import { AUTH_INVALID_EVENT } from "./api/http";
import { getHealth, getJob, getStatus } from "./api/inkmoment";
import {
  getDesktopBackendLogs,
  getDesktopBackendStatus,
  initDesktopBackend,
  isTauriRuntime,
} from "./api/runtime";
import { useAuthSession } from "./composables/useAuthSession";
import { resolveNextStep } from "./composables/useNextStep";
import { useSessionReset } from "./composables/useSessionReset";

const ACTIVE_JOB_STATUSES = new Set(["pending", "scanning", "hashing", "grouping", "checking"]);
const BACKEND_STATUS_POLL_MS = 3000;
const BACKEND_STATUS_FAILURE_LIMIT = 3;

const currentView = ref("landing");
const startedPayload = ref(null);
const booting = ref(true);
const bootMessage = ref("正在启动本地服务...");
const bootError = ref("");
const desktopBackendError = ref("");
const debugOpen = ref(false);
const debugLoading = ref(false);
const debugError = ref("");
const debugPayload = ref(null);
const debugBackendStatus = ref(null);
const debugHealth = ref(null);
const debugCopied = ref(false);
const { resetting, resetError, resetCurrentSession } = useSessionReset();
const auth = useAuthSession();
let desktopBackendTimer = null;
let desktopBackendFailureCount = 0;
let desktopBackendStatusInFlight = false;

const bannerText = computed(() => {
  if (booting.value) return bootMessage.value || "正在启动";
  if (resetting.value) return "正在回首页...";
  return resetError.value || desktopBackendError.value || bootError.value || auth.error.value;
});

const bannerError = computed(() => Boolean(
  resetError.value || desktopBackendError.value || bootError.value || auth.error.value,
));

const debugLogText = computed(() => {
  const payload = debugPayload.value || {};
  const lines = Array.isArray(payload.lines) ? payload.lines : [];
  const authStatus = auth.status.value || {};
  const backendStatus = debugBackendStatus.value || {};
  const health = debugHealth.value || {};
  const header = [
    `frontend_view=${currentView.value}`,
    `frontend_booting=${booting.value}`,
    `frontend_banner=${bannerText.value || ""}`,
    `auth_configured=${authStatus.configured ?? ""}`,
    `auth_authenticated=${authStatus.authenticated ?? ""}`,
    `auth_authorized=${authStatus.authorized ?? ""}`,
    `auth_reason=${authStatus.reason || auth.license.value?.reason || ""}`,
    `auth_last_error=${auth.lastErrorCode.value || ""}`,
    `desktop_backend_ready=${backendStatus.ready ?? ""}`,
    `desktop_backend_running=${backendStatus.running ?? ""}`,
    `desktop_backend_starting=${backendStatus.starting ?? ""}`,
    `desktop_backend_error=${backendStatus.error || desktopBackendError.value || ""}`,
    `sidecar_health_ok=${health.ok ?? ""}`,
    `sidecar_active_job=${health.active_job || ""}`,
    `sidecar_active_session=${health.active_session || ""}`,
    `backend_url=${payload.backend?.url || ""}`,
    `health_url=${payload.backend?.health_url || ""}`,
    `pid=${payload.backend?.pid || ""}`,
    `startup_error=${payload.startup_error || ""}`,
  ];
  return [...header, "", ...lines].join("\n").trim();
});

function enterProcessing(payload) {
  startedPayload.value = payload;
  currentView.value = "processing";
}

async function backHome() {
  if (resetting.value) return;
  if (currentView.value !== "landing") {
    const ok = await resetCurrentSession();
    if (!ok) {
      console.warn("reset_session failed; returning to landing anyway");
    }
  }
  startedPayload.value = null;
  currentView.value = "landing";
}

function continueFromProcessing(kind) {
  if (kind === "prescreen" || kind === "confirm-prescreen") {
    currentView.value = "prescreen";
    return;
  }
  if (kind === "preview") {
    currentView.value = "preview";
    return;
  }
  if (kind === "arena") {
    currentView.value = "arena";
    return;
  }
  if (kind === "done") {
    currentView.value = "done";
  }
}

function applyResumeStep(kind) {
  if (kind === "prescreen" || kind === "confirm-prescreen") {
    currentView.value = "prescreen";
    return;
  }
  if (kind === "preview") {
    currentView.value = "preview";
    return;
  }
  if (kind === "arena") {
    currentView.value = "arena";
    return;
  }
  if (kind === "done") {
    currentView.value = "done";
    return;
  }
  currentView.value = "landing";
}

async function resumeFromBackend() {
  booting.value = true;
  bootMessage.value = "正在启动本地服务...";
  bootError.value = "";
  try {
    const backend = await initDesktopBackend({
      onStatus(status) {
        if (status?.starting) {
          bootMessage.value = "正在启动本地服务...";
        }
      },
    });
    if (backend) startDesktopBackendMonitor();
    bootMessage.value = "正在检查登录状态...";
    const authStatus = await auth.refresh(true);
    if (!authStatus?.authorized) {
      currentView.value = "landing";
      return;
    }
    bootMessage.value = "正在恢复上次进度...";
    await restoreAuthorizedWorkflow();
  } catch (err) {
    bootError.value = err.message || "恢复进度失败";
    currentView.value = "landing";
  } finally {
    booting.value = false;
  }
}

async function restoreAuthorizedWorkflow() {
  auth.startPolling(handleAuthInvalid);
  const job = await getJob();
  if (ACTIVE_JOB_STATUSES.has(job?.status)) {
    startedPayload.value = {
      folder: job.folder,
      mode: job.mode,
      engine: job.engine,
      dry_run: job.dry_run,
    };
    currentView.value = "processing";
    return;
  }

  const status = await getStatus();
  applyResumeStep(resolveNextStep(status).kind);
}

async function handleAuthAuthorized() {
  booting.value = true;
  bootError.value = "";
  try {
    await restoreAuthorizedWorkflow();
  } catch (err) {
    bootError.value = err.message || "授权后恢复进度失败";
    currentView.value = "landing";
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
  startedPayload.value = null;
  currentView.value = "landing";
}

function handleAuthInvalidEvent(event) {
  const code = event?.detail?.code || "unauthenticated";
  handleAuthInvalid(event?.detail?.auth || {
    reason: code,
    license: { authorized: false, reason: code },
  });
}

function startDesktopBackendMonitor() {
  if (!isTauriRuntime() || desktopBackendTimer) return;
  desktopBackendTimer = window.setInterval(async () => {
    if (desktopBackendStatusInFlight) return;
    desktopBackendStatusInFlight = true;
    try {
      const status = await getDesktopBackendStatus();
      if (!status || status.ready) {
        desktopBackendFailureCount = 0;
        desktopBackendError.value = "";
        return;
      }
      desktopBackendFailureCount += 1;
      if (status.running && isTransientBackendHealthError(status.error) && desktopBackendFailureCount < BACKEND_STATUS_FAILURE_LIMIT) {
        return;
      }
      desktopBackendError.value = status.error || "桌面后端不可用";
    } catch (err) {
      desktopBackendFailureCount += 1;
      if (isTransientBackendHealthError(err.message) && desktopBackendFailureCount < BACKEND_STATUS_FAILURE_LIMIT) {
        return;
      }
      desktopBackendError.value = err.message || "桌面后端状态检查失败";
    } finally {
      desktopBackendStatusInFlight = false;
    }
  }, BACKEND_STATUS_POLL_MS);
}

function isTransientBackendHealthError(message = "") {
  return /读取健康检查响应超时|Resource temporarily unavailable|os error 35|timed out|WouldBlock/i.test(
    String(message || ""),
  );
}

async function openDebugLogs() {
  debugOpen.value = true;
  await refreshDebugLogs();
}

async function refreshDebugLogs() {
  debugLoading.value = true;
  debugError.value = "";
  debugCopied.value = false;
  try {
    const [logsResult, backendStatusResult, healthResult] = await Promise.allSettled([
      getDesktopBackendLogs(),
      getDesktopBackendStatus(),
      getHealth(),
    ]);
    if (logsResult.status === "fulfilled") {
      debugPayload.value = logsResult.value;
    } else {
      debugPayload.value = {
        lines: [`[frontend] 读取后端日志失败：${logsResult.reason?.message || logsResult.reason}`],
        startup_error: "",
        backend: null,
      };
    }
    debugBackendStatus.value = backendStatusResult.status === "fulfilled"
      ? backendStatusResult.value
      : { error: backendStatusResult.reason?.message || "读取桌面后端状态失败" };
    debugHealth.value = healthResult.status === "fulfilled"
      ? healthResult.value
      : { ok: false, error: healthResult.reason?.message || "读取 sidecar health 失败" };
  } catch (err) {
    debugError.value = err.message || "读取 Debug 日志失败";
  } finally {
    debugLoading.value = false;
  }
}

async function copyDebugLogs() {
  debugCopied.value = false;
  try {
    await navigator.clipboard.writeText(debugLogText.value || "");
    debugCopied.value = true;
  } catch (err) {
    debugError.value = err.message || "复制日志失败";
  }
}

function enterPreview() {
  currentView.value = "preview";
}

function enterArena() {
  currentView.value = "arena";
}

function enterDone() {
  currentView.value = "done";
}

onMounted(() => {
  window.addEventListener(AUTH_INVALID_EVENT, handleAuthInvalidEvent);
  resumeFromBackend();
});

onUnmounted(() => {
  window.removeEventListener(AUTH_INVALID_EVENT, handleAuthInvalidEvent);
  auth.stopPolling();
  if (desktopBackendTimer) {
    window.clearInterval(desktopBackendTimer);
    desktopBackendTimer = null;
  }
});
</script>

<template>
  <AuthView
    v-if="!booting && !auth.authorized.value"
    :auth="auth"
    @authorized="handleAuthAuthorized"
  />
  <LandingView
    v-else-if="!booting && currentView === 'landing'"
    @job-started="enterProcessing"
  />
  <ProcessingView
    v-else-if="!booting && currentView === 'processing'"
    :started-payload="startedPayload"
    :returning-home="resetting"
    @back-home="backHome"
    @continue="continueFromProcessing"
  />
  <PrescreenView
    v-else-if="!booting && currentView === 'prescreen'"
    :returning-home="resetting"
    @back-home="backHome"
    @continue-preview="enterPreview"
  />
  <PreviewView
    v-else-if="!booting && currentView === 'preview'"
    :returning-home="resetting"
    @back-home="backHome"
    @continue-arena="enterArena"
  />
  <ArenaView
    v-else-if="!booting && currentView === 'arena'"
    :returning-home="resetting"
    @back-home="backHome"
    @done="enterDone"
  />
  <DoneView
    v-else-if="!booting"
    :returning-home="resetting"
    @back-home="backHome"
    @continue-arena="enterArena"
    @job-started="enterProcessing"
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

  <button
    v-if="isTauriRuntime()"
    class="debug-log-button"
    type="button"
    title="查看后台运行日志"
    @click="openDebugLogs"
  >
    日志
  </button>

  <div v-if="debugOpen" class="debug-log-overlay" role="dialog" aria-modal="true">
    <section class="debug-log-panel">
      <header class="debug-log-head">
        <div>
          <p class="eyebrow">Backend</p>
          <h2>运行日志</h2>
        </div>
        <button class="btn-ghost" type="button" @click="debugOpen = false">关闭</button>
      </header>
      <div class="debug-log-actions">
        <button class="btn-ghost" type="button" :disabled="debugLoading" @click="refreshDebugLogs">
          {{ debugLoading ? "刷新中..." : "刷新" }}
        </button>
        <button class="btn-primary" type="button" :disabled="!debugLogText" @click="copyDebugLogs">
          {{ debugCopied ? "已复制" : "复制日志" }}
        </button>
      </div>
      <p v-if="debugError" class="debug-log-error">{{ debugError }}</p>
      <pre class="debug-log-output">{{ debugLogText || "暂无日志" }}</pre>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import ArenaView from "./views/ArenaView.vue";
import DoneView from "./views/DoneView.vue";
import LandingView from "./views/LandingView.vue";
import PrescreenView from "./views/PrescreenView.vue";
import PreviewView from "./views/PreviewView.vue";
import ProcessingView from "./views/ProcessingView.vue";
import { getJob, getStatus } from "./api/inkmoment";
import { getDesktopBackendStatus, initDesktopBackend, isTauriRuntime } from "./api/runtime";
import { resolveNextStep } from "./composables/useNextStep";
import { useSessionReset } from "./composables/useSessionReset";

const ACTIVE_JOB_STATUSES = new Set(["pending", "scanning", "hashing", "grouping", "checking"]);
const BACKEND_STATUS_POLL_MS = 3000;

const currentView = ref("landing");
const startedPayload = ref(null);
const booting = ref(true);
const bootError = ref("");
const desktopBackendError = ref("");
const { resetting, resetError, resetCurrentSession } = useSessionReset();
let desktopBackendTimer = null;

const bannerText = computed(() => {
  if (booting.value) return "正在恢复上次进度...";
  if (resetting.value) return "正在回首页...";
  return resetError.value || desktopBackendError.value || bootError.value;
});

const bannerError = computed(() => Boolean(resetError.value || desktopBackendError.value || bootError.value));

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
  bootError.value = "";
  try {
    const backend = await initDesktopBackend();
    if (backend) startDesktopBackendMonitor();
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
  } catch (err) {
    bootError.value = err.message || "恢复进度失败";
    currentView.value = "landing";
  } finally {
    booting.value = false;
  }
}

function startDesktopBackendMonitor() {
  if (!isTauriRuntime() || desktopBackendTimer) return;
  desktopBackendTimer = window.setInterval(async () => {
    try {
      const status = await getDesktopBackendStatus();
      if (!status || status.ready) {
        desktopBackendError.value = "";
        return;
      }
      desktopBackendError.value = status.error || "桌面后端不可用";
    } catch (err) {
      desktopBackendError.value = err.message || "桌面后端状态检查失败";
    }
  }, BACKEND_STATUS_POLL_MS);
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

onMounted(resumeFromBackend);

onUnmounted(() => {
  if (desktopBackendTimer) {
    window.clearInterval(desktopBackendTimer);
    desktopBackendTimer = null;
  }
});
</script>

<template>
  <LandingView
    v-if="!booting && currentView === 'landing'"
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
  />
  <main v-else class="app-shell app-boot-shell">
    <div class="app-boot-panel">
      <p class="eyebrow">InkMoment</p>
      <h1>正在恢复进度</h1>
    </div>
  </main>

  <div v-if="bannerText" class="session-reset-banner" :class="{ error: bannerError }">
    {{ bannerText }}
  </div>
</template>

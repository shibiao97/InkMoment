<script setup>
import { computed, onMounted, ref } from "vue";
import ArenaView from "./views/ArenaView.vue";
import DoneView from "./views/DoneView.vue";
import LandingView from "./views/LandingView.vue";
import PrescreenView from "./views/PrescreenView.vue";
import PreviewView from "./views/PreviewView.vue";
import ProcessingView from "./views/ProcessingView.vue";
import { getJob, getStatus } from "./api/inkmoment";
import { initDesktopBackend } from "./api/runtime";
import { resolveNextStep } from "./composables/useNextStep";
import { useSessionReset } from "./composables/useSessionReset";

const ACTIVE_JOB_STATUSES = new Set(["pending", "scanning", "hashing", "grouping", "checking"]);

const currentView = ref("landing");
const startedPayload = ref(null);
const booting = ref(true);
const bootError = ref("");
const { resetting, resetError, resetCurrentSession } = useSessionReset();

const bannerText = computed(() => {
  if (booting.value) return "正在恢复上次进度...";
  if (resetting.value) return "正在回首页...";
  return resetError.value || bootError.value;
});

const bannerError = computed(() => Boolean(resetError.value || bootError.value));

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
    await initDesktopBackend();
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
</script>

<template>
  <LandingView
    v-if="!booting && currentView === 'landing'"
    @job-started="enterProcessing"
  />
  <ProcessingView
    v-else-if="!booting && currentView === 'processing'"
    :started-payload="startedPayload"
    @back-home="backHome"
    @continue="continueFromProcessing"
  />
  <PrescreenView
    v-else-if="!booting && currentView === 'prescreen'"
    @back-home="backHome"
    @continue-preview="enterPreview"
  />
  <PreviewView
    v-else-if="!booting && currentView === 'preview'"
    @back-home="backHome"
    @continue-arena="enterArena"
  />
  <ArenaView
    v-else-if="!booting && currentView === 'arena'"
    @back-home="backHome"
    @done="enterDone"
  />
  <DoneView
    v-else-if="!booting"
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

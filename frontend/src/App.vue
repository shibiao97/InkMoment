<script setup>
import { ref } from "vue";
import ArenaView from "./views/ArenaView.vue";
import DoneView from "./views/DoneView.vue";
import LandingView from "./views/LandingView.vue";
import PrescreenView from "./views/PrescreenView.vue";
import PreviewView from "./views/PreviewView.vue";
import ProcessingView from "./views/ProcessingView.vue";
import { useSessionReset } from "./composables/useSessionReset";

const currentView = ref("landing");
const startedPayload = ref(null);
const { resetting, resetError, resetCurrentSession } = useSessionReset();

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

function enterPreview() {
  currentView.value = "preview";
}

function enterArena() {
  currentView.value = "arena";
}

function enterDone() {
  currentView.value = "done";
}
</script>

<template>
  <LandingView
    v-if="currentView === 'landing'"
    @job-started="enterProcessing"
  />
  <ProcessingView
    v-else-if="currentView === 'processing'"
    :started-payload="startedPayload"
    @back-home="backHome"
    @continue="continueFromProcessing"
  />
  <PrescreenView
    v-else-if="currentView === 'prescreen'"
    @back-home="backHome"
    @continue-preview="enterPreview"
  />
  <PreviewView
    v-else-if="currentView === 'preview'"
    @back-home="backHome"
    @continue-arena="enterArena"
  />
  <ArenaView
    v-else-if="currentView === 'arena'"
    @back-home="backHome"
    @done="enterDone"
  />
  <DoneView
    v-else
    @back-home="backHome"
    @continue-arena="enterArena"
  />

  <div v-if="resetting || resetError" class="session-reset-banner" :class="{ error: resetError }">
    {{ resetting ? "正在回首页..." : resetError }}
  </div>
</template>

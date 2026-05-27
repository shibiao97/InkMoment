<script setup>
import { ref } from "vue";
import ArenaView from "./views/ArenaView.vue";
import LandingView from "./views/LandingView.vue";
import PrescreenView from "./views/PrescreenView.vue";
import PreviewView from "./views/PreviewView.vue";
import ProcessingView from "./views/ProcessingView.vue";

const currentView = ref("landing");
const startedPayload = ref(null);

function enterProcessing(payload) {
  startedPayload.value = payload;
  currentView.value = "processing";
}

function backHome() {
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
  }
}

function enterPreview() {
  currentView.value = "preview";
}

function enterArena() {
  currentView.value = "arena";
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
    v-else
    @back-home="backHome"
  />
</template>

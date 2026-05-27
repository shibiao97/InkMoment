<script setup>
import { ref } from "vue";
import LandingView from "./views/LandingView.vue";
import PrescreenView from "./views/PrescreenView.vue";
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
  }
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
    v-else
    @back-home="backHome"
  />
</template>

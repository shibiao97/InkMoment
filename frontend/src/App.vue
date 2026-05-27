<script setup>
import { ref } from "vue";
import LandingView from "./views/LandingView.vue";
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
</script>

<template>
  <LandingView
    v-if="currentView === 'landing'"
    @job-started="enterProcessing"
  />
  <ProcessingView
    v-else
    :started-payload="startedPayload"
    @back-home="backHome"
  />
</template>

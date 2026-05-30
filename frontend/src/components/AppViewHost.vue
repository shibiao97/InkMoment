<script setup>
import ArenaView from "../views/ArenaView.vue";
import DoneView from "../views/DoneView.vue";
import LandingView from "../views/LandingView.vue";
import PrescreenView from "../views/PrescreenView.vue";
import PreviewView from "../views/PreviewView.vue";
import ProcessingView from "../views/ProcessingView.vue";

defineProps({
  currentView: {
    type: String,
    required: true,
  },
  startedPayload: {
    type: Object,
    default: null,
  },
  returningHome: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits([
  "back-home",
  "job-started",
  "continue-step",
  "enter-preview",
  "enter-arena",
  "enter-done",
]);
</script>

<template>
  <LandingView
    v-if="currentView === 'landing'"
    @job-started="emit('job-started', $event)"
  />
  <ProcessingView
    v-else-if="currentView === 'processing'"
    :started-payload="startedPayload"
    :returning-home="returningHome"
    @back-home="emit('back-home')"
    @continue="emit('continue-step', $event)"
  />
  <PrescreenView
    v-else-if="currentView === 'prescreen'"
    :returning-home="returningHome"
    @back-home="emit('back-home')"
    @continue-preview="emit('enter-preview')"
  />
  <PreviewView
    v-else-if="currentView === 'preview'"
    :returning-home="returningHome"
    @back-home="emit('back-home')"
    @continue-arena="emit('enter-arena')"
  />
  <ArenaView
    v-else-if="currentView === 'arena'"
    :returning-home="returningHome"
    @back-home="emit('back-home')"
    @done="emit('enter-done')"
  />
  <DoneView
    v-else
    :returning-home="returningHome"
    @back-home="emit('back-home')"
    @continue-arena="emit('enter-arena')"
    @job-started="emit('job-started', $event)"
  />
</template>

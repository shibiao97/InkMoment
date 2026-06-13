<script setup>
import { computed } from "vue";
import ArenaView from "../views/ArenaView.vue";
import DoneView from "../views/DoneView.vue";
import LandingView from "../views/LandingView.vue";
import PrescreenView from "../views/PrescreenView.vue";
import PreviewView from "../views/PreviewView.vue";
import ProcessingView from "../views/ProcessingView.vue";

const props = defineProps({
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
  "busy-change",
  "continue-step",
  "enter-preview",
  "enter-arena",
  "enter-done",
]);

const VIEW_REGISTRY = {
  landing: {
    component: LandingView,
    props: () => ({}),
    listeners: () => ({
      "job-started": (payload) => emit("job-started", payload),
      "busy-change": (state) => emit("busy-change", state),
    }),
  },
  processing: {
    component: ProcessingView,
    props: () => ({
      startedPayload: props.startedPayload,
      returningHome: props.returningHome,
    }),
    listeners: () => ({
      "back-home": () => emit("back-home"),
      continue: (step) => emit("continue-step", step),
    }),
  },
  prescreen: {
    component: PrescreenView,
    props: () => ({ returningHome: props.returningHome }),
    listeners: () => ({
      "back-home": () => emit("back-home"),
      "continue-preview": () => emit("enter-preview"),
    }),
  },
  preview: {
    component: PreviewView,
    props: () => ({ returningHome: props.returningHome }),
    listeners: () => ({
      "back-home": () => emit("back-home"),
      "continue-arena": () => emit("enter-arena"),
    }),
  },
  arena: {
    component: ArenaView,
    props: () => ({ returningHome: props.returningHome }),
    listeners: () => ({
      "back-home": () => emit("back-home"),
      done: () => emit("enter-done"),
    }),
  },
  done: {
    component: DoneView,
    props: () => ({ returningHome: props.returningHome }),
    listeners: () => ({
      "back-home": () => emit("back-home"),
      "continue-arena": () => emit("enter-arena"),
      "job-started": (payload) => emit("job-started", payload),
    }),
  },
};

const activeView = computed(() => VIEW_REGISTRY[props.currentView] || VIEW_REGISTRY.done);
const activeProps = computed(() => activeView.value.props());
const activeListeners = computed(() => activeView.value.listeners());
</script>

<template>
  <component
    :is="activeView.component"
    v-bind="activeProps"
    v-on="activeListeners"
  />
</template>

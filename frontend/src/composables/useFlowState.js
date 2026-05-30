import { ref } from "vue";

const FLOW_VIEWS = new Set(["landing", "processing", "prescreen", "preview", "arena", "done"]);
const STEP_TO_VIEW = {
  prescreen: "prescreen",
  "confirm-prescreen": "prescreen",
  preview: "preview",
  arena: "arena",
  done: "done",
  home: "landing",
};

export function viewForStep(kind) {
  return STEP_TO_VIEW[kind] || "landing";
}

export function useFlowState() {
  const currentView = ref("landing");
  const startedPayload = ref(null);

  function go(view) {
    currentView.value = FLOW_VIEWS.has(view) ? view : "landing";
  }

  function enterProcessing(payload) {
    startedPayload.value = payload;
    go("processing");
  }

  function clearStartedPayload() {
    startedPayload.value = null;
  }

  function resumeStep(kind) {
    go(viewForStep(kind));
  }

  return {
    currentView,
    startedPayload,
    go,
    enterProcessing,
    clearStartedPayload,
    resumeStep,
    enterPreview: () => go("preview"),
    enterArena: () => go("arena"),
    enterDone: () => go("done"),
    enterHome: () => go("landing"),
  };
}

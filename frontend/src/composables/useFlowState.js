import { ref } from "vue";

export const FLOW_VIEW = Object.freeze({
  LANDING: "landing",
  PROCESSING: "processing",
  PRESCREEN: "prescreen",
  PREVIEW: "preview",
  ARENA: "arena",
  DONE: "done",
});

export const FLOW_VIEWS = new Set(Object.values(FLOW_VIEW));
export const STEP_TO_VIEW = Object.freeze({
  prescreen: FLOW_VIEW.PRESCREEN,
  "confirm-prescreen": FLOW_VIEW.PRESCREEN,
  preview: FLOW_VIEW.PREVIEW,
  arena: FLOW_VIEW.ARENA,
  done: FLOW_VIEW.DONE,
  home: FLOW_VIEW.LANDING,
});

export function viewForStep(kind) {
  return STEP_TO_VIEW[kind] || FLOW_VIEW.LANDING;
}

export function useFlowState() {
  const currentView = ref(FLOW_VIEW.LANDING);
  const startedPayload = ref(null);

  function go(view) {
    currentView.value = FLOW_VIEWS.has(view) ? view : FLOW_VIEW.LANDING;
  }

  function enterProcessing(payload) {
    startedPayload.value = payload;
    go(FLOW_VIEW.PROCESSING);
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
    navigateToView: go,
    enterProcessing,
    clearStartedPayload,
    resumeStep,
    navigateToStep: resumeStep,
    enterPreview: () => go(FLOW_VIEW.PREVIEW),
    enterArena: () => go(FLOW_VIEW.ARENA),
    enterDone: () => go(FLOW_VIEW.DONE),
    enterHome: () => go(FLOW_VIEW.LANDING),
  };
}

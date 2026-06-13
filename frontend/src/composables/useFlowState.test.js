import { describe, expect, it } from "vitest";

import {
  FLOW_VIEW,
  FLOW_VIEWS,
  STEP_TO_VIEW,
  useFlowState,
  viewForStep,
} from "./useFlowState";

describe("useFlowState", () => {
  it("exports stable workflow constants", () => {
    expect(FLOW_VIEW).toEqual({
      LANDING: "landing",
      PROCESSING: "processing",
      PRESCREEN: "prescreen",
      PREVIEW: "preview",
      ARENA: "arena",
      DONE: "done",
    });
    expect(FLOW_VIEWS).toEqual(new Set(["landing", "processing", "prescreen", "preview", "arena", "done"]));
    expect(STEP_TO_VIEW).toMatchObject({
      prescreen: "prescreen",
      "confirm-prescreen": "prescreen",
      preview: "preview",
      arena: "arena",
      done: "done",
      home: "landing",
    });
  });

  it("maps known backend steps to stable views", () => {
    expect(viewForStep("prescreen")).toBe("prescreen");
    expect(viewForStep("confirm-prescreen")).toBe("prescreen");
    expect(viewForStep("preview")).toBe("preview");
    expect(viewForStep("arena")).toBe("arena");
    expect(viewForStep("done")).toBe("done");
    expect(viewForStep("home")).toBe("landing");
    expect(viewForStep("unknown")).toBe("landing");
    expect(viewForStep()).toBe("landing");
  });

  it("guards unknown view transitions and preserves the start payload", () => {
    const flow = useFlowState();

    flow.enterProcessing({ folder: "/tmp/photos" });
    expect(flow.currentView.value).toBe("processing");
    expect(flow.startedPayload.value).toEqual({ folder: "/tmp/photos" });

    flow.go("missing");
    expect(flow.currentView.value).toBe("landing");
    expect(flow.startedPayload.value).toEqual({ folder: "/tmp/photos" });

    flow.resumeStep("arena");
    expect(flow.currentView.value).toBe("arena");

    flow.clearStartedPayload();
    expect(flow.startedPayload.value).toBeNull();
  });

  it("keeps payload cleanup explicit when returning home", () => {
    const flow = useFlowState();

    flow.enterProcessing({ folder: "/tmp/photos", mode: "fast" });
    flow.enterHome();

    expect(flow.currentView.value).toBe("landing");
    expect(flow.startedPayload.value).toEqual({ folder: "/tmp/photos", mode: "fast" });

    flow.clearStartedPayload();
    expect(flow.startedPayload.value).toBeNull();
  });

  it("navigates with shortcut helpers and backend step resume", () => {
    const flow = useFlowState();

    flow.navigateToView("processing");
    expect(flow.currentView.value).toBe("processing");

    flow.enterPreview();
    expect(flow.currentView.value).toBe("preview");

    flow.enterArena();
    expect(flow.currentView.value).toBe("arena");

    flow.enterDone();
    expect(flow.currentView.value).toBe("done");

    flow.resumeStep("confirm-prescreen");
    expect(flow.currentView.value).toBe("prescreen");

    flow.navigateToStep("preview");
    expect(flow.currentView.value).toBe("preview");

    flow.resumeStep("home");
    expect(flow.currentView.value).toBe("landing");

    flow.resumeStep("missing");
    expect(flow.currentView.value).toBe("landing");
  });
});

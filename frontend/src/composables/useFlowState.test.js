import { describe, expect, it } from "vitest";

import { useFlowState, viewForStep } from "./useFlowState";

describe("useFlowState", () => {
  it("maps known backend steps to stable views", () => {
    expect(viewForStep("prescreen")).toBe("prescreen");
    expect(viewForStep("confirm-prescreen")).toBe("prescreen");
    expect(viewForStep("preview")).toBe("preview");
    expect(viewForStep("arena")).toBe("arena");
    expect(viewForStep("done")).toBe("done");
    expect(viewForStep("unknown")).toBe("landing");
  });

  it("guards unknown view transitions and preserves the start payload", () => {
    const flow = useFlowState();

    flow.enterProcessing({ folder: "/tmp/photos" });
    expect(flow.currentView.value).toBe("processing");
    expect(flow.startedPayload.value).toEqual({ folder: "/tmp/photos" });

    flow.go("missing");
    expect(flow.currentView.value).toBe("landing");

    flow.resumeStep("arena");
    expect(flow.currentView.value).toBe("arena");

    flow.clearStartedPayload();
    expect(flow.startedPayload.value).toBeNull();
  });
});

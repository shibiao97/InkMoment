import { describe, expect, it } from "vitest";

import {
  buildLandingStartPayload,
  hasSameLandingStartPayload,
  landingStartPayloadSignature,
} from "./useLandingStartPayload";

function baseOptions(overrides = {}) {
  return {
    folder: " /tmp/photos ",
    mode: "move",
    engine: "fast",
    thresholdNear: 10,
    thresholdFar: 6,
    nearMinutes: 5,
    prescreenEnabled: true,
    prescreenStrength: "advanced",
    faceAware: true,
    selectedLlmModel: "vision-pro",
    ...overrides,
  };
}

describe("landing start payload", () => {
  it("normalizes form options into the backend start payload", () => {
    expect(buildLandingStartPayload(baseOptions())).toEqual({
      folder: "/tmp/photos",
      dry_run: false,
      wipe_cache: true,
      mode: "move",
      engine: "fast",
      threshold_near: 10,
      threshold_far: 6,
      near_seconds: 300,
      prescreen_enabled: true,
      prescreen_strength: "advanced",
      face_aware: false,
      llm_model: "",
    });
  });

  it("only enables face aware payloads for expert mode", () => {
    expect(buildLandingStartPayload(baseOptions({ engine: "expert" })).face_aware).toBe(true);
    expect(buildLandingStartPayload(baseOptions({ engine: "tycoon" })).face_aware).toBe(false);
  });

  it("only sends the selected model for tycoon mode", () => {
    expect(buildLandingStartPayload(baseOptions({ engine: "expert" })).llm_model).toBe("");
    expect(buildLandingStartPayload(baseOptions({ engine: "tycoon" })).llm_model).toBe("vision-pro");
  });

  it("detects stale pending start payloads when launch options change", () => {
    const pending = buildLandingStartPayload(baseOptions({ thresholdNear: 10 }));
    const current = buildLandingStartPayload(baseOptions({ thresholdNear: 11 }));

    expect(hasSameLandingStartPayload(pending, current)).toBe(false);
    expect(landingStartPayloadSignature(pending)).not.toBe(landingStartPayloadSignature(current));
  });
});

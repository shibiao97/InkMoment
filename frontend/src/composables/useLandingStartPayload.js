export function buildLandingStartPayload(options) {
  const engine = options.engine || "fast";
  return {
    folder: String(options.folder || "").trim(),
    dry_run: false,
    wipe_cache: true,
    mode: options.mode,
    engine,
    threshold_near: Number(options.thresholdNear),
    threshold_far: Number(options.thresholdFar),
    near_seconds: Number(options.nearMinutes) * 60,
    prescreen_enabled: Boolean(options.prescreenEnabled),
    prescreen_strength: options.prescreenStrength,
    face_aware: engine === "expert" && Boolean(options.faceAware),
    llm_model: engine === "tycoon" ? options.selectedLlmModel || "" : "",
  };
}

export function landingStartPayloadSignature(payload) {
  if (!payload) return "";
  return JSON.stringify([
    payload.folder,
    payload.mode,
    payload.engine,
    payload.threshold_near,
    payload.threshold_far,
    payload.near_seconds,
    payload.prescreen_enabled,
    payload.prescreen_strength,
    payload.face_aware,
    payload.llm_model,
  ]);
}

export function hasSameLandingStartPayload(left, right) {
  return landingStartPayloadSignature(left) === landingStartPayloadSignature(right);
}

export function canContinueLandingStartPayload(pendingPayload, currentPayload, capturedPayload) {
  return Boolean(
    pendingPayload
      && hasSameLandingStartPayload(pendingPayload, capturedPayload)
      && hasSameLandingStartPayload(capturedPayload, currentPayload),
  );
}

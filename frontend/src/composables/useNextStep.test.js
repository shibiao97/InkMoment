import { describe, expect, it } from "vitest";

import { resolveNextStep } from "./useNextStep";

function readyStatus(overrides = {}) {
  return {
    ready: true,
    prescreen_enabled: false,
    prescreen_reviewed: false,
    prescreen_pending_count: 0,
    selection_started: false,
    finished_groups: 0,
    total_groups: 8,
    unfinished_groups: 8,
    multi_groups: 3,
    winner_count: 0,
    ...overrides,
  };
}

describe("resolveNextStep", () => {
  it("returns home when backend status is not ready", () => {
    expect(resolveNextStep(null).kind).toBe("home");
    expect(resolveNextStep({ ready: false }).kind).toBe("home");
  });

  it("routes to prescreen when enabled and pending items exist", () => {
    const next = resolveNextStep(readyStatus({
      prescreen_enabled: true,
      prescreen_pending_count: 5,
    }));

    expect(next.kind).toBe("prescreen");
    expect(next.description).toContain("5 张照片");
  });

  it("routes to confirm-prescreen when prescreen has no pending items", () => {
    expect(resolveNextStep(readyStatus({
      prescreen_enabled: true,
      prescreen_pending_count: 0,
    })).kind).toBe("confirm-prescreen");
  });

  it("routes to done when every group is finished", () => {
    const next = resolveNextStep(readyStatus({
      finished_groups: 8,
      total_groups: 8,
      winner_count: 12,
    }));

    expect(next.kind).toBe("done");
    expect(next.description).toContain("已完成 8 组");
  });

  it("routes to arena when selection has started", () => {
    const next = resolveNextStep(readyStatus({
      selection_started: true,
      unfinished_groups: 2,
    }));

    expect(next.kind).toBe("arena");
    expect(next.description).toContain("还有 2 组未完成");
  });

  it("routes to preview for a ready session before manual selection", () => {
    const next = resolveNextStep(readyStatus({
      total_groups: 10,
      multi_groups: 4,
    }));

    expect(next.kind).toBe("preview");
    expect(next.description).toContain("10 个分组");
  });
});

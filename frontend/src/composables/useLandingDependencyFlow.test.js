import { describe, expect, it, vi, beforeEach } from "vitest";

import {
  downloadDependencies,
  getDependencyDownloadStatus,
  preflightDependencies,
  startJob,
} from "../api/inkmoment";
import { useLandingDependencyFlow } from "./useLandingDependencyFlow";

vi.mock("../api/inkmoment", () => ({
  downloadDependencies: vi.fn(),
  getDependencyDownloadStatus: vi.fn(),
  preflightDependencies: vi.fn(),
  startJob: vi.fn(),
}));

vi.mock("../api/runtime", () => ({
  pickDesktopFolder: vi.fn(),
}));

function startPayload(overrides = {}) {
  return {
    folder: "/tmp/photos",
    mode: "move",
    engine: "expert",
    threshold_near: 10,
    threshold_far: 6,
    near_seconds: 300,
    prescreen_enabled: true,
    prescreen_strength: "advanced",
    face_aware: true,
    llm_model: "",
    ...overrides,
  };
}

function createFlow(options = {}) {
  let payload = startPayload();
  const flow = useLandingDependencyFlow({
    buildStartPayload: () => ({ ...payload }),
    validateStartInputs: () => true,
    selectedEngineLabel: "专家模式",
    sleep: () => Promise.resolve(),
    downloadWaitMs: 100,
    downloadPollMs: 0,
    ...options,
  });
  return {
    flow,
    setPayload: (nextPayload) => {
      payload = startPayload(nextPayload);
    },
  };
}

describe("useLandingDependencyFlow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("ignores stale preflight failures after a newer request has completed", async () => {
    let rejectFirst;
    preflightDependencies
      .mockImplementationOnce(() => new Promise((_, reject) => {
        rejectFirst = reject;
      }))
      .mockResolvedValueOnce({
        ok: true,
        engine: "expert",
        engine_label: "专家模式",
        missing: [],
        download_dir: "/models",
      });
    const { flow } = createFlow();

    const first = flow.runDependencyPreflight(startPayload());
    const second = flow.runDependencyPreflight(startPayload());

    await expect(second).resolves.toMatchObject({ ok: true });
    rejectFirst(new Error("older failure"));
    await expect(first).resolves.toBeNull();

    expect(flow.dependencyError.value).toBe("");
    expect(flow.dependencyReport.value.ok).toBe(true);
    expect(flow.isCheckingDependencies.value).toBe(false);
  });

  it("does not launch after download when start options changed during the wait", async () => {
    let resolveDownload;
    preflightDependencies.mockResolvedValueOnce({
      ok: false,
      engine: "expert",
      engine_label: "专家模式",
      can_download: true,
      missing: [{ id: "model", label: "模型", detail: "missing", downloadable: true }],
    });
    downloadDependencies.mockImplementationOnce(() => new Promise((resolve) => {
      resolveDownload = resolve;
    }));
    getDependencyDownloadStatus.mockResolvedValueOnce({
      id: "download-1",
      status: "done",
      message: "done",
      download_dir: "/models",
    });
    const { flow, setPayload } = createFlow();

    await flow.handleStart();
    const download = flow.handleDependencyDownload();
    setPayload({ threshold_near: 12 });
    resolveDownload({
      id: "download-1",
      status: "running",
      message: "started",
    });
    await download;

    expect(startJob).not.toHaveBeenCalled();
    expect(preflightDependencies).toHaveBeenCalledOnce();
    expect(flow.dependencyMessage.value).toContain("启动参数已变化");
    expect(flow.isDownloadingDependencies.value).toBe(false);
    expect(flow.isStarting.value).toBe(false);
  });

  it("clears starting state when dependency state is reset during a download", async () => {
    let resolveDownload;
    downloadDependencies.mockImplementationOnce(() => new Promise((resolve) => {
      resolveDownload = resolve;
    }));
    const { flow } = createFlow();
    flow.pendingStartPayload.value = startPayload();

    const download = flow.handleDependencyDownload();
    await Promise.resolve();

    expect(flow.isStarting.value).toBe(true);
    expect(flow.isDownloadingDependencies.value).toBe(true);

    flow.clearDependencyState();
    resolveDownload({
      id: "download-1",
      status: "running",
      message: "started",
    });
    await download;

    expect(flow.isStarting.value).toBe(false);
    expect(flow.isDownloadingDependencies.value).toBe(false);
    expect(getDependencyDownloadStatus).not.toHaveBeenCalled();
  });
});

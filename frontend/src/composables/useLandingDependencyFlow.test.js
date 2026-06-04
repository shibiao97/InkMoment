import { describe, expect, it, vi, beforeEach } from "vitest";

import {
  downloadDependencies,
  getDependencyDownloadStatus,
  preflightDependencies,
  startJob,
} from "../api/inkmoment";
import { buildManualCommands, useLandingDependencyFlow } from "./useLandingDependencyFlow";

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
    selectedEngineLabel: "质感优选",
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
        engine_label: "质感优选",
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
      engine_label: "质感优选",
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

  it("builds manual install commands for missing pyiqa dependencies", async () => {
    preflightDependencies.mockResolvedValueOnce({
      ok: false,
      engine: "expert",
      engine_label: "质感优选",
      missing: [{
        id: "python:pyiqa",
        label: "pyiqa",
        detail: "Python 模块不可导入：ModuleNotFoundError",
        downloadable: false,
      }],
      manual_required: true,
    });
    const { flow } = createFlow();

    await flow.handleDependencyCheckOnly();

    expect(flow.dependencyManualCommands.value.join("\n")).toContain("'pyiqa>=0.1.10' 'timm>=0.9'");
    expect(flow.dependencyManualCommands.value.join("\n")).not.toContain("opencv-python");
    expect(flow.dependencyReportText.value).toContain("recommended_commands:");
  });

  it("allows one-click handling for repairable manual dependencies", async () => {
    preflightDependencies
      .mockResolvedValueOnce({
        ok: false,
        engine: "expert",
        engine_label: "质感优选",
        can_download: true,
        missing: [{
          id: "python:pyiqa",
          label: "pyiqa",
          detail: "Python 模块不可导入：FileNotFoundError: missing pyiqa/models",
          downloadable: false,
          repairable: true,
        }],
        manual_required: true,
      })
      .mockResolvedValueOnce({
        ok: true,
        engine: "expert",
        engine_label: "质感优选",
        missing: [],
      });
    downloadDependencies.mockResolvedValueOnce({
      id: "download-1",
      status: "done",
      message: "模块资源已修复完成。",
      repaired: [{ id: "python:pyiqa" }],
    });
    getDependencyDownloadStatus.mockResolvedValueOnce({
      id: "download-1",
      status: "done",
      message: "模块资源已修复完成。",
    });
    const { flow } = createFlow();

    await flow.handleDependencyCheckOnly();

    expect(flow.dependencyManualCount.value).toBe(1);
    expect(flow.dependencyActionableCount.value).toBe(1);
    expect(flow.canDownloadDependencies.value).toBe(true);

    await flow.handleDependencyDownload();

    expect(downloadDependencies).toHaveBeenCalledWith({ engine: "expert" });
    expect(flow.dependencyMessage.value).toBe("处理完成，当前模式运行资源已就绪");
  });
});

describe("buildManualCommands", () => {
  it("recommends the full mode install, package command, and model download when needed", () => {
    const commands = buildManualCommands({
      engine: "expert",
      missing: [
        { id: "python:pyiqa", downloadable: false },
        { id: "model:facebook/dinov2-small", downloadable: true },
      ],
    });

    expect(commands[0]).toContain("'torch>=2.2'");
    expect(commands.some((command) => command.includes("'pyiqa>=0.1.10' 'timm>=0.9'"))).toBe(true);
    expect(commands.some((command) => command.includes("scripts/download_models.py"))).toBe(true);
  });

  it("recommends manual model download even when the missing model is auto-downloadable", () => {
    const commands = buildManualCommands({
      engine: "expert",
      missing: [
        { id: "model:facebook/dinov2-small", downloadable: true },
      ],
    });

    expect(commands).toEqual([
      ".venv/bin/python scripts/download_models.py --model facebook/dinov2-small",
    ]);
  });
});

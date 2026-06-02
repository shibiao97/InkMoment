import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getSkipped,
  getStatus,
  getWinners,
  openFolder,
  reopenGroup,
  startJob,
} from "../api/inkmoment";
import { openDesktopPath } from "../api/runtime";
import { useDoneResults } from "./useDoneResults";

vi.mock("../api/inkmoment", () => ({
  getSkipped: vi.fn(),
  getStatus: vi.fn(),
  getWinners: vi.fn(),
  openFolder: vi.fn(),
  reopenGroup: vi.fn(),
  startJob: vi.fn(),
}));

vi.mock("../api/runtime", () => ({
  openDesktopPath: vi.fn(),
}));

describe("useDoneResults", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads status, winners, skipped entries and groups winners by group size", async () => {
    getStatus.mockResolvedValue({
      ready: true,
      image_count: 3,
      winner_count: 2,
      loser_count: 1,
      total_groups: 2,
      multi_groups: 1,
      mode: "copy",
    });
    getWinners.mockResolvedValue({
      winners: [
        { path: "/a.jpg", name: "a.jpg", group_size: 1 },
        { path: "/b.jpg", name: "b.jpg", group_size: 3 },
      ],
    });
    getSkipped.mockResolvedValue({ skipped: [{ path: "/bad.jpg", reason: "decode" }] });
    const done = useDoneResults();

    await done.load();

    expect(done.total.value).toBe(3);
    expect(done.kept.value).toBe(2);
    expect(done.rejected.value).toBe(1);
    expect(done.skipped.value).toHaveLength(1);
    expect(done.sections.value.map((section) => section.title)).toEqual(["独张保留", "连拍中胜出"]);
    expect(done.error.value).toBe("");
  });

  it("uses backend-equivalent defaults for redo payload fields missing from status", async () => {
    startJob.mockResolvedValue({});
    const done = useDoneResults();
    done.status.value = {
      folder: "/tmp/photos",
      mode: "move",
      engine: "expert",
    };

    await expect(done.redoCurrentSession()).resolves.toMatchObject({
      folder: "/tmp/photos",
      mode: "move",
      engine: "expert",
      prescreen_enabled: true,
      face_aware: true,
    });

    expect(startJob).toHaveBeenCalledWith(expect.objectContaining({
      prescreen_enabled: true,
      face_aware: true,
      wipe_cache: true,
    }));
  });

  it("preserves explicit false redo payload settings", async () => {
    startJob.mockResolvedValue({});
    const done = useDoneResults();
    done.status.value = {
      folder: "/tmp/photos",
      prescreen_enabled: false,
      face_aware: false,
    };

    await done.redoCurrentSession();

    expect(startJob).toHaveBeenCalledWith(expect.objectContaining({
      prescreen_enabled: false,
      face_aware: false,
    }));
  });

  it("uses the desktop opener before falling back to the backend folder opener", async () => {
    openDesktopPath.mockResolvedValue(true);
    const done = useDoneResults();
    done.status.value = { folder: "/tmp/photos" };

    await expect(done.openOutputFolder()).resolves.toBe(true);

    expect(openDesktopPath).toHaveBeenCalledWith("/tmp/photos");
    expect(openFolder).not.toHaveBeenCalled();
  });

  it("emits a continue-ready result only when reopen succeeds", async () => {
    reopenGroup.mockResolvedValue({});
    const done = useDoneResults();

    await expect(done.reopenWinnerGroup("group-a")).resolves.toBe(true);

    expect(reopenGroup).toHaveBeenCalledWith("group-a");
    expect(done.reopeningGroupId.value).toBe("");
  });
});

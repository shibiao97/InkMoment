import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  chooseGroup,
  getGroup,
  getStatus,
} from "../api/inkmoment";
import { formatMeta, useArenaGroup } from "./useArenaGroup";

vi.mock("../api/inkmoment", () => ({
  chooseGroup: vi.fn(),
  getGroup: vi.fn(),
  getStatus: vi.fn(),
  skipGroup: vi.fn(),
  undoGroup: vi.fn(),
}));

describe("useArenaGroup", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("formats metadata and marks fields that differ from the paired image", () => {
    expect(formatMeta(
      { camera: "A7", iso: 100, shutter: "1/200" },
      { camera: "A7", iso: 400, shutter: "1/200" },
    )).toEqual([
      { key: "camera", value: "A7", different: false },
      { key: "shutter", value: "1/200", different: false },
      { key: "iso", value: "ISO 100", different: true },
    ]);
  });

  it("loads the current group and status together", async () => {
    getGroup.mockResolvedValue({
      done: false,
      group: { id: 1, left: "/left.jpg" },
    });
    getStatus.mockResolvedValue({
      multi_groups: 4,
      finished_multi_groups: 1,
    });
    const arena = useArenaGroup();

    await arena.load();

    expect(arena.group.value.left).toBe("/left.jpg");
    expect(arena.done.value).toBe(false);
    expect(arena.overallPercent.value).toBe(25);
    expect(arena.error.value).toBe("");
  });

  it("keeps the next group when status refresh fails after a successful choice", async () => {
    chooseGroup.mockResolvedValue({
      done: false,
      group: { id: 2, left: "/next.jpg" },
    });
    getStatus.mockRejectedValue(new Error("status offline"));
    const arena = useArenaGroup();
    arena.group.value = { id: 1, left: "/old.jpg", right: "/old-right.jpg" };

    await expect(arena.choose("right")).resolves.toBe(true);

    expect(chooseGroup).toHaveBeenCalledWith("right");
    expect(arena.group.value.left).toBe("/next.jpg");
    expect(arena.done.value).toBe(false);
    expect(arena.error.value).toBe("status offline");
    expect(arena.busy.value).toBe(false);
  });
});

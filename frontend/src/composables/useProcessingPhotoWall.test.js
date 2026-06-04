import { nextTick, ref } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  classifyProcessingEventReason,
  processingEventImagePath,
  processingWallCellState,
  useProcessingPhotoWall,
} from "./useProcessingPhotoWall";

describe("useProcessingPhotoWall", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it("queues and paints incoming events at the wall fill cadence", async () => {
    const events = ref([]);
    const wall = useProcessingPhotoWall({
      events,
      status: ref("hashing"),
      total: ref(2),
      random: () => 0,
    });

    events.value = [
      { seq: 1, ok: true, name: "a.jpg" },
      { seq: 2, ok: false, reason: "decode error" },
    ];
    await nextTick();

    expect(wall.filledCount.value).toBe(0);
    vi.advanceTimersByTime(200);
    expect(wall.filledCount.value).toBe(1);
    expect(wall.cells.value.some((cell) => cell.event?.seq === 1)).toBe(true);

    vi.advanceTimersByTime(200);
    expect(wall.filledCount.value).toBe(2);
    expect(wall.cells.value.some((cell) => cell.event?.seq === 2)).toBe(true);
  });

  it("keeps echoing queued events while the backend is grouping", async () => {
    const events = ref([{ seq: 1, ok: true, name: "a.jpg" }]);
    const status = ref("grouping");
    const wall = useProcessingPhotoWall({
      events,
      status,
      total: ref(1),
      random: () => 0,
    });
    await nextTick();

    vi.advanceTimersByTime(60);
    expect(wall.filledCount.value).toBe(1);
    expect(wall.collecting.value).toBe(true);

    status.value = "done";
    await nextTick();

    expect(wall.collecting.value).toBe(false);
    expect(wall.filledCount.value).toBe(1);
  });

  it("resets stale cells when a new event stream restarts from a lower seq", async () => {
    const events = ref([]);
    const wall = useProcessingPhotoWall({
      events,
      status: ref("hashing"),
      total: ref(1),
      random: () => 0,
    });

    events.value = [{ seq: 5, ok: true, name: "old.jpg" }];
    await nextTick();
    vi.advanceTimersByTime(200);
    expect(wall.cells.value[0].event.name).toBe("old.jpg");

    events.value = [{ seq: 1, ok: true, name: "new.jpg" }];
    await nextTick();
    expect(wall.filledCount.value).toBe(0);

    vi.advanceTimersByTime(200);
    expect(wall.cells.value[0].event.name).toBe("new.jpg");
  });

  it("clears replacement timers when stopped", async () => {
    const events = ref([{ seq: 1, ok: true, name: "a.jpg" }]);
    const wall = useProcessingPhotoWall({
      events,
      status: ref("hashing"),
      total: ref(1),
      random: () => 0,
    });
    await nextTick();
    vi.advanceTimersByTime(200);

    events.value = [
      { seq: 1, ok: true, name: "a.jpg" },
      { seq: 2, ok: true, name: "b.jpg" },
    ];
    await nextTick();
    vi.advanceTimersByTime(420);
    expect(wall.cells.value[0].event.name).toBe("b.jpg");
    expect(wall.cells.value[0].leaving).toBe(true);

    wall.stop();
    vi.advanceTimersByTime(220);
    expect(wall.cells.value[0].leaving).toBe(true);
  });

  it("maps rejection reasons and cell state labels", () => {
    expect(classifyProcessingEventReason("照片模糊")).toBe("blur");
    expect(classifyProcessingEventReason("闭眼")).toBe("eyes");
    expect(classifyProcessingEventReason("曝光过亮")).toBe("exposure");
    expect(processingWallCellState({ ok: false, reason: "decode error" })).toEqual({
      kind: "error",
      category: "other",
      label: "UNREAD",
      reason: "decode error",
    });
    expect(processingWallCellState({ reject: true, reason: "照片模糊" }).label).toBe("BLUR");
  });

  it("resolves compatible image path fields from backend events", () => {
    expect(processingEventImagePath({ path: "/photos/a.jpg" })).toBe("/photos/a.jpg");
    expect(processingEventImagePath({ image_path: "/photos/b.jpg" })).toBe("/photos/b.jpg");
    expect(processingEventImagePath({ original_path: "/photos/c.jpg" })).toBe("/photos/c.jpg");
    expect(processingEventImagePath({ thumbnail_path: "/photos/d.jpg" })).toBe("/photos/d.jpg");
    expect(processingEventImagePath({ thumb_path: "/photos/e.jpg" })).toBe("/photos/e.jpg");
    expect(processingEventImagePath(null)).toBe("");
  });
});

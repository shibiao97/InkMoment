import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getJob, streamJob } from "../api/inkmoment";
import { useJobPolling } from "./useJobPolling";

vi.mock("../api/inkmoment", () => ({
  cancelJob: vi.fn(),
  getJob: vi.fn(),
  streamJob: vi.fn(),
}));

function flushPromises() {
  return new Promise((resolve) => window.setTimeout(resolve, 0));
}

function createEventSource() {
  const listeners = {};
  return {
    close: vi.fn(),
    addEventListener: vi.fn((name, handler) => {
      listeners[name] = handler;
    }),
    emit(name, data) {
      listeners[name]?.({ data: JSON.stringify(data) });
    },
    fail() {
      this.onerror?.(new Error("stream failed"));
    },
  };
}

describe("useJobPolling", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it("uses SSE first and stops when a terminal job event arrives", () => {
    const source = createEventSource();
    streamJob.mockReturnValue(source);

    const polling = useJobPolling();
    polling.start();

    expect(polling.isStreaming.value).toBe(true);
    expect(streamJob).toHaveBeenCalledWith(0);

    source.emit("job", {
      task_id: "job-1",
      status: "done",
      done: 4,
      total: 4,
      elapsed: 61,
      events: [{ seq: 1, message: "finished" }],
    });

    expect(polling.progressPercent.value).toBe(100);
    expect(polling.elapsedText.value).toBe("1 分 1 秒");
    expect(polling.events.value).toHaveLength(1);
    expect(polling.isStreaming.value).toBe(false);
    expect(source.close).toHaveBeenCalledOnce();
  });

  it("falls back to polling when SSE is unavailable", async () => {
    streamJob.mockReturnValue(null);
    getJob.mockResolvedValue({
      task_id: "job-1",
      status: "running",
      done: 2,
      total: 5,
      events: [{ seq: 1, message: "progress" }],
    });

    const polling = useJobPolling();
    polling.start();
    await flushPromises();

    expect(polling.isPolling.value).toBe(true);
    expect(polling.progressPercent.value).toBe(40);
    expect(polling.events.value[0].message).toBe("progress");

    polling.stop();
    expect(polling.isPolling.value).toBe(false);
  });

  it("restarts streaming from the first event when start is called again", () => {
    const firstSource = createEventSource();
    const secondSource = createEventSource();
    streamJob.mockReturnValueOnce(firstSource).mockReturnValueOnce(secondSource);

    const polling = useJobPolling();
    polling.start();
    firstSource.emit("job", {
      task_id: "job-1",
      status: "done",
      done: 3,
      total: 3,
      events: [{ seq: 3, message: "finished" }],
    });
    expect(polling.events.value).toHaveLength(1);

    polling.start();

    expect(streamJob).toHaveBeenLastCalledWith(0);
    expect(polling.events.value).toEqual([]);
    expect(polling.isStreaming.value).toBe(true);
  });

  it("clears stale events when the backend payload switches to a new task", () => {
    const source = createEventSource();
    streamJob.mockReturnValue(source);

    const polling = useJobPolling();
    polling.start();
    source.emit("job", {
      task_id: "job-1",
      status: "hashing",
      done: 5,
      total: 10,
      events: [{ seq: 5, message: "old task" }],
    });
    source.emit("job", {
      task_id: "job-2",
      status: "hashing",
      done: 1,
      total: 10,
      events: [{ seq: 1, message: "new task" }],
    });

    expect(polling.events.value).toEqual([{ seq: 1, message: "new task" }]);
  });

  it("backfills image events when a terminal stream payload only carries event_seq", async () => {
    const source = createEventSource();
    streamJob.mockReturnValue(source);
    getJob.mockResolvedValue({
      task_id: "job-1",
      status: "done",
      done: 2,
      total: 2,
      event_seq: 2,
      events: [
        { seq: 1, message: "first image" },
        { seq: 2, message: "second image" },
      ],
    });

    const polling = useJobPolling();
    polling.start();
    source.emit("job", {
      task_id: "job-1",
      status: "done",
      done: 2,
      total: 2,
      event_seq: 2,
      events: [],
    });
    await flushPromises();

    expect(getJob).toHaveBeenCalledWith(0);
    expect(polling.events.value.map((event) => event.message)).toEqual(["first image", "second image"]);
  });
});

import { computed, getCurrentInstance, onBeforeUnmount, ref, toValue, watch } from "vue";

export const MAX_WALL_CELL_COUNT = 40;
export const FALLBACK_WALL_CELL_COUNT = 1;
const WALL_FILL_MS = 200;
const WALL_REPLACE_MS = 420;
const WALL_LEAVE_MS = 220;
const WALL_QUEUE_CAP = 80;

const ACTIVE_JOB_STATUSES = new Set(["pending", "scanning", "hashing", "checking", "grouping"]);
const RESET_BOUNDARY_STATUSES = new Set(["", "idle", "done", "error", "cancelled"]);

const CAT_LABEL = {
  blur: "BLUR",
  eyes: "EYES",
  exposure: "EXPOSURE",
  comp: "FRAMING",
  format: "FORMAT",
  other: "OTHER",
};

function readSource(source, fallback) {
  const value = toValue(source);
  return value ?? fallback;
}

export function normalizeProcessingWallCellCount(count) {
  return Math.max(
    FALLBACK_WALL_CELL_COUNT,
    Math.min(MAX_WALL_CELL_COUNT, Math.floor(Number(count) || 0)),
  );
}

export function classifyProcessingEventReason(reason) {
  if (!reason) return "other";
  if (/失焦|焦点|模糊|未跟上/.test(reason)) return "blur";
  if (/闭眼|眨眼/.test(reason)) return "eyes";
  if (/曝光|高光|过暗|过亮|溢出/.test(reason)) return "exposure";
  if (/被切|反差|信息|缺少/.test(reason)) return "comp";
  if (/截图|尺寸|文件异常|非拍摄/.test(reason)) return "format";
  return "other";
}

export function processingWallCellState(event) {
  if (!event) return { kind: "", category: "other", label: "", reason: "" };
  if (event.reject) {
    const category = classifyProcessingEventReason(event.reason);
    return {
      kind: "rejected",
      category,
      label: CAT_LABEL[category] || CAT_LABEL.other,
      reason: event.reason || "失败",
    };
  }
  if (!event.ok) {
    return {
      kind: "error",
      category: "other",
      label: "UNREAD",
      reason: event.reason || "未能读取",
    };
  }
  return { kind: "ok", category: "other", label: "", reason: "" };
}

function createEmptyCells(count) {
  return Array.from({ length: normalizeProcessingWallCellCount(count) }, (_, index) => ({
    id: index,
    event: null,
    insertedAt: 0,
    leaving: false,
  }));
}

function maxEventSeq(events) {
  let maxSeq = 0;
  for (const event of events) {
    const seq = Number(event?.seq || 0);
    if (seq > maxSeq) maxSeq = seq;
  }
  return maxSeq;
}

function shouldResetForStatus(status, previous) {
  if (previous === undefined) return false;
  return ACTIVE_JOB_STATUSES.has(status) && RESET_BOUNDARY_STATUSES.has(previous || "");
}

export function useProcessingPhotoWall({
  events,
  status,
  total,
  random = Math.random,
} = {}) {
  const cells = ref(createEmptyCells(resolveCellCount()));
  const queue = [];
  const leaveTimers = new Set();
  let drainTimer = null;
  let seenSeq = 0;
  let insertedAt = 0;

  const filledCount = computed(() => cells.value.filter((cell) => cell.event).length);
  const collecting = computed(() => readStatus() === "grouping");
  const wallCellCount = computed(() => cells.value.length);
  const wallCountLabel = computed(() => {
    const totalValue = normalizedTotal();
    if (totalValue > MAX_WALL_CELL_COUNT) return `${MAX_WALL_CELL_COUNT}+`;
    return wallCellCount.value.toLocaleString();
  });
  const wallColumns = computed(() => {
    const count = wallCellCount.value;
    if (count <= 2) return Math.max(1, count);
    if (count <= 4) return count;
    if (count <= 8) return 4;
    if (count <= 15) return 5;
    if (count <= 24) return 6;
    return 10;
  });
  const wallStyle = computed(() => {
    const columns = wallColumns.value;
    const maxWidth = columns >= 10
      ? "100%"
      : `${columns * 168 + Math.max(0, columns - 1) * 8}px`;
    return {
      "--wall-cols": String(columns),
      "--wall-max-width": maxWidth,
    };
  });

  function readEvents() {
    const value = readSource(events, []);
    return Array.isArray(value) ? value : [];
  }

  function readStatus() {
    return String(readSource(status, "") || "");
  }

  function normalizedTotal() {
    const totalValue = Number(readSource(total, 0) || 0);
    if (!Number.isFinite(totalValue)) return 0;
    return Math.max(0, Math.floor(totalValue));
  }

  function resolveCellCount(nextEvents = readEvents()) {
    const totalValue = normalizedTotal();
    if (totalValue > 0) return normalizeProcessingWallCellCount(totalValue);
    return normalizeProcessingWallCellCount(nextEvents.length);
  }

  function resizeCells(nextCount) {
    const targetCount = normalizeProcessingWallCellCount(nextCount);
    if (cells.value.length === targetCount) return;

    const loadedCells = cells.value
      .filter((cell) => cell.event)
      .sort((left, right) => left.insertedAt - right.insertedAt)
      .slice(-targetCount);
    const nextCells = createEmptyCells(targetCount);
    loadedCells.forEach((cell, index) => {
      nextCells[index] = {
        ...nextCells[index],
        event: cell.event,
        insertedAt: cell.insertedAt,
        leaving: false,
      };
    });
    cells.value = nextCells;
  }

  function syncCellCount(nextEvents = readEvents()) {
    resizeCells(resolveCellCount(nextEvents));
  }

  function pickCellIndex() {
    const emptyIndexes = [];
    cells.value.forEach((cell, index) => {
      if (!cell.event) emptyIndexes.push(index);
    });
    if (emptyIndexes.length) {
      return emptyIndexes[Math.floor(random() * emptyIndexes.length)];
    }

    let oldestIndex = 0;
    for (let index = 1; index < cells.value.length; index += 1) {
      if (cells.value[index].insertedAt < cells.value[oldestIndex].insertedAt) {
        oldestIndex = index;
      }
    }
    return oldestIndex;
  }

  function paintEvent(event) {
    const index = pickCellIndex();
    const previous = cells.value[index];
    const wasLoaded = Boolean(previous.event);
    const nextCell = {
      ...previous,
      event,
      insertedAt: insertedAt += 1,
      leaving: wasLoaded,
    };
    cells.value.splice(index, 1, nextCell);

    if (wasLoaded) {
      const timer = window.setTimeout(() => {
        leaveTimers.delete(timer);
        const current = cells.value[index];
        if (current?.event?.seq === event.seq) {
          cells.value.splice(index, 1, { ...current, leaving: false });
        }
      }, WALL_LEAVE_MS);
      leaveTimers.add(timer);
    }
  }

  function drainQueue() {
    if (queue.length > WALL_QUEUE_CAP) {
      queue.splice(0, queue.length - WALL_QUEUE_CAP);
    }
    const event = queue.shift();
    if (event) paintEvent(event);
    scheduleDrain();
  }

  function scheduleDrain() {
    clearDrainTimer();
    if (collecting.value) return;
    if (!queue.length) return;
    const hasEmpty = cells.value.some((cell) => !cell.event);
    drainTimer = window.setTimeout(drainQueue, hasEmpty ? WALL_FILL_MS : WALL_REPLACE_MS);
  }

  function clearDrainTimer() {
    if (drainTimer) {
      window.clearTimeout(drainTimer);
      drainTimer = null;
    }
  }

  function clearLeaveTimers() {
    for (const timer of leaveTimers) {
      window.clearTimeout(timer);
    }
    leaveTimers.clear();
  }

  function stop() {
    clearDrainTimer();
    clearLeaveTimers();
  }

  function resetWall(nextEvents = readEvents()) {
    stop();
    queue.splice(0);
    cells.value = createEmptyCells(resolveCellCount(nextEvents));
    seenSeq = 0;
    insertedAt = 0;
    scheduleDrain();
  }

  function syncEventQueue(nextEvents = readEvents()) {
    syncCellCount(nextEvents);
    const nextMaxSeq = maxEventSeq(nextEvents);
    if (seenSeq > 0 && nextMaxSeq > 0 && nextMaxSeq < seenSeq) {
      resetWall(nextEvents);
    }

    let queued = false;
    for (const event of nextEvents) {
      if (!event?.seq || event.seq <= seenSeq) continue;
      queue.push(event);
      seenSeq = event.seq;
      queued = true;
    }
    if (queued) scheduleDrain();
  }

  watch(
    () => readStatus(),
    (nextStatus, previousStatus) => {
      if (shouldResetForStatus(nextStatus, previousStatus)) resetWall();
      scheduleDrain();
    },
    { immediate: true },
  );

  watch(
    () => readEvents(),
    (nextEvents) => {
      syncEventQueue(nextEvents);
    },
    { deep: true, immediate: true },
  );

  watch(
    () => readSource(total, 0),
    () => {
      syncCellCount();
      scheduleDrain();
    },
  );

  if (getCurrentInstance()) {
    onBeforeUnmount(stop);
  }

  return {
    cells,
    filledCount,
    collecting,
    wallCellCount,
    wallCountLabel,
    wallColumns,
    wallStyle,
    cellState: processingWallCellState,
    resetWall,
    stop,
  };
}

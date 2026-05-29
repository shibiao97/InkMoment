<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { imageUrl } from "../api/http";

const MAX_WALL_CELL_COUNT = 40;
const FALLBACK_WALL_CELL_COUNT = 1;
const WALL_FILL_MS = 200;
const WALL_REPLACE_MS = 420;
const WALL_QUEUE_CAP = 80;

const CAT_LABEL = {
  blur: "BLUR",
  eyes: "EYES",
  exposure: "EXPOSURE",
  comp: "FRAMING",
  format: "FORMAT",
  other: "OTHER",
};

const props = defineProps({
  events: {
    type: Array,
    default: () => [],
  },
  status: {
    type: String,
    default: "",
  },
  total: {
    type: Number,
    default: 0,
  },
});

const cells = ref(createEmptyCells(resolveCellCount()));
const queue = [];
let drainTimer = null;
let seenSeq = 0;
let insertedAt = 0;

const filledCount = computed(() => cells.value.filter((cell) => cell.event).length);
const collecting = computed(() => props.status === "grouping");
const wallCellCount = computed(() => cells.value.length);
const wallCountLabel = computed(() => {
  const total = normalizedTotal();
  if (total > MAX_WALL_CELL_COUNT) return `${MAX_WALL_CELL_COUNT}+`;
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

function normalizedTotal() {
  const total = Number(props.total || 0);
  if (!Number.isFinite(total)) return 0;
  return Math.max(0, Math.floor(total));
}

function normalizeCellCount(count) {
  return Math.max(
    FALLBACK_WALL_CELL_COUNT,
    Math.min(MAX_WALL_CELL_COUNT, Math.floor(Number(count) || 0)),
  );
}

function resolveCellCount(events = props.events) {
  const total = normalizedTotal();
  if (total > 0) return normalizeCellCount(total);
  return normalizeCellCount(Array.isArray(events) ? events.length : 0);
}

function createEmptyCells(count) {
  return Array.from({ length: normalizeCellCount(count) }, (_, index) => ({
    id: index,
    event: null,
    insertedAt: 0,
    leaving: false,
  }));
}

function resizeCells(nextCount) {
  const targetCount = normalizeCellCount(nextCount);
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

function syncCellCount(events = props.events) {
  resizeCells(resolveCellCount(events));
}

function classifyReason(reason) {
  if (!reason) return "other";
  if (/失焦|焦点|模糊|未跟上/.test(reason)) return "blur";
  if (/闭眼|眨眼/.test(reason)) return "eyes";
  if (/曝光|高光|过暗|过亮|溢出/.test(reason)) return "exposure";
  if (/被切|反差|信息|缺少/.test(reason)) return "comp";
  if (/截图|尺寸|文件异常|非拍摄/.test(reason)) return "format";
  return "other";
}

function cellState(event) {
  if (!event) return { kind: "", category: "other", label: "", reason: "" };
  if (event.reject) {
    const category = classifyReason(event.reason);
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

function pickCellIndex() {
  const emptyIndexes = [];
  cells.value.forEach((cell, index) => {
    if (!cell.event) emptyIndexes.push(index);
  });
  if (emptyIndexes.length) {
    return emptyIndexes[Math.floor(Math.random() * emptyIndexes.length)];
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
    window.setTimeout(() => {
      const current = cells.value[index];
      if (current?.event?.seq === event.seq) {
        cells.value.splice(index, 1, { ...current, leaving: false });
      }
    }, 220);
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

function resetWall() {
  clearDrainTimer();
  queue.splice(0);
  cells.value = createEmptyCells(resolveCellCount());
  seenSeq = 0;
  insertedAt = 0;
  scheduleDrain();
}

watch(
  () => props.events,
  (events) => {
    syncCellCount(events);
    let queued = false;
    for (const event of events) {
      if (!event?.seq || event.seq <= seenSeq) continue;
      queue.push(event);
      seenSeq = event.seq;
      queued = true;
    }
    if (queued) scheduleDrain();
  },
  { deep: true },
);

watch(
  () => props.total,
  () => {
    syncCellCount();
    scheduleDrain();
  },
);

watch(
  () => props.status,
  (status, previous) => {
    if (status && previous === "idle") resetWall();
    scheduleDrain();
  },
  { immediate: true },
);

onBeforeUnmount(clearDrainTimer);
</script>

<template>
  <section class="processing-wall-panel">
    <div class="processing-wall-head">
      <div>
        <p class="eyebrow">照片墙</p>
        <h2>每张照片都会经过这里</h2>
      </div>
      <span>{{ filledCount }} / {{ wallCountLabel }}</span>
    </div>

    <div class="processing-photo-wall" :class="{ collecting }" :style="wallStyle">
      <article
        v-for="cell in cells"
        :key="cell.id"
        class="wall-cell-vue"
        :class="[
          cell.event ? 'loaded' : '',
          cell.leaving ? 'leaving' : '',
          cellState(cell.event).kind,
          cell.event?.reject ? `cat-${cellState(cell.event).category}` : '',
        ]"
      >
        <img
          v-if="cell.event?.path"
          class="wall-image-vue"
          :src="imageUrl(cell.event.path, 260)"
          :alt="cell.event.name || '正在分析的照片'"
          loading="lazy"
        >
        <div class="wall-overlay-vue">
          <div class="overlay-text-vue">
            <span class="overlay-cat-vue">{{ cellState(cell.event).label }}</span>
            <span class="overlay-reason-vue">{{ cellState(cell.event).reason }}</span>
          </div>
        </div>
      </article>

      <div v-if="collecting" class="wall-deck-overlay-vue visible">
        <div class="deck-label-vue">正在整理分组...</div>
      </div>
    </div>
  </section>
</template>

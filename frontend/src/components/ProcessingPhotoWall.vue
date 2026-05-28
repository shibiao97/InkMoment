<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { imageUrl } from "../api/http";

const WALL_CELL_COUNT = 40;
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
});

const cells = ref(createEmptyCells());
const queue = [];
let drainTimer = null;
let seenSeq = 0;
let insertedAt = 0;

const filledCount = computed(() => cells.value.filter((cell) => cell.event).length);
const collecting = computed(() => props.status === "grouping");

function createEmptyCells() {
  return Array.from({ length: WALL_CELL_COUNT }, (_, index) => ({
    id: index,
    event: null,
    insertedAt: 0,
    leaving: false,
  }));
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
  cells.value = createEmptyCells();
  seenSeq = 0;
  insertedAt = 0;
  scheduleDrain();
}

watch(
  () => props.events,
  (events) => {
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
      <span>{{ filledCount }} / {{ WALL_CELL_COUNT }}</span>
    </div>

    <div class="processing-photo-wall" :class="{ collecting }">
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

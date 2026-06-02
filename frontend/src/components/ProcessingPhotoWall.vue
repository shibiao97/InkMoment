<script setup>
import { imageUrl } from "../api/http";
import { useProcessingPhotoWall } from "../composables/useProcessingPhotoWall";

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

const {
  cells,
  filledCount,
  collecting,
  wallCountLabel,
  wallStyle,
  cellState,
} = useProcessingPhotoWall({
  events: () => props.events,
  status: () => props.status,
  total: () => props.total,
});
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

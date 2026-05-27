<script setup>
import { imageUrl } from "../api/http";

defineProps({
  snapshot: {
    type: Object,
    default: null,
  },
});
</script>

<template>
  <div v-if="snapshot" class="folder-snapshot">
    <div class="snap-row">
      <div class="snap-stat">
        <div class="snap-num">{{ Number(snapshot.count).toLocaleString() }}</div>
        <div class="snap-cap">张照片</div>
      </div>
      <div class="snap-divider"></div>
      <div class="snap-stat">
        <div class="snap-line">
          {{ snapshot.latest ? `${snapshot.earliest} - ${snapshot.latest}` : snapshot.earliest }}
        </div>
        <div class="snap-line snap-line-sub">
          {{ snapshot.active_period ? `主要在 ${snapshot.active_period} 拍摄` : "" }}
        </div>
      </div>
      <div class="snap-divider"></div>
      <div class="snap-stat">
        <div class="snap-line">{{ snapshot.size_text }}</div>
        <div class="snap-line snap-line-sub">
          {{ snapshot.span_days > 1 ? `跨 ${snapshot.span_days} 天` : "" }}
        </div>
      </div>
    </div>

    <div v-if="snapshot.samples?.length" class="snap-samples">
      <img
        v-for="sample in snapshot.samples.slice(0, 3)"
        :key="sample"
        :src="imageUrl(sample, 220)"
        alt=""
        loading="lazy"
      >
    </div>
  </div>
</template>

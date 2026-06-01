<script setup>
import { imageUrl } from "../../api/http";

defineProps({
  group: {
    type: Object,
    required: true,
  },
  leftMeta: {
    type: Array,
    required: true,
  },
  rightMeta: {
    type: Array,
    required: true,
  },
  disableActions: {
    type: Boolean,
    required: true,
  },
  isSingleReview: {
    type: Boolean,
    required: true,
  },
});

const emit = defineEmits(["choose-left", "choose-right", "zoom"]);

function basename(path) {
  if (!path) return "无图";
  return path.split(/[\\/]/).pop() || path;
}
</script>

<template>
  <section class="arena-stage" :class="{ 'single-review': isSingleReview }">
    <article class="arena-side">
      <div class="arena-photo">
        <button
          v-if="group.left"
          class="arena-photo-button"
          type="button"
          @click="emit('zoom', 'left')"
        >
          <img :src="imageUrl(group.left, 1200)" :alt="basename(group.left)">
        </button>
      </div>
      <div class="arena-meta">
        <h2>{{ basename(group.left) }}</h2>
        <div class="meta-pills">
          <span
            v-for="item in leftMeta"
            :key="item.key"
            :class="{ diff: item.different }"
          >
            {{ item.value }}
          </span>
        </div>
      </div>
      <button class="btn-primary" type="button" :disabled="disableActions" @click="emit('choose-left')">
        {{ isSingleReview ? "保留这张" : "留左边" }}
      </button>
    </article>

    <article v-if="!isSingleReview" class="arena-side" :class="{ empty: !group.right }">
      <div class="arena-photo">
        <button
          v-if="group.right"
          class="arena-photo-button"
          type="button"
          @click="emit('zoom', 'right')"
        >
          <img :src="imageUrl(group.right, 1200)" :alt="basename(group.right)">
        </button>
        <span v-else>右侧无图</span>
      </div>
      <div class="arena-meta">
        <h2>{{ basename(group.right) }}</h2>
        <div class="meta-pills">
          <span
            v-for="item in rightMeta"
            :key="item.key"
            :class="{ diff: item.different }"
          >
            {{ item.value }}
          </span>
        </div>
      </div>
      <button class="btn-primary" type="button" :disabled="disableActions || !group.right" @click="emit('choose-right')">
        留右边
      </button>
    </article>
  </section>
</template>

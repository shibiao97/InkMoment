<script setup>
import { imageUrl } from "../../api/http";

defineProps({
  winners: {
    type: Array,
    required: true,
  },
  sections: {
    type: Array,
    required: true,
  },
  reopeningGroupId: {
    type: [String, Number],
    default: "",
  },
});

const emit = defineEmits(["reopen"]);
</script>

<template>
  <section class="done-winners">
    <div class="winners-section-head">
      <h2 class="winners-section-title">这次留下的</h2>
      <span class="winners-count">{{ winners.length }} 张</span>
    </div>

    <div v-for="section in sections" :key="section.title" class="done-section">
      <div class="album-chapter">
        <span class="album-chapter-name">{{ section.title }}</span>
        <span class="album-chapter-meta">{{ section.items.length }} 张</span>
      </div>
      <div class="done-grid">
        <article v-for="item in section.items" :key="item.path" class="done-card">
          <img :src="imageUrl(item.path, 520)" :alt="item.name" loading="lazy">
          <span>{{ item.group_size > 1 ? `从 ${item.group_size} 张里` : "独张" }}</span>
          <button
            v-if="item.group_id && item.group_size > 1"
            class="done-card-reopen"
            type="button"
            :disabled="Boolean(reopeningGroupId)"
            @click="emit('reopen', item.group_id)"
          >
            {{ reopeningGroupId === item.group_id ? "打开中" : "重选" }}
          </button>
        </article>
      </div>
    </div>
  </section>
</template>

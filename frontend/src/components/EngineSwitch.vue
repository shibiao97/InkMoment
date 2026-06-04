<script setup>
defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
});

const model = defineModel({ type: String, required: true });

const engines = [
  {
    id: "fast",
    title: "轻量快选",
    description: "本地基础评分 · 无模型缓存 · 适合快速整理大量照片",
  },
  {
    id: "expert",
    title: "质感优选",
    description: "本地多维评分 · 支持资源缓存 · 适合更严格的批量筛选",
  },
  {
    id: "tycoon",
    title: "云端精评",
    description: "远程视觉评审 · 需要 API Key · 适合少量精选照片",
  },
];
</script>

<template>
  <div class="engine-switch" role="radiogroup" aria-label="筛选方案">
    <button
      v-for="engine in engines"
      :key="engine.id"
      type="button"
      class="engine-opt"
      :class="{ 'is-active': model === engine.id, 'is-disabled': disabled || engine.disabled }"
      :disabled="disabled || engine.disabled"
      @click="model = engine.id"
    >
      <span class="engine-title">{{ engine.title }}</span>
      <span class="engine-desc">{{ engine.description }}</span>
    </button>
  </div>
</template>

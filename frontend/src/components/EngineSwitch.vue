<script setup>
const model = defineModel({ type: String, required: true });

const engines = [
  {
    id: "fast",
    title: "极速模式",
    description: "本地 CV · 无模型下载 · 适合先快速整理大量照片",
  },
  {
    id: "expert",
    title: "专家模式",
    description: "本地模型评分 · 自动下载缓存 · 适合更严格的批量筛选",
  },
  {
    id: "tycoon",
    title: "土豪模式",
    description: "视觉大模型判定 · 需要 API Key · 适合少量精修图",
  },
];
</script>

<template>
  <div class="engine-switch" role="radiogroup" aria-label="算法模式">
    <button
      v-for="engine in engines"
      :key="engine.id"
      type="button"
      class="engine-opt"
      :class="{ 'is-active': model === engine.id, 'is-disabled': engine.disabled }"
      :disabled="engine.disabled"
      @click="model = engine.id"
    >
      <span class="engine-title">{{ engine.title }}</span>
      <span class="engine-desc">{{ engine.description }}</span>
    </button>
  </div>
</template>

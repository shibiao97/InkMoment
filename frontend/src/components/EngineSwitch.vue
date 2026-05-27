<script setup>
const model = defineModel({ type: String, required: true });

const engines = [
  {
    id: "fast",
    title: "极速模式",
    description: "本地传统 CV · 多 hash + HSV + ORB 几何验证 · 零模型依赖",
  },
  {
    id: "expert",
    title: "专家模式",
    description: "DINOv2 + NIMA / MUSIQ / CLIP-IQA+ 三模型联合 · 人脸识别拒片",
  },
  {
    id: "tycoon",
    title: "土豪模式 ¥",
    description: "兼容 OpenAI 协议的大模型直接判定 · 适合少量高价值精修筛选",
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

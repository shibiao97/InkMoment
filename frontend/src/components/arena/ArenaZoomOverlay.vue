<script setup>
import { imageUrl } from "../../api/http";

defineProps({
  target: {
    type: String,
    required: true,
  },
  path: {
    type: String,
    required: true,
  },
  name: {
    type: String,
    required: true,
  },
  scale: {
    type: Number,
    required: true,
  },
});

const emit = defineEmits(["close", "set-scale"]);
</script>

<template>
  <div
    class="zoom-overlay"
    role="dialog"
    aria-modal="true"
    @click.self="emit('close')"
  >
    <div class="zoom-topbar">
      <div>
        <span>{{ target === "left" ? "左图" : "右图" }}</span>
        <strong>{{ name }}</strong>
      </div>
      <div class="zoom-actions">
        <button class="btn-ghost" type="button" @click="emit('set-scale', scale - 0.5)">缩小</button>
        <button class="btn-ghost" type="button" @click="emit('set-scale', 1)">{{ scale.toFixed(1) }}×</button>
        <button class="btn-ghost" type="button" @click="emit('set-scale', scale + 0.5)">放大</button>
        <button class="btn-primary" type="button" @click="emit('close')">关闭</button>
      </div>
    </div>
    <div class="zoom-stage">
      <img
        :src="imageUrl(path, 1800)"
        :alt="name"
        :style="{ transform: `scale(${scale})` }"
      >
    </div>
  </div>
</template>

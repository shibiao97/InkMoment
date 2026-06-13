<script setup>
defineProps({
  bootMessage: {
    type: String,
    default: "正在启动本地服务...",
  },
});
</script>

<template>
  <main class="app-shell app-boot-shell">
    <div class="app-boot-panel">
      <p class="eyebrow">InkMoment</p>
      <h1>{{ bootMessage }}</h1>
    </div>
  </main>
</template>

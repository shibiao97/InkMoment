<script setup>
defineProps({
  title: {
    type: String,
    default: "正在处理",
  },
  description: {
    type: String,
    default: "",
  },
});
</script>

<template>
  <section class="loading-state">
    <div class="progress-bar indeterminate">
      <div class="progress-fill"></div>
    </div>
    <strong>{{ title }}</strong>
    <p v-if="description">{{ description }}</p>
  </section>
</template>

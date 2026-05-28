<script setup>
defineProps({
  title: {
    type: String,
    default: "操作失败",
  },
  message: {
    type: String,
    default: "",
  },
});
</script>

<template>
  <section v-if="message" class="error-panel">
    <strong>{{ title }}</strong>
    <p>{{ message }}</p>
  </section>
</template>

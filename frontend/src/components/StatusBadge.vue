<script setup>
defineProps({
  label: {
    type: String,
    default: "引擎就绪",
  },
  state: {
    type: String,
    default: "idle",
  },
});
</script>

<template>
  <div class="status-badge" :class="`is-${state}`">
    <span class="status-dot"></span>
    <span>{{ label }}</span>
  </div>
</template>

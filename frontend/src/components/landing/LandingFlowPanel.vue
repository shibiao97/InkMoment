<script setup>
defineProps({
  items: {
    type: Array,
    required: true,
  },
});
</script>

<template>
  <section class="flow-panel" aria-label="启动状态">
    <div
      v-for="item in items"
      :key="item.id"
      class="flow-item"
      :class="`is-${item.state}`"
    >
      <span>{{ item.label }}</span>
      <strong>{{ item.value }}</strong>
    </div>
  </section>
</template>

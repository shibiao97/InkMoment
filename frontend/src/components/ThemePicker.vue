<script setup>
defineProps({
  themes: {
    type: Array,
    required: true,
  },
});

const model = defineModel({ type: String, required: true });
</script>

<template>
  <label class="theme-picker">
    <span>风格</span>
    <select v-model="model" aria-label="选择页面风格">
      <option v-for="item in themes" :key="item.id" :value="item.id">
        {{ item.label }}
      </option>
    </select>
  </label>
</template>

<script setup>
defineProps({
  status: {
    type: Object,
    default: null,
  },
  group: {
    type: Object,
    default: null,
  },
  overallPercent: {
    type: Number,
    required: true,
  },
  groupPercent: {
    type: Number,
    required: true,
  },
});
</script>

<template>
  <section class="arena-progress">
    <div>
      <span>总进度</span>
      <strong>{{ status?.finished_multi_groups || 0 }} / {{ status?.multi_groups || 0 }} 组</strong>
    </div>
    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: `${overallPercent}%` }"></div>
    </div>
    <div>
      <span>当前组</span>
      <strong>{{ group?.decided || 0 }} / {{ group?.total_images || 0 }} 已决</strong>
    </div>
    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: `${groupPercent}%` }"></div>
    </div>
  </section>
</template>

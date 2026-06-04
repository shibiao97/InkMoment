<script setup>
defineProps({
  activeStep: {
    type: String,
    required: true,
  },
  summaryLabel: {
    type: String,
    default: "任务摘要",
  },
  summaryValue: {
    type: String,
    default: "未开始",
  },
  summaryDetail: {
    type: String,
    default: "",
  },
});

const steps = [
  { id: "landing", label: "导入配置" },
  { id: "processing", label: "分析处理" },
  { id: "prescreen", label: "初筛复核" },
  { id: "preview", label: "分组预览" },
  { id: "arena", label: "人工选片" },
  { id: "done", label: "最终导出" },
];
</script>

<template>
  <aside class="studio-sidebar">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true"></span>
      <div>
        <span class="brand-name">影刻</span>
        <span class="site-tag">本地运行 · 不上传</span>
      </div>
    </div>

    <nav class="studio-nav" aria-label="工作流">
      <span
        v-for="step in steps"
        :key="step.id"
        :class="{ active: step.id === activeStep }"
      >
        {{ step.label }}
      </span>
    </nav>

    <div class="studio-sidebar-foot">
      <span>{{ summaryLabel }}</span>
      <strong>{{ summaryValue }}</strong>
      <small v-if="summaryDetail">{{ summaryDetail }}</small>
    </div>
  </aside>
</template>

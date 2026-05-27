<script setup>
defineProps({
  nextStep: {
    type: Object,
    required: true,
  },
  status: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["refresh", "back-home"]);
</script>

<template>
  <section class="next-step-panel">
    <div>
      <span class="step-kind">{{ nextStep.kind }}</span>
      <h2>{{ loading ? "正在判断下一步..." : nextStep.title }}</h2>
      <p>{{ error || nextStep.description }}</p>
    </div>

    <div v-if="status?.ready" class="next-step-stats">
      <div>
        <strong>{{ status.image_count?.toLocaleString?.() || 0 }}</strong>
        <span>照片</span>
      </div>
      <div>
        <strong>{{ status.total_groups?.toLocaleString?.() || 0 }}</strong>
        <span>分组</span>
      </div>
      <div>
        <strong>{{ status.prescreen_pending_count?.toLocaleString?.() || 0 }}</strong>
        <span>待复核</span>
      </div>
    </div>

    <div class="next-step-actions">
      <button class="btn-ghost" type="button" @click="emit('refresh')">刷新状态</button>
      <button class="btn-primary" type="button" @click="emit('back-home')">
        {{ nextStep.kind === "home" ? "回首页" : "暂回首页" }}
      </button>
    </div>
  </section>
</template>

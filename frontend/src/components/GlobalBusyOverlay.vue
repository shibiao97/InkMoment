<script setup>
defineProps({
  state: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(["cancel"]);
</script>

<template>
  <Teleport to="body">
    <div v-if="state" class="global-busy-overlay" role="status" aria-live="polite">
      <section class="global-busy-panel">
        <div class="global-busy-main">
          <span class="wait-spinner" aria-hidden="true"></span>
          <div>
            <p class="eyebrow">{{ state.status || "处理中" }}</p>
            <h2>{{ state.title || "正在处理" }}</h2>
            <p>{{ state.message || "请稍等，完成后会自动继续。" }}</p>
          </div>
        </div>
        <div class="global-busy-progress">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: `${Math.max(8, Math.min(100, state.progress || 0))}%` }"></div>
          </div>
          <span>{{ Math.round(Math.max(0, Math.min(100, state.progress || 0))) }}%</span>
        </div>
        <button
          v-if="state.cancelable"
          class="btn-ghost global-busy-cancel"
          type="button"
          @click="emit('cancel')"
        >
          {{ state.cancelText || "停止" }}
        </button>
      </section>
    </div>
  </Teleport>
</template>

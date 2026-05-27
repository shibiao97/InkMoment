<script setup>
import { computed } from "vue";

const props = defineProps({
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

const emit = defineEmits(["refresh", "back-home", "continue"]);

const canContinue = computed(() => {
  return ["prescreen", "confirm-prescreen", "preview", "arena", "done"].includes(props.nextStep.kind);
});

const primaryLabel = computed(() => {
  if (props.nextStep.kind === "prescreen") return "进入复核";
  if (props.nextStep.kind === "confirm-prescreen") return "进入确认";
  if (props.nextStep.kind === "preview") return "进入预览";
  if (props.nextStep.kind === "arena") return "继续选片";
  if (props.nextStep.kind === "done") return "查看结果";
  if (props.nextStep.kind === "home") return "回首页";
  return "暂回首页";
});

function handlePrimary() {
  if (canContinue.value) {
    emit("continue", props.nextStep.kind);
    return;
  }
  emit("back-home");
}
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
      <button class="btn-primary" type="button" :disabled="loading" @click="handlePrimary">
        {{ primaryLabel }}
      </button>
    </div>
  </section>
</template>

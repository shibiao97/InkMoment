<script setup>
import { computed, onMounted, watch } from "vue";
import NextStepPanel from "../components/NextStepPanel.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useJobPolling } from "../composables/useJobPolling";
import { useNextStep } from "../composables/useNextStep";

const props = defineProps({
  startedPayload: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(["back-home", "continue"]);

const {
  job,
  events,
  error,
  isCancelling,
  progressPercent,
  elapsedText,
  start,
  requestCancel,
} = useJobPolling();

const {
  status,
  nextStep,
  loading: loadingNextStep,
  error: nextStepError,
  refreshStatus,
} = useNextStep();

const statusLabel = computed(() => {
  if (job.value?.status === "done") return "分析完成";
  if (job.value?.status === "error") return "处理失败";
  if (job.value?.status === "cancelled") return "已中止";
  if (job.value?.status === "idle") return "引擎就绪";
  if (job.value?.total) {
    return `分析中 · ${job.value.done.toLocaleString()} / ${job.value.total.toLocaleString()}`;
  }
  return "分析中";
});

const statusState = computed(() => {
  if (job.value?.status === "error") return "error";
  if (job.value?.status === "done") return "done";
  if (job.value?.status === "cancelled" || job.value?.status === "idle") return "idle";
  return "busy";
});

const title = computed(() => {
  if (job.value?.status === "done") return "照片已经过目完毕";
  if (job.value?.status === "error") return "处理时遇到问题";
  if (job.value?.status === "cancelled") return "分析已中止";
  return "正在过目每张照片";
});

const progressText = computed(() => {
  const total = job.value?.total || 0;
  if (!total) return "扫描文件夹...";
  return `${job.value.done.toLocaleString()} / ${total.toLocaleString()} · ${progressPercent.value}%`;
});

const recentEvents = computed(() => events.value.slice(-10).reverse());
const rejectedCount = computed(() => job.value?.rejected_running || 0);
const skippedCount = computed(() => job.value?.skipped_count || 0);

async function cancel() {
  await requestCancel();
}

watch(
  () => job.value?.status,
  (value) => {
    if (value === "done") refreshStatus();
  },
);

onMounted(start);
</script>

<template>
  <main class="app-shell processing-shell">
    <StatusBadge :label="statusLabel" :state="statusState" />

    <header class="processing-topbar">
      <div>
        <p class="eyebrow">分析中</p>
        <h1>{{ title }}</h1>
        <p class="processing-folder">{{ job?.folder || startedPayload?.folder }}</p>
      </div>
      <div class="processing-actions">
        <button class="btn-ghost" type="button" @click="emit('back-home')">回首页</button>
        <button
          class="btn-ghost"
          type="button"
          :disabled="isCancelling || ['done', 'error', 'cancelled'].includes(job?.status)"
          @click="cancel"
        >
          {{ isCancelling ? "中止中" : "中止分析" }}
        </button>
      </div>
    </header>

    <section class="progress-panel">
      <div class="progress-head">
        <span>{{ job?.label || progressText }}</span>
        <span>{{ elapsedText ? `已用 ${elapsedText}` : "" }}</span>
      </div>
      <div class="progress-bar" :class="{ indeterminate: !job?.total }">
        <div class="progress-fill" :style="{ width: job?.total ? `${progressPercent}%` : '36%' }"></div>
      </div>
      <div class="progress-counters">
        <div>
          <strong>{{ job?.done?.toLocaleString?.() || 0 }}</strong>
          <span>已过目</span>
        </div>
        <div>
          <strong>{{ job?.total?.toLocaleString?.() || "—" }}</strong>
          <span>总张数</span>
        </div>
        <div>
          <strong>{{ rejectedCount.toLocaleString() }}</strong>
          <span>检出失败</span>
        </div>
        <div>
          <strong>{{ skippedCount.toLocaleString() }}</strong>
          <span>无法读取</span>
        </div>
      </div>
    </section>

    <section v-if="job?.error || error" class="error-panel">
      <strong>{{ job?.error_info?.title || "处理失败" }}</strong>
      <p>{{ job?.error_info?.message || job?.error || error }}</p>
    </section>

    <NextStepPanel
      v-if="job?.status === 'done'"
      :next-step="nextStep"
      :status="status"
      :loading="loadingNextStep"
      :error="nextStepError"
      @refresh="refreshStatus"
      @back-home="emit('back-home')"
      @continue="emit('continue', $event)"
    />

    <section class="event-panel">
      <div class="panel-head">
        <h2>实时记录</h2>
        <span>{{ events.length }} 条</span>
      </div>
      <div v-if="recentEvents.length" class="event-list">
        <article
          v-for="event in recentEvents"
          :key="event.seq"
          class="event-row"
          :class="{ reject: event.reject, fail: !event.ok && !event.reject }"
        >
          <span class="event-name">{{ event.name || "—" }}</span>
          <span class="event-verdict">{{ event.verdict || "—" }}</span>
          <span class="event-reason">{{ event.reason || event.engine || "" }}</span>
        </article>
      </div>
      <p v-else class="empty-events">等待后台返回第一条图片记录...</p>
    </section>

    <p class="start-note">
      Vue 迁移版已接入基础处理进度和初筛复核入口。分组预览、擂台页将在后续迭代接入。
    </p>
  </main>
</template>

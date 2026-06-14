<script setup>
import { computed, onMounted, watch } from "vue";
import ErrorPanel from "../components/ErrorPanel.vue";
import NextStepPanel from "../components/NextStepPanel.vue";
import ProcessingPhotoWall from "../components/ProcessingPhotoWall.vue";
import StatusBadge from "../components/StatusBadge.vue";
import WorkflowSidebar from "../components/WorkflowSidebar.vue";
import { useJobPolling } from "../composables/useJobPolling";
import { useNextStep } from "../composables/useNextStep";

defineProps({
  startedPayload: {
    type: Object,
    default: null,
  },
  returningHome: {
    type: Boolean,
    default: false,
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
const processingErrorTitle = computed(() => job.value?.error_info?.title || "处理失败");
const processingErrorMessage = computed(() => job.value?.error_info?.message || job.value?.error || error.value || "");

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
  <main class="app-shell studio-shell flow-workbench processing-shell">
    <WorkflowSidebar
      active-step="processing"
      summary-label="当前任务"
      :summary-value="statusLabel"
      :summary-detail="job?.folder || startedPayload?.folder || '等待照片文件夹'"
    />

    <section class="studio-main flow-main flow-main-stack">
      <StatusBadge :label="statusLabel" :state="statusState" />

      <header class="processing-topbar flow-hero">
        <div>
          <p class="eyebrow">分析处理</p>
          <h1>{{ title }}</h1>
          <p class="processing-folder">{{ job?.folder || startedPayload?.folder }}</p>
        </div>
      </header>

      <ErrorPanel :title="processingErrorTitle" :message="processingErrorMessage" />

      <section class="processing-workspace">
        <div class="processing-wall-column">
          <ProcessingPhotoWall :events="events" :status="job?.status || ''" :total="job?.total || 0" />

          <NextStepPanel
            v-if="job?.status === 'done'"
            :next-step="nextStep"
            :status="status"
            :loading="loadingNextStep"
            :error="nextStepError"
            :returning-home="returningHome"
            @refresh="refreshStatus"
            @back-home="emit('back-home')"
            @continue="emit('continue', $event)"
          />
        </div>
      </section>

      <p class="start-note">
        照片墙会跟随实时事件更新；进入分组阶段后会收拢展示，稍后进入下一步。
      </p>
    </section>

    <aside class="studio-inspector flow-inspector processing-inspector">
      <section class="inspector-card inspector-status-card">
        <p class="eyebrow">当前状态</p>
        <h2>{{ statusLabel }}</h2>
        <p>{{ job?.label || progressText }}</p>
      </section>

      <section class="inspector-card progress-panel compact-progress-panel">
        <div class="progress-head">
          <span>{{ progressText }}</span>
          <span>{{ elapsedText ? `已用 ${elapsedText}` : "" }}</span>
        </div>
        <div class="progress-bar" :class="{ indeterminate: !job?.total }">
          <div class="progress-fill" :style="{ width: job?.total ? `${progressPercent}%` : '36%' }"></div>
        </div>
      </section>

      <section class="inspector-card inspector-stat-grid">
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
      </section>

      <section class="inspector-card inspector-actions">
        <button class="btn-ghost" type="button" :disabled="returningHome" @click="emit('back-home')">
          {{ returningHome ? "返回中" : "回首页" }}
        </button>
        <button
          class="btn-ghost btn-danger"
          type="button"
          :disabled="isCancelling || ['done', 'error', 'cancelled'].includes(job?.status)"
          @click="cancel"
        >
          {{ isCancelling ? "中止中" : "中止分析" }}
        </button>
      </section>

      <section class="inspector-card event-panel processing-event-panel">
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
            <span v-if="event.signals?.length" class="event-signals">
              <span
                v-for="signal in event.signals"
                :key="`${event.seq}-${signal.kind}-${signal.label}`"
                class="event-signal"
                :class="`is-${signal.kind}`"
              >
                <b>{{ signal.label }}</b>
                {{ signal.value }}
              </span>
            </span>
          </article>
        </div>
        <p v-else class="empty-events">等待后台返回第一条图片记录...</p>
      </section>
    </aside>
  </main>
</template>

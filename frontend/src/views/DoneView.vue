<script setup>
import { computed, onMounted } from "vue";
import DoneWatermarkPanel from "../components/done/DoneWatermarkPanel.vue";
import DoneWinnersGrid from "../components/done/DoneWinnersGrid.vue";
import ErrorPanel from "../components/ErrorPanel.vue";
import LoadingState from "../components/LoadingState.vue";
import StatusBadge from "../components/StatusBadge.vue";
import WorkflowSidebar from "../components/WorkflowSidebar.vue";
import { useDoneResults } from "../composables/useDoneResults";
import { useWatermarkExport } from "../composables/useWatermarkExport";

defineProps({
  returningHome: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["back-home", "continue-arena", "job-started"]);

const {
  status,
  winners,
  skipped,
  sections,
  total,
  kept,
  rejected,
  subtitle,
  statusLabel,
  statusState,
  loading,
  opening,
  redoing,
  reopeningGroupId,
  error,
  load,
  openOutputFolder,
  reopenWinnerGroup,
  redoCurrentSession,
} = useDoneResults();
const watermark = useWatermarkExport();

const winnersPath = computed(() => status.value?.folder ? `${status.value.folder}/winners` : "");
const losersPath = computed(() => status.value?.folder ? `${status.value.folder}/losers` : "");
const hasUnfinished = computed(() => (status.value?.unfinished_groups || 0) > 0);
const canWatermark = computed(() => winners.value.length > 0 && !status.value?.dry_run);
const canRedo = computed(() => Boolean(status.value?.folder) && !loading.value && !redoing.value);

async function loadPage() {
  await load();
  if (canWatermark.value) {
    await watermark.initialize();
  }
}

async function reopenGroupFromWinner(groupId) {
  const reopened = await reopenWinnerGroup(groupId);
  if (reopened) {
    emit("continue-arena");
  }
}

async function redoCurrentFolder() {
  if (!status.value?.folder || redoing.value) return;
  const ok = window.confirm(
    `重做这个文件夹\n\n将清掉 ${status.value.folder}/winners 与 /losers 子目录、所有缓存与本次进度，并用同样设置重新分析。此操作不可撤销。`,
  );
  if (!ok) return;
  const payload = await redoCurrentSession();
  if (payload) {
    emit("job-started", payload);
  }
}

onMounted(loadPage);
</script>

<template>
  <main class="app-shell studio-shell flow-workbench done-shell-vue">
    <WorkflowSidebar
      active-step="done"
      summary-label="最终导出"
      :summary-value="`${kept.toLocaleString()} 张胜出`"
      :summary-detail="status?.folder || '等待结果'"
    />

    <section class="studio-main flow-main">
      <StatusBadge :label="statusLabel" :state="statusState" />

      <header class="done-topbar">
      <div>
        <p class="eyebrow">完成</p>
        <h1>这些是你留下的。</h1>
        <p class="done-subtitle">{{ subtitle }}</p>
      </div>
      <div class="done-actions">
        <button class="btn-ghost" type="button" :disabled="opening" @click="openOutputFolder">
          {{ opening ? "打开中" : "打开文件夹" }}
        </button>
        <button
          class="btn-ghost"
          type="button"
          :disabled="!canRedo || returningHome"
          @click="redoCurrentFolder"
        >
          {{ redoing ? "重做中" : "重做本次" }}
        </button>
        <button
          class="btn-primary"
          type="button"
          :disabled="!canWatermark || watermark.loadingTemplates.value || watermark.previewing.value || watermark.isRunning.value"
          @click="watermark.refreshPreview()"
        >
          水印预览
        </button>
        <button class="btn-ghost" type="button" :disabled="returningHome" @click="emit('back-home')">
          {{ returningHome ? "返回中" : "回首页" }}
        </button>
      </div>
    </header>

    <section class="done-hero-panel">
      <strong>{{ total.toLocaleString() }}</strong>
      <span>→</span>
      <strong class="accent">{{ kept.toLocaleString() }}</strong>
    </section>

    <section class="done-stats-grid">
      <div>
        <strong>{{ kept.toLocaleString() }}</strong>
        <span>胜出</span>
      </div>
      <div>
        <strong>{{ rejected.toLocaleString() }}</strong>
        <span>放手</span>
      </div>
      <div>
        <strong>{{ status?.multi_groups || 0 }}</strong>
        <span>连拍组</span>
      </div>
      <div>
        <strong>{{ skipped.length }}</strong>
        <span>无法读取</span>
      </div>
    </section>

    <ErrorPanel title="结果读取失败" :message="error" />

    <section class="done-paths-vue">
      <div>
        <span>胜出</span>
        <code>{{ winnersPath }}</code>
      </div>
      <div>
        <span>淘汰</span>
        <code>{{ losersPath }}</code>
      </div>
    </section>

    <section v-if="hasUnfinished" class="unfinished-notice-vue">
      <span>{{ status.unfinished_groups }} 组之前跳过了。</span>
      <button class="btn-primary" type="button" @click="emit('continue-arena')">回去处理</button>
    </section>

    <DoneWatermarkPanel :watermark="watermark" :can-watermark="canWatermark" />

    <LoadingState
      v-if="loading"
      title="正在读取完成结果"
      description="正在汇总胜出照片、跳过记录和水印状态。"
    />
    <section v-else-if="!winners.length" class="done-empty">
      暂时没有胜出的照片。
    </section>
    <DoneWinnersGrid
      v-else
      :winners="winners"
      :sections="sections"
      :reopening-group-id="reopeningGroupId"
      @reopen="reopenGroupFromWinner"
    />

    <details v-if="skipped.length" class="done-skipped">
      <summary>无法读取的照片（{{ skipped.length }}）</summary>
      <ul>
        <li v-for="item in skipped.slice(-50).reverse()" :key="`${item.path}-${item.reason}`">
          <span>{{ item.path.split(/[\\/]/).pop() }}</span>
          <code>{{ item.reason }}</code>
        </li>
      </ul>
      </details>
    </section>
  </main>
</template>

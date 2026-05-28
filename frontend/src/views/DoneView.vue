<script setup>
import { computed, onMounted } from "vue";
import { imageUrl } from "../api/http";
import ErrorPanel from "../components/ErrorPanel.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useDoneResults } from "../composables/useDoneResults";
import { useTheme } from "../composables/useTheme";
import { useWatermarkExport } from "../composables/useWatermarkExport";

defineProps({
  returningHome: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["back-home", "continue-arena"]);

const { theme } = useTheme();
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
  reopeningGroupId,
  error,
  load,
  openOutputFolder,
  reopenWinnerGroup,
} = useDoneResults();
const watermark = useWatermarkExport();

const winnersPath = computed(() => status.value?.folder ? `${status.value.folder}/winners` : "");
const losersPath = computed(() => status.value?.folder ? `${status.value.folder}/losers` : "");
const hasUnfinished = computed(() => (status.value?.unfinished_groups || 0) > 0);
const canWatermark = computed(() => winners.value.length > 0 && !status.value?.dry_run);
const watermarkPreviewSrc = computed(() => {
  return watermark.preview.value?.image_b64
    ? `data:image/jpeg;base64,${watermark.preview.value.image_b64}`
    : "";
});
const watermarkStatusText = computed(() => {
  const job = watermark.job.value || {};
  if (job.status === "running") {
    return `处理中 ${job.done || 0}/${job.total || 0} · ${job.current || ""}`;
  }
  if (job.status === "done") {
    return `完成 · 成功 ${job.ok || 0}/${job.total || 0}${job.failed_count ? `，失败 ${job.failed_count}` : ""}`;
  }
  if (job.status === "cancelled") {
    return `已中止 · 完成 ${job.ok || 0}/${job.total || 0}`;
  }
  if (job.status === "error") {
    return `出错：${job.error || "未知错误"}`;
  }
  return "选择样式后可预览并批量导出。";
});
const watermarkExifRows = computed(() => {
  const exif = watermark.preview.value?.exif || {};
  return [
    ["机身", [exif.make, exif.model].filter(Boolean).join(" ")],
    ["镜头", exif.lens],
    ["焦距", exif.focal_length],
    ["光圈", exif.f_number],
    ["快门", exif.exposure],
    ["ISO", exif.iso],
    ["时间", exif.datetime],
  ];
});

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

onMounted(loadPage);
</script>

<template>
  <main class="app-shell done-shell-vue" :style="{ '--accent': theme.accent }">
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

    <section class="watermark-panel-vue" :class="{ disabled: !canWatermark }">
      <div class="watermark-head-vue">
        <div>
          <p class="eyebrow">相机水印</p>
          <h2>给胜出照片批量导出水印版</h2>
        </div>
        <div class="watermark-actions-vue">
          <button
            class="btn-ghost"
            type="button"
            :disabled="!canWatermark || watermark.loadingTemplates.value || watermark.previewing.value || watermark.isRunning.value"
            @click="watermark.nextPreview(-1)"
          >
            上一张
          </button>
          <button
            class="btn-ghost"
            type="button"
            :disabled="!canWatermark || watermark.loadingTemplates.value || watermark.previewing.value || watermark.isRunning.value"
            @click="watermark.nextPreview(1)"
          >
            下一张
          </button>
          <button
            v-if="watermark.isRunning.value"
            class="btn-ghost"
            type="button"
            :disabled="watermark.cancelling.value"
            @click="watermark.cancelExport"
          >
            {{ watermark.cancelling.value ? "中止中" : "中止" }}
          </button>
          <button
            v-else-if="watermark.hasOutput.value"
            class="btn-primary"
            type="button"
            :disabled="watermark.opening.value"
            @click="watermark.openOutputFolder"
          >
            {{ watermark.opening.value ? "打开中" : "打开水印目录" }}
          </button>
          <button
            class="btn-primary"
            type="button"
            :disabled="!canWatermark || watermark.loadingTemplates.value || watermark.starting.value || watermark.previewing.value || watermark.isRunning.value"
            @click="watermark.startExport"
          >
            {{ watermark.starting.value ? "启动中" : "开始导出" }}
          </button>
        </div>
      </div>

      <p v-if="!canWatermark" class="watermark-hint-vue">
        当前没有可导出的胜出照片，或处于试运行模式。
      </p>

      <div v-else class="watermark-body-vue">
        <aside class="watermark-options-vue">
          <div class="watermark-template-grid-vue">
            <button
              v-for="template in watermark.templates.value"
              :key="template.id"
              class="watermark-template-vue"
              :class="{ active: template.id === watermark.selectedTemplate.value }"
              type="button"
              :disabled="watermark.loadingTemplates.value || watermark.previewing.value || watermark.isRunning.value"
              @click="watermark.selectTemplate(template.id)"
            >
              <strong>{{ template.name }}</strong>
              <span>{{ template.desc }}</span>
            </button>
          </div>

          <div class="watermark-exif-vue">
            <span>预览照片 EXIF</span>
            <dl>
              <template v-for="[label, value] in watermarkExifRows" :key="label">
                <dt>{{ label }}</dt>
                <dd :class="{ empty: !value }">{{ value || "未读到" }}</dd>
              </template>
            </dl>
          </div>
        </aside>

        <section class="watermark-preview-vue">
          <div class="watermark-preview-head-vue">
            <strong>
              {{ watermark.preview.value?.source_name ? `预览 · ${watermark.preview.value.source_name}` : "预览" }}
            </strong>
            <span>
              {{ watermark.totalWinners.value ? `${watermark.previewIndex.value + 1} / ${watermark.totalWinners.value}` : "— / —" }}
            </span>
          </div>
          <div class="watermark-preview-frame-vue">
            <span v-if="watermark.loadingTemplates.value">加载样式中...</span>
            <span v-else-if="watermark.previewing.value">渲染中...</span>
            <img v-else-if="watermarkPreviewSrc" :src="watermarkPreviewSrc" alt="水印预览">
            <span v-else>暂无预览</span>
          </div>
          <div class="watermark-progress-vue">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: `${watermark.progressPercent.value}%` }"></div>
            </div>
            <p>{{ watermarkStatusText }}</p>
            <p v-if="watermark.error.value" class="watermark-error-vue">{{ watermark.error.value }}</p>
          </div>
        </section>
      </div>
    </section>

    <section v-if="loading" class="done-empty">
      正在读取完成结果...
    </section>
    <section v-else-if="!winners.length" class="done-empty">
      暂时没有胜出的照片。
    </section>
    <section v-else class="done-winners">
      <div class="winners-section-head">
        <h2 class="winners-section-title">这次留下的</h2>
        <span class="winners-count">{{ winners.length }} 张</span>
      </div>

      <div v-for="section in sections" :key="section.title" class="done-section">
        <div class="album-chapter">
          <span class="album-chapter-name">{{ section.title }}</span>
          <span class="album-chapter-meta">{{ section.items.length }} 张</span>
        </div>
        <div class="done-grid">
          <article v-for="item in section.items" :key="item.path" class="done-card">
            <img :src="imageUrl(item.path, 520)" :alt="item.name" loading="lazy">
            <span>{{ item.group_size > 1 ? `从 ${item.group_size} 张里` : "独张" }}</span>
            <button
              v-if="item.group_id && item.group_size > 1"
              class="done-card-reopen"
              type="button"
              :disabled="Boolean(reopeningGroupId)"
              @click="reopenGroupFromWinner(item.group_id)"
            >
              {{ reopeningGroupId === item.group_id ? "打开中" : "重选" }}
            </button>
          </article>
        </div>
      </div>
    </section>

    <details v-if="skipped.length" class="done-skipped">
      <summary>无法读取的照片（{{ skipped.length }}）</summary>
      <ul>
        <li v-for="item in skipped.slice(-50).reverse()" :key="`${item.path}-${item.reason}`">
          <span>{{ item.path.split(/[\\/]/).pop() }}</span>
          <code>{{ item.reason }}</code>
        </li>
      </ul>
    </details>
  </main>
</template>

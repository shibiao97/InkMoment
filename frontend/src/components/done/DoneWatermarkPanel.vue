<script setup>
import { computed } from "vue";

const props = defineProps({
  watermark: {
    type: Object,
    required: true,
  },
  canWatermark: {
    type: Boolean,
    required: true,
  },
});

const watermarkPreviewSrc = computed(() => {
  return props.watermark.preview.value?.image_b64
    ? `data:image/jpeg;base64,${props.watermark.preview.value.image_b64}`
    : "";
});
const watermarkStatusText = computed(() => {
  const job = props.watermark.job.value || {};
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
  const exif = props.watermark.preview.value?.exif || {};
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
</script>

<template>
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
      </section>

      <aside class="watermark-details-vue">
        <div class="watermark-exif-vue">
          <span>预览照片 EXIF</span>
          <dl>
            <template v-for="[label, value] in watermarkExifRows" :key="label">
              <dt>{{ label }}</dt>
              <dd :class="{ empty: !value }">{{ value || "未读到" }}</dd>
            </template>
          </dl>
        </div>

        <div class="watermark-progress-vue">
          <span>导出状态</span>
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: `${watermark.progressPercent.value}%` }"></div>
          </div>
          <p>{{ watermarkStatusText }}</p>
          <p v-if="watermark.error.value" class="watermark-error-vue">{{ watermark.error.value }}</p>
        </div>
      </aside>
    </div>
  </section>
</template>

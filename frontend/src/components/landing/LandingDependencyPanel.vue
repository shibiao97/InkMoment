<script setup>
defineProps({
  canPickFolder: {
    type: Boolean,
    required: true,
  },
  isChecking: {
    type: Boolean,
    required: true,
  },
  isDownloading: {
    type: Boolean,
    required: true,
  },
  report: {
    type: Object,
    default: null,
  },
  title: {
    type: String,
    required: true,
  },
  missingCount: {
    type: Number,
    required: true,
  },
  downloadableCount: {
    type: Number,
    required: true,
  },
  manualCount: {
    type: Number,
    required: true,
  },
  hasPendingStart: {
    type: Boolean,
    required: true,
  },
  actionHint: {
    type: String,
    required: true,
  },
  downloadStatus: {
    type: Object,
    default: null,
  },
  message: {
    type: String,
    default: "",
  },
  error: {
    type: String,
    default: "",
  },
  downloadStatusText: {
    type: String,
    required: true,
  },
  canDownload: {
    type: Boolean,
    required: true,
  },
  downloadButtonText: {
    type: String,
    required: true,
  },
  reportText: {
    type: String,
    default: "",
  },
  copied: {
    type: Boolean,
    required: true,
  },
});

const emit = defineEmits(["check", "pick-folder", "recheck", "download", "copy"]);

const downloadDir = defineModel("downloadDir", { type: String, required: true });
</script>

<template>
  <section class="dependency-panel">
    <div class="dependency-head">
      <div>
        <div class="option-label">运行资源</div>
        <h2>{{ title }}</h2>
      </div>
      <button
        class="btn-primary"
        type="button"
        :disabled="isChecking || isDownloading"
        @click="emit('check')"
      >
        {{ isChecking ? "检查中" : "检查当前模式" }}
      </button>
    </div>

    <label class="dependency-dir">
      <span>模型 / 资源下载位置</span>
      <input
        v-model="downloadDir"
        type="text"
        placeholder="留空则使用默认资源目录"
        spellcheck="false"
      >
    </label>

    <div v-if="report" class="dependency-summary">
      <div>
        <span>缺失项</span>
        <strong>{{ missingCount }}</strong>
      </div>
      <div>
        <span>可下载</span>
        <strong>{{ downloadableCount }}</strong>
      </div>
      <div>
        <span>需手动处理</span>
        <strong>{{ manualCount }}</strong>
      </div>
    </div>

    <ul v-if="report?.missing?.length" class="dependency-list">
      <li v-for="item in report.missing" :key="item.id">
        <div>
          <strong>{{ item.label }}</strong>
          <span>{{ item.detail }}</span>
          <small v-if="item.hint">{{ item.hint }}</small>
        </div>
        <em :class="{ 'is-downloadable': item.downloadable }">
          {{ item.downloadable ? "可自动下载" : "需手动处理" }}
        </em>
      </li>
    </ul>

    <p v-else-if="report?.ok" class="start-note">
      当前模式运行资源已就绪。
    </p>

    <p v-if="report?.manual_required" class="dependency-blocker">
      {{ hasPendingStart ? "存在无法自动下载的依赖，需要处理后再点击“检查并继续”。" : "存在无法自动下载的依赖，需要处理后重新检查。" }}
    </p>
    <p v-if="report" class="dependency-hint">
      {{ actionHint }}
    </p>

    <div v-if="isDownloading || downloadStatus" class="dependency-progress">
      <span :class="`is-${downloadStatus?.status || 'running'}`"></span>
      <div>
        <strong>{{ downloadStatusText }}</strong>
        <small>{{ downloadStatus?.message || message || "正在处理下载任务" }}</small>
      </div>
    </div>

    <div class="dependency-actions">
      <button
        v-if="canPickFolder"
        class="btn-ghost"
        type="button"
        :disabled="isDownloading"
        @click="emit('pick-folder')"
      >
        指定下载位置
      </button>
      <button
        v-if="hasPendingStart"
        class="btn-ghost"
        type="button"
        :disabled="isChecking || isDownloading"
        @click="emit('recheck')"
      >
        {{ isChecking ? "检查中" : "检查并继续" }}
      </button>
      <button
        class="btn-primary"
        type="button"
        :disabled="!canDownload || isDownloading"
        @click="emit('download')"
      >
        {{ downloadButtonText }}
      </button>
      <button
        class="btn-ghost"
        type="button"
        :disabled="!reportText"
        @click="emit('copy')"
      >
        {{ copied ? "已复制" : "复制检查结果" }}
      </button>
    </div>

    <p v-if="message" class="start-note">{{ message }}</p>
    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

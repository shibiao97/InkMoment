<script setup>
import { computed, ref } from "vue";

const props = defineProps({
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
  manualCommands: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["check", "recheck", "download", "copy"]);

const manualDialogOpen = ref(false);
const manualItems = computed(() => props.report?.missing?.filter((item) => !item.downloadable) || []);
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
        <span v-if="isChecking" class="btn-spinner" aria-hidden="true"></span>
        {{ isChecking ? "检查中" : "检查当前模式" }}
      </button>
    </div>

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
        <button
          v-if="!item.downloadable"
          class="dependency-chip"
          type="button"
          @click="manualDialogOpen = true"
        >
          处理方式
        </button>
        <em v-else class="is-downloadable">可自动下载</em>
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
      <span
        :class="[
          `is-${downloadStatus?.status || 'running'}`,
          { 'is-spinning': !downloadStatus?.status || ['pending', 'running'].includes(downloadStatus.status) },
        ]"
      ></span>
      <div>
        <strong>{{ downloadStatusText }}</strong>
        <small>{{ downloadStatus?.message || message || "正在检查并处理资源" }}</small>
      </div>
    </div>

    <div class="dependency-actions">
      <button
        v-if="hasPendingStart"
        class="btn-ghost"
        type="button"
        :disabled="isChecking || isDownloading"
        @click="emit('recheck')"
      >
        <span v-if="isChecking" class="btn-spinner" aria-hidden="true"></span>
        {{ isChecking ? "检查中" : "检查并继续" }}
      </button>
      <button
        class="btn-primary"
        type="button"
        :disabled="!canDownload || isDownloading"
        @click="emit('download')"
      >
        <span v-if="isDownloading" class="btn-spinner" aria-hidden="true"></span>
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

    <Teleport to="body">
      <div v-if="manualDialogOpen" class="dependency-modal-backdrop" @click.self="manualDialogOpen = false">
        <section class="dependency-modal" role="dialog" aria-modal="true" aria-labelledby="dependency-modal-title">
          <header>
            <div>
              <span class="option-label">手动处理</span>
              <h2 id="dependency-modal-title">推荐下载 / 安装命令</h2>
            </div>
            <button class="btn-ghost" type="button" @click="manualDialogOpen = false">关闭</button>
          </header>

          <ul v-if="manualItems.length" class="dependency-modal-list">
            <li v-for="item in manualItems" :key="item.id">
              <strong>{{ item.label }}</strong>
              <span>{{ item.detail }}</span>
              <small v-if="item.hint">{{ item.hint }}</small>
            </li>
          </ul>

          <div v-if="manualCommands.length" class="dependency-command">
            <span>推荐手动下载 / 安装命令</span>
            <code v-for="command in manualCommands" :key="command">{{ command }}</code>
          </div>
          <p v-else class="dependency-hint">当前缺失项没有可推荐命令，请打开日志复制详细错误后重新打包。</p>
        </section>
      </div>
    </Teleport>
  </section>
</template>

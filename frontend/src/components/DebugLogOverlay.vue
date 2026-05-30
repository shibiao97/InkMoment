<script setup>
defineProps({
  open: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: "",
  },
  logText: {
    type: String,
    default: "",
  },
  copied: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["open", "close", "refresh", "copy"]);
</script>

<template>
  <button
    class="debug-log-button"
    type="button"
    title="查看后台运行日志"
    @click="emit('open')"
  >
    日志
  </button>

  <div v-if="open" class="debug-log-overlay" role="dialog" aria-modal="true">
    <section class="debug-log-panel">
      <header class="debug-log-head">
        <div>
          <p class="eyebrow">Backend</p>
          <h2>运行日志</h2>
        </div>
        <button class="btn-ghost" type="button" @click="emit('close')">关闭</button>
      </header>
      <div class="debug-log-actions">
        <button class="btn-ghost" type="button" :disabled="loading" @click="emit('refresh')">
          {{ loading ? "刷新中..." : "刷新" }}
        </button>
        <button class="btn-primary" type="button" :disabled="!logText" @click="emit('copy')">
          {{ copied ? "已复制" : "复制日志" }}
        </button>
      </div>
      <p v-if="error" class="debug-log-error">{{ error }}</p>
      <pre class="debug-log-output">{{ logText || "暂无日志" }}</pre>
    </section>
  </div>
</template>

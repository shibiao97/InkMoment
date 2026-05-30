<script setup>
defineProps({
  status: {
    type: Object,
    default: null,
  },
  models: {
    type: Array,
    required: true,
  },
  concurrency: {
    type: Object,
    default: null,
  },
  diagnostics: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    required: true,
  },
  checkingModels: {
    type: Boolean,
    required: true,
  },
  saving: {
    type: Boolean,
    required: true,
  },
  configured: {
    type: Boolean,
    required: true,
  },
  message: {
    type: String,
    default: "",
  },
  error: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["refresh", "save", "clear", "refresh-models"]);

const baseUrl = defineModel("baseUrl", { type: String, required: true });
const apiKey = defineModel("apiKey", { type: String, required: true });
const selectedModel = defineModel("selectedModel", { type: String, required: true });
</script>

<template>
  <section class="llm-panel">
    <div class="llm-head">
      <div>
        <div class="option-label">模型服务</div>
        <h2>土豪模式配置</h2>
      </div>
      <button class="btn-ghost" type="button" :disabled="loading" @click="emit('refresh')">
        {{ loading ? "检查中" : "刷新状态" }}
      </button>
    </div>

    <div class="llm-status-grid">
      <div>
        <span>Key</span>
        <strong>{{ configured ? status?.masked || "已配置" : "未配置" }}</strong>
      </div>
      <div>
        <span>并发</span>
        <strong>{{ concurrency?.limit ?? "—" }}</strong>
      </div>
      <div>
        <span>可用模型</span>
        <strong>{{ models.length }}</strong>
      </div>
    </div>

    <div class="llm-config-grid">
      <label>
        <span>服务地址</span>
        <input
          v-model="baseUrl"
          type="url"
          placeholder="https://api.openai.com/v1"
          spellcheck="false"
        >
      </label>
      <label>
        <span>API Key</span>
        <input
          v-model="apiKey"
          type="password"
          placeholder="粘贴新的 Key 后保存"
          autocomplete="off"
          spellcheck="false"
        >
      </label>
    </div>

    <div class="llm-actions">
      <button class="btn-primary" type="button" :disabled="saving || !apiKey.trim()" @click="emit('save')">
        {{ saving ? "保存中" : "保存并验证" }}
      </button>
      <button class="btn-ghost" type="button" :disabled="checkingModels || !configured" @click="emit('refresh-models')">
        {{ checkingModels ? "刷新中" : "刷新模型" }}
      </button>
      <button class="btn-ghost" type="button" :disabled="saving || !configured" @click="emit('clear')">
        清除 Key
      </button>
    </div>

    <label class="llm-model-select">
      <span>视觉模型</span>
      <select v-model="selectedModel" :disabled="!models.length">
        <option value="">请选择模型</option>
        <option v-for="model in models" :key="model.id" :value="model.id">
          {{ model.label || model.id }}
        </option>
      </select>
    </label>

    <p v-if="status?.base_url" class="llm-note">
      当前地址：{{ status.base_url }} · 来源：{{ status.base_url_source || "default" }}
    </p>
    <p v-if="diagnostics?.llm" class="llm-note">
      诊断：{{ diagnostics.llm.configured ? "已读取到 Key" : "未读取到 Key" }}
    </p>
    <p v-if="message" class="start-note">{{ message }}</p>
    <p v-if="error" class="form-error">{{ error }}</p>
  </section>
</template>

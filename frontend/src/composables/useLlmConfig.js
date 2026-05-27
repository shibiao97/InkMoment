import { computed, onMounted, ref } from "vue";
import {
  clearArkKey,
  getArkKeyStatus,
  getDiagnostics,
  getLlmConcurrency,
  getLlmModels,
  saveArkKey,
} from "../api/inkmoment";

export function useLlmConfig() {
  const status = ref(null);
  const models = ref([]);
  const unavailable = ref([]);
  const selectedModel = ref("");
  const concurrency = ref(null);
  const diagnostics = ref(null);
  const baseUrlInput = ref("");
  const keyInput = ref("");
  const loading = ref(false);
  const checkingModels = ref(false);
  const saving = ref(false);
  const error = ref("");
  const message = ref("");

  const configured = computed(() => Boolean(status.value?.configured));
  const modelReady = computed(() => configured.value && Boolean(selectedModel.value));

  async function loadStatus() {
    const payload = await getArkKeyStatus();
    status.value = payload;
    baseUrlInput.value = payload.base_url || payload.default_base_url || "";
    return payload;
  }

  async function loadModels(force = false) {
    checkingModels.value = true;
    try {
      const payload = await getLlmModels(force);
      models.value = payload.models || [];
      unavailable.value = payload.unavailable || [];
      if (!models.value.includes(selectedModel.value)) {
        selectedModel.value = models.value[0] || "";
      }
      return payload;
    } finally {
      checkingModels.value = false;
    }
  }

  async function loadSupplementalStatus() {
    const [limitPayload, diagnosticsPayload] = await Promise.allSettled([
      getLlmConcurrency(),
      getDiagnostics(),
    ]);
    concurrency.value = limitPayload.status === "fulfilled" ? limitPayload.value : null;
    diagnostics.value = diagnosticsPayload.status === "fulfilled" ? diagnosticsPayload.value : null;
  }

  async function refresh({ forceModels = false } = {}) {
    loading.value = true;
    error.value = "";
    message.value = "";
    try {
      await loadStatus();
      await loadSupplementalStatus();
      if (configured.value) {
        await loadModels(forceModels);
      } else {
        models.value = [];
        unavailable.value = [];
        selectedModel.value = "";
      }
    } catch (err) {
      error.value = err.message || "模型服务状态读取失败";
    } finally {
      loading.value = false;
    }
  }

  async function saveConfig() {
    saving.value = true;
    error.value = "";
    message.value = "";
    try {
      const payload = await saveArkKey({
        key: keyInput.value,
        base_url: baseUrlInput.value,
      });
      keyInput.value = "";
      await refresh({ forceModels: true });
      message.value = `配置已保存，可见模型 ${payload.model_count ?? 0} 个`;
    } catch (err) {
      error.value = err.message || "模型服务配置保存失败";
    } finally {
      saving.value = false;
    }
  }

  async function clearConfig() {
    saving.value = true;
    error.value = "";
    message.value = "";
    try {
      await clearArkKey();
      keyInput.value = "";
      await refresh();
      message.value = "已清除本地 API Key";
    } catch (err) {
      error.value = err.message || "清除配置失败";
    } finally {
      saving.value = false;
    }
  }

  async function refreshModels() {
    error.value = "";
    message.value = "";
    try {
      await loadModels(true);
      message.value = `已刷新模型列表，可用 ${models.value.length} 个`;
    } catch (err) {
      error.value = err.message || "模型列表刷新失败";
    }
  }

  onMounted(() => {
    refresh();
  });

  return {
    status,
    models,
    unavailable,
    selectedModel,
    concurrency,
    diagnostics,
    baseUrlInput,
    keyInput,
    loading,
    checkingModels,
    saving,
    error,
    message,
    configured,
    modelReady,
    refresh,
    saveConfig,
    clearConfig,
    refreshModels,
  };
}

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
  let modelsRequest = null;

  const configured = computed(() => Boolean(status.value?.configured));
  const modelReady = computed(() => configured.value && Boolean(selectedModel.value));

  async function loadStatus() {
    const payload = await getArkKeyStatus();
    status.value = payload;
    baseUrlInput.value = payload.base_url || payload.default_base_url || "";
    return payload;
  }

  async function loadModels(force = false) {
    if (modelsRequest) {
      return modelsRequest;
    }
    checkingModels.value = true;
    modelsRequest = (async () => {
      const payload = await getLlmModels(force);
      models.value = normalizeModels(payload.models || []);
      unavailable.value = payload.unavailable || [];
      if (!models.value.some((model) => model.id === selectedModel.value)) {
        selectedModel.value = models.value[0]?.id || "";
      }
      return payload;
    })();
    try {
      return await modelsRequest;
    } finally {
      checkingModels.value = false;
      modelsRequest = null;
    }
  }

  async function loadSupplementalStatus({
    includeConcurrency = true,
    includeDiagnostics = true,
  } = {}) {
    const tasks = [];
    if (includeConcurrency) {
      tasks.push(["concurrency", getLlmConcurrency()]);
    }
    if (includeDiagnostics) {
      tasks.push(["diagnostics", getDiagnostics()]);
    }
    if (!tasks.length) return;

    const results = await Promise.allSettled(tasks.map(([, task]) => task));
    tasks.forEach(([name], index) => {
      const result = results[index];
      if (name === "concurrency") {
        concurrency.value = result.status === "fulfilled" ? result.value : null;
      }
      if (name === "diagnostics") {
        diagnostics.value = result.status === "fulfilled" ? result.value : null;
      }
    });
    if (!includeConcurrency) {
      concurrency.value = null;
    }
    if (!includeDiagnostics) {
      diagnostics.value = null;
    }
  }

  async function refresh({
    forceModels = false,
    includeModels = true,
    includeConcurrency = true,
    includeDiagnostics = true,
  } = {}) {
    loading.value = true;
    error.value = "";
    message.value = "";
    try {
      await loadStatus();
      await loadSupplementalStatus({ includeConcurrency, includeDiagnostics });
      if (configured.value && includeModels) {
        await loadModels(forceModels);
      } else if (!configured.value) {
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
    refresh({ includeModels: false, includeConcurrency: false, includeDiagnostics: false });
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

export function normalizeModels(rawModels) {
  return rawModels
    .map((model) => {
      if (typeof model === "string") {
        return { id: model, label: model, tier: "" };
      }
      if (!model || typeof model !== "object") {
        return null;
      }
      const id = String(model.id || model.name || model.model || "").trim();
      if (!id) return null;
      return {
        ...model,
        id,
        label: readableModelLabel(model) || id,
      };
    })
    .filter(Boolean);
}

function readableModelLabel(model) {
  for (const key of ["label", "display_name", "name", "model", "id"]) {
    const value = model?.[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
    if (typeof value === "number") {
      return String(value);
    }
  }
  return "";
}

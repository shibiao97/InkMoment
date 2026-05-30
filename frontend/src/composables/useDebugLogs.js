import { computed, ref } from "vue";
import { getHealth } from "../api/inkmoment";
import { getDesktopBackendLogs, getDesktopBackendStatus } from "../api/runtime";

export function useDebugLogs({ currentView, booting, bannerText, auth, desktopBackendError }) {
  const debugOpen = ref(false);
  const debugLoading = ref(false);
  const debugError = ref("");
  const debugPayload = ref(null);
  const debugBackendStatus = ref(null);
  const debugHealth = ref(null);
  const debugCopied = ref(false);

  const debugLogText = computed(() => {
    const payload = debugPayload.value || {};
    const lines = Array.isArray(payload.lines) ? payload.lines : [];
    const authStatus = auth.status.value || {};
    const backendStatus = debugBackendStatus.value || {};
    const health = debugHealth.value || {};
    const header = [
      `frontend_view=${currentView.value}`,
      `frontend_booting=${booting.value}`,
      `frontend_banner=${bannerText.value || ""}`,
      `auth_configured=${authStatus.configured ?? ""}`,
      `auth_authenticated=${authStatus.authenticated ?? ""}`,
      `auth_authorized=${authStatus.authorized ?? ""}`,
      `auth_reason=${authStatus.reason || auth.license.value?.reason || ""}`,
      `auth_last_error=${auth.lastErrorCode.value || ""}`,
      `desktop_backend_ready=${backendStatus.ready ?? ""}`,
      `desktop_backend_running=${backendStatus.running ?? ""}`,
      `desktop_backend_starting=${backendStatus.starting ?? ""}`,
      `desktop_backend_error=${backendStatus.error || desktopBackendError.value || ""}`,
      `sidecar_health_ok=${health.ok ?? ""}`,
      `sidecar_active_job=${health.active_job || ""}`,
      `sidecar_active_session=${health.active_session || ""}`,
      `backend_url=${payload.backend?.url || ""}`,
      `health_url=${payload.backend?.health_url || ""}`,
      `pid=${payload.backend?.pid || ""}`,
      `startup_error=${payload.startup_error || ""}`,
    ];
    return [...header, "", ...lines].join("\n").trim();
  });

  async function openDebugLogs() {
    debugOpen.value = true;
    await refreshDebugLogs();
  }

  async function refreshDebugLogs() {
    debugLoading.value = true;
    debugError.value = "";
    debugCopied.value = false;
    try {
      const [logsResult, backendStatusResult, healthResult] = await Promise.allSettled([
        getDesktopBackendLogs(),
        getDesktopBackendStatus(),
        getHealth(),
      ]);
      debugPayload.value = logsResult.status === "fulfilled"
        ? logsResult.value
        : {
            lines: [`[frontend] 读取后端日志失败：${logsResult.reason?.message || logsResult.reason}`],
            startup_error: "",
            backend: null,
          };
      debugBackendStatus.value = backendStatusResult.status === "fulfilled"
        ? backendStatusResult.value
        : { error: backendStatusResult.reason?.message || "读取桌面后端状态失败" };
      debugHealth.value = healthResult.status === "fulfilled"
        ? healthResult.value
        : { ok: false, error: healthResult.reason?.message || "读取 sidecar health 失败" };
    } catch (err) {
      debugError.value = err.message || "读取 Debug 日志失败";
    } finally {
      debugLoading.value = false;
    }
  }

  async function copyDebugLogs() {
    debugCopied.value = false;
    try {
      await navigator.clipboard.writeText(debugLogText.value || "");
      debugCopied.value = true;
    } catch (err) {
      debugError.value = err.message || "复制日志失败";
    }
  }

  return {
    debugOpen,
    debugLoading,
    debugError,
    debugLogText,
    debugCopied,
    openDebugLogs,
    refreshDebugLogs,
    copyDebugLogs,
  };
}

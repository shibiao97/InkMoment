import { ref } from "vue";
import { getDesktopBackendStatus, isTauriRuntime } from "../api/runtime";

const BACKEND_STATUS_POLL_MS = 3000;
const BACKEND_STATUS_FAILURE_LIMIT = 3;

export function useDesktopBackendMonitor() {
  const desktopBackendError = ref("");
  let desktopBackendTimer = null;
  let desktopBackendFailureCount = 0;
  let desktopBackendStatusInFlight = false;

  function startDesktopBackendMonitor() {
    if (!isTauriRuntime() || desktopBackendTimer) return;
    desktopBackendTimer = window.setInterval(checkDesktopBackendStatus, BACKEND_STATUS_POLL_MS);
  }

  function stopDesktopBackendMonitor() {
    if (!desktopBackendTimer) return;
    window.clearInterval(desktopBackendTimer);
    desktopBackendTimer = null;
  }

  async function checkDesktopBackendStatus() {
    if (desktopBackendStatusInFlight) return;
    desktopBackendStatusInFlight = true;
    try {
      const status = await getDesktopBackendStatus();
      if (!status || status.ready) {
        desktopBackendFailureCount = 0;
        desktopBackendError.value = "";
        return;
      }
      desktopBackendFailureCount += 1;
      if (
        status.running &&
        isTransientBackendHealthError(status.error) &&
        desktopBackendFailureCount < BACKEND_STATUS_FAILURE_LIMIT
      ) {
        return;
      }
      desktopBackendError.value = status.error || "桌面后端不可用";
    } catch (err) {
      desktopBackendFailureCount += 1;
      if (
        isTransientBackendHealthError(err.message) &&
        desktopBackendFailureCount < BACKEND_STATUS_FAILURE_LIMIT
      ) {
        return;
      }
      desktopBackendError.value = err.message || "桌面后端状态检查失败";
    } finally {
      desktopBackendStatusInFlight = false;
    }
  }

  return {
    desktopBackendError,
    startDesktopBackendMonitor,
    stopDesktopBackendMonitor,
  };
}

function isTransientBackendHealthError(message = "") {
  return /读取健康检查响应超时|Resource temporarily unavailable|os error 35|timed out|WouldBlock/i.test(
    String(message || ""),
  );
}

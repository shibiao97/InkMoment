import { ref } from "vue";

import { AUTH_INVALID_EVENT } from "../api/http";
import { getJob, getStatus } from "../api/inkmoment";
import { initDesktopBackend } from "../api/runtime";
import { resolveNextStep } from "./useNextStep";

const ACTIVE_JOB_STATUSES = new Set(["pending", "scanning", "hashing", "grouping", "checking"]);
const STARTUP_AUTH_TIMEOUT_MS = 6000;

export function useAppStartup({
  auth,
  enterProcessing,
  enterHome,
  resumeStep,
  clearStartedPayload,
  startDesktopBackendMonitor,
  onAuthInvalid = null,
}) {
  const booting = ref(true);
  const bootMessage = ref("正在启动本地服务...");
  const bootError = ref("");
  const authDialogOpen = ref(false);

  async function resumeFromBackend() {
    booting.value = true;
    bootMessage.value = "正在启动本地服务...";
    bootError.value = "";
    try {
      const backend = await initDesktopBackend({
        onStatus: (status) => {
          if (status?.starting) bootMessage.value = "正在启动本地服务...";
        },
      });
      if (backend) startDesktopBackendMonitor();
      bootMessage.value = "正在检查登录状态...";
      const authStatus = await auth.refresh(true, { timeoutMs: STARTUP_AUTH_TIMEOUT_MS });
      if (!authStatus?.authorized) {
        authDialogOpen.value = true;
        enterHome();
        return;
      }
      bootMessage.value = "正在恢复上次进度...";
      await restoreAuthorizedWorkflow();
    } catch (err) {
      bootError.value = err.message || "恢复进度失败";
      enterHome();
    } finally {
      booting.value = false;
    }
  }

  async function restoreAuthorizedWorkflow() {
    auth.startPolling(handleAuthInvalid);
    const job = await getJob();
    if (ACTIVE_JOB_STATUSES.has(job?.status)) {
      enterProcessing({ folder: job.folder, mode: job.mode, engine: job.engine, dry_run: job.dry_run });
      return;
    }
    const status = await getStatus();
    resumeStep(resolveNextStep(status).kind);
  }

  async function handleAuthAuthorized() {
    booting.value = true;
    bootError.value = "";
    try {
      await restoreAuthorizedWorkflow();
    } catch (err) {
      bootError.value = err.message || "授权后恢复进度失败";
      enterHome();
    } finally {
      booting.value = false;
    }
  }

  function handleAuthInvalid(nextStatus = null) {
    if (nextStatus && typeof nextStatus === "object") {
      auth.applyStatus(nextStatus);
    } else {
      auth.markInvalid({ reason: "unauthenticated" });
    }
    auth.stopPolling();
    authDialogOpen.value = true;
    if (typeof onAuthInvalid === "function") onAuthInvalid();
    clearStartedPayload();
    enterHome();
  }

  function handleAuthInvalidEvent(event) {
    const code = event?.detail?.code || "unauthenticated";
    const eventAuth = event?.detail?.auth;
    handleAuthInvalid(eventAuth ? {
      ...eventAuth,
      reason: code || eventAuth.reason,
      license: {
        ...(eventAuth.license || {}),
        authorized: false,
        reason: code || eventAuth.license?.reason || eventAuth.reason,
      },
    } : {
      reason: code,
      license: { authorized: false, reason: code },
    });
  }

  function bindAuthInvalidEvent() {
    window.addEventListener(AUTH_INVALID_EVENT, handleAuthInvalidEvent);
  }

  function unbindAuthInvalidEvent() {
    window.removeEventListener(AUTH_INVALID_EVENT, handleAuthInvalidEvent);
  }

  return {
    booting,
    bootMessage,
    bootError,
    authDialogOpen,
    bindAuthInvalidEvent,
    handleAuthAuthorized,
    resumeFromBackend,
    unbindAuthInvalidEvent,
  };
}

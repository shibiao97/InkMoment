import { computed, onUnmounted, ref } from "vue";
import {
  getAuthStatus,
  loginAuth,
  logoutAuth,
  redeemAuthCdk,
  registerAuth,
  unbindAuthDevice,
} from "../api/inkmoment";

const DEFAULT_AUTH_CHECK_MS = 10 * 60 * 1000;
const TRANSIENT_AUTH_ERROR_CODES = new Set([
  "",
  "auth_check_failed",
  "auth_server_unavailable",
  "request_timeout",
]);

export function useAuthSession() {
  const status = ref(null);
  const loading = ref(false);
  const error = ref("");
  const message = ref("");
  const lastErrorCode = ref("");
  let timer = null;

  const configured = computed(() => Boolean(status.value?.configured));
  const authenticated = computed(() => Boolean(status.value?.authenticated));
  const authorized = computed(() => Boolean(status.value?.authorized));
  const account = computed(() => status.value?.account || null);
  const license = computed(() => status.value?.license || {});
  const device = computed(() => status.value?.device || account.value?.device || {});
  const limits = computed(() => status.value?.limits || account.value?.limits || {});
  const serverUrl = computed(() => status.value?.server_url || "");
  const connectionState = computed(() => {
    const code = lastErrorCode.value || status.value?.reason || "";
    if (!configured.value) return "blocked";
    if (code === "auth_server_unavailable" || code === "auth_check_failed") return "error";
    if (loading.value) return "checking";
    return "ready";
  });
  const connectionText = computed(() => {
    if (!configured.value) return "授权服务不可用";
    if (connectionState.value === "error") return "连接异常";
    if (connectionState.value === "checking") return "检查中";
    return "已配置授权服务";
  });
  const checkIntervalMs = computed(() => {
    const seconds = Number(status.value?.check_interval_seconds || 0);
    return seconds > 0 ? seconds * 1000 : DEFAULT_AUTH_CHECK_MS;
  });

  const reasonText = computed(() => {
    const reason = status.value?.reason || license.value?.reason;
    if (!configured.value) return "授权服务不可用";
    if (!authenticated.value) return "请登录账号";
    if (reason === "not_activated") return "账号尚未开通";
    if (reason === "expired") return "账号使用期限已过期";
    if (reason === "revoked") return "账号授权已被撤销";
    if (reason === "disabled") return "账号已被禁用";
    if (reason === "device_mismatch") return "当前设备与账号绑定设备不一致";
    if (!authorized.value) return "账号暂不可用";
    return "授权有效";
  });

  async function refresh(force = false, options = {}) {
    loading.value = true;
    error.value = "";
    lastErrorCode.value = "";
    try {
      status.value = await getAuthStatus(force, options);
      return status.value;
    } catch (err) {
      lastErrorCode.value = err.code || "";
      error.value = friendlyAuthError(err, "授权状态检查失败");
      if (TRANSIENT_AUTH_ERROR_CODES.has(err.code || "")) {
        return status.value;
      }
      markInvalid(err.data?.auth || {
        reason: err.code || "auth_check_failed",
        license: { authorized: false, reason: err.code || "auth_check_failed" },
      });
      return status.value;
    } finally {
      loading.value = false;
    }
  }

  async function login(email, password) {
    loading.value = true;
    error.value = "";
    message.value = "";
    lastErrorCode.value = "";
    try {
      status.value = await loginAuth({ email, password });
      message.value = authorized.value ? "登录成功" : "登录成功，请兑换 CDK 开通";
      return true;
    } catch (err) {
      lastErrorCode.value = err.code || "";
      error.value = friendlyAuthError(err, "登录失败");
      return false;
    } finally {
      loading.value = false;
    }
  }

  async function register(email, password, displayName = "") {
    loading.value = true;
    error.value = "";
    message.value = "";
    lastErrorCode.value = "";
    try {
      status.value = await registerAuth({ email, password, display_name: displayName });
      message.value = authorized.value ? "注册成功" : "注册成功，请兑换 CDK 开通";
      return true;
    } catch (err) {
      lastErrorCode.value = err.code || "";
      error.value = friendlyAuthError(err, "注册失败");
      return false;
    } finally {
      loading.value = false;
    }
  }

  async function redeem(code) {
    loading.value = true;
    error.value = "";
    message.value = "";
    lastErrorCode.value = "";
    try {
      status.value = await redeemAuthCdk(code);
      message.value = authorized.value ? "CDK 兑换成功" : "CDK 已提交，请刷新授权状态";
      return true;
    } catch (err) {
      lastErrorCode.value = err.code || "";
      error.value = friendlyAuthError(err, "CDK 兑换失败");
      return false;
    } finally {
      loading.value = false;
    }
  }

  async function unbindDevice(reason = "") {
    loading.value = true;
    error.value = "";
    message.value = "";
    lastErrorCode.value = "";
    try {
      status.value = await unbindAuthDevice({
        confirm_penalty: true,
        reason,
      });
      message.value = "设备已解除绑定，已扣除 3 天使用时长，请重新登录";
      await logout();
      return true;
    } catch (err) {
      lastErrorCode.value = err.code || "";
      error.value = friendlyAuthError(err, "解除设备绑定失败");
      return false;
    } finally {
      loading.value = false;
    }
  }

  async function logout() {
    loading.value = true;
    error.value = "";
    lastErrorCode.value = "";
    try {
      status.value = await logoutAuth();
      message.value = "已退出登录";
      return true;
    } catch (err) {
      lastErrorCode.value = err.code || "";
      error.value = friendlyAuthError(err, "退出登录失败");
      return false;
    } finally {
      loading.value = false;
    }
  }

  function startPolling(onInvalid) {
    stopPolling();
    timer = window.setInterval(async () => {
      const next = await refresh(true);
      if (!next?.authorized && typeof onInvalid === "function") {
        onInvalid(next);
      }
    }, checkIntervalMs.value);
  }

  function stopPolling() {
    if (timer) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  function applyStatus(nextStatus) {
    if (nextStatus && typeof nextStatus === "object") {
      status.value = nextStatus;
    }
  }

  function markInvalid(nextStatus = {}) {
    const reason = nextStatus.reason || nextStatus.code || nextStatus.license?.reason || "unauthenticated";
    lastErrorCode.value = reason;
    status.value = {
      configured: nextStatus.configured ?? configured.value ?? true,
      server_url: nextStatus.server_url ?? serverUrl.value,
      authenticated: Boolean(nextStatus.authenticated),
      authorized: false,
      reason,
      account: nextStatus.account ?? account.value,
      license: nextStatus.license || { authorized: false, reason },
      device: nextStatus.device || device.value,
      limits: nextStatus.limits || limits.value,
      last_checked_at: nextStatus.last_checked_at || status.value?.last_checked_at || 0,
      next_check_at: null,
      check_interval_seconds: nextStatus.check_interval_seconds || status.value?.check_interval_seconds,
    };
  }

  onUnmounted(stopPolling);

  return {
    status,
    loading,
    error,
    message,
    lastErrorCode,
    configured,
    authenticated,
    authorized,
    account,
    license,
    device,
    limits,
    serverUrl,
    connectionState,
    connectionText,
    reasonText,
    refresh,
    login,
    register,
    redeem,
    unbindDevice,
    logout,
    startPolling,
    stopPolling,
    applyStatus,
    markInvalid,
  };
}

function friendlyAuthError(err, fallback) {
  const code = err?.code || "";
  if (code === "device_mismatch") {
    return "当前设备与账号绑定设备不一致。请先在原设备自助解绑，或联系管理员后台解除绑定后再登录。";
  }
  if (code === "invalid_credentials") {
    return "账号或密码不正确。";
  }
  if (code === "login_locked") {
    return "账号连续登录失败后已临时锁定，请稍后再试。";
  }
  if (code === "expired") {
    return "账号使用期限已过期，请兑换新的 CDK 后继续使用。";
  }
  if (code === "not_activated") {
    return "账号尚未开通，请先兑换 CDK。";
  }
  if (code === "revoked") {
    return "账号授权已被撤销，请联系管理员处理。";
  }
  if (code === "disabled") {
    return "账号已被禁用，请联系管理员处理。";
  }
  if (code === "auth_server_not_configured") {
    return "授权服务不可用，请联系管理员处理。";
  }
  if (code === "auth_server_unavailable" || code === "auth_check_failed" || code === "request_timeout") {
    return "暂时无法连接授权服务，当前页面不会因此退出登录。请稍后重试或打开日志查看网络错误。";
  }
  return err?.message || fallback;
}

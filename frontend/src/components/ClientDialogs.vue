<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  auth: {
    type: Object,
    required: true,
  },
  authOpen: {
    type: Boolean,
    default: false,
  },
  notices: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(["authorized", "update:authOpen"]);

const AUTH_PANEL_TITLES = {
  account: "登录 / 注册",
  redeem: "兑换 CDK",
  status: "授权状态",
  device: "设备已绑定",
  expired: "授权已过期",
};
const DISMISSED_NOTICE_KEY = "inkmoment.dismissedClientNotices";

const authMode = ref("login");
const email = ref("");
const password = ref("");
const displayName = ref("");
const cdk = ref("");
const unbindReason = ref("");
const confirmingUnbind = ref(false);
const dismissedNotices = ref(loadDismissedNotices());

const accountEmail = computed(() => props.auth.account.value?.email || "");
const statusReason = computed(() => (
  props.auth.status.value?.reason
  || props.auth.license.value?.reason
  || props.auth.lastErrorCode?.value
  || ""
));
const authPanel = computed(() => {
  const reason = statusReason.value;
  if (reason === "device_mismatch" || props.auth.lastErrorCode?.value === "device_mismatch") return "device";
  if (!props.auth.authenticated.value) return "account";
  if (reason === "expired") return "expired";
  if (!props.auth.authorized.value) return "redeem";
  return "status";
});
const authTone = computed(() => {
  if (!props.auth.configured.value) return "blocked";
  if (props.auth.authorized.value) return "ready";
  if (["device_mismatch", "expired", "disabled", "revoked"].includes(statusReason.value)) return "blocked";
  if (props.auth.authenticated.value) return "warning";
  return "pending";
});
const dialogTitle = computed(() => AUTH_PANEL_TITLES[authPanel.value] || "客户端授权");
const canCloseAuthDialog = computed(() => props.auth.authorized.value && authPanel.value === "status");
const canSubmitAccount = computed(() => email.value.trim() && password.value.length >= 8);
const canRedeem = computed(() => cdk.value.trim().length >= 4);
const remainingDays = computed(() => {
  const seconds = Number(props.auth.license.value?.remaining_seconds || 0);
  if (seconds <= 0) return 0;
  return Math.ceil(seconds / 86400);
});
const expiresText = computed(() => formatAuthTime(props.auth.license.value?.expires_at, "未开通"));
const lastCheckedText = computed(() => formatAuthTime(props.auth.status.value?.last_checked_at, "尚未检查"));
const deviceName = computed(() => {
  const device = props.auth.device.value || {};
  return device.name || device.hostname || device.fingerprint || "未绑定";
});
const deviceFingerprint = computed(() => props.auth.device.value?.fingerprint || "未识别");
const authStageItems = computed(() => [
  {
    label: "账号",
    value: props.auth.authenticated.value ? "已登录" : "未登录",
    state: props.auth.authenticated.value ? "ready" : "pending",
  },
  {
    label: "授权",
    value: props.auth.reasonText.value,
    state: props.auth.authorized.value ? "ready" : authTone.value,
  },
  {
    label: "设备",
    value: deviceName.value,
    state: statusReason.value === "device_mismatch" ? "blocked" : "ready",
  },
]);
const maintenanceNotice = computed(() => normalizeNotice(props.notices?.maintenance, "maintenance"));
const versionNotice = computed(() => normalizeNotice(props.notices?.version_update, "version"));
const remoteNotices = computed(() => {
  const notices = props.notices?.remote_notices;
  if (!Array.isArray(notices)) return [];
  return notices
    .map((notice) => normalizeNotice(notice, "notice"))
    .filter(Boolean)
    .sort((left, right) => Number(right.pinned) - Number(left.pinned));
});
const activeNotice = computed(() => {
  const maintenance = maintenanceNotice.value;
  if (maintenance?.enabled && (maintenance.blocking || !dismissedNotices.value.has(maintenance.id))) {
    return maintenance;
  }
  const remote = remoteNotices.value.find((notice) => (
    notice.blocking
    || notice.force
    || !dismissedNotices.value.has(notice.id)
  ));
  if (remote) return remote;
  const version = versionNotice.value;
  if (version?.enabled && (version.force || !dismissedNotices.value.has(version.id))) {
    return version;
  }
  return null;
});

watch(
  () => props.auth.authorized.value,
  (authorized) => {
    if (authorized) {
      confirmingUnbind.value = false;
      emit("update:authOpen", false);
    }
  },
);

async function submitAccount() {
  if (!canSubmitAccount.value || props.auth.loading.value) return;
  const ok = authMode.value === "register"
    ? await props.auth.register(email.value.trim(), password.value, displayName.value.trim())
    : await props.auth.login(email.value.trim(), password.value);
  if (ok && props.auth.authorized.value) emit("authorized");
}

async function submitCdk() {
  if (!canRedeem.value || props.auth.loading.value) return;
  const ok = await props.auth.redeem(cdk.value.trim());
  if (ok && props.auth.authorized.value) {
    cdk.value = "";
    emit("authorized");
  }
}

async function refreshAuthStatus() {
  if (props.auth.loading.value) return;
  await props.auth.refresh(true);
}

function openAuthStatus() {
  emit("update:authOpen", true);
}

function closeAuthDialog() {
  if (!canCloseAuthDialog.value) return;
  emit("update:authOpen", false);
}

function requestUnbind() {
  confirmingUnbind.value = true;
}

async function confirmUnbind() {
  if (props.auth.loading.value) return;
  const ok = await props.auth.unbindDevice(unbindReason.value.trim() || "用户自助换机");
  if (ok) {
    confirmingUnbind.value = false;
    emit("update:authOpen", true);
  }
}

function dismissNotice(notice) {
  if (!notice || notice.blocking || notice.force) return;
  dismissedNotices.value = new Set([...dismissedNotices.value, notice.id]);
  saveDismissedNotices(dismissedNotices.value);
}

function openNoticeUrl(notice) {
  if (!notice?.url || typeof window === "undefined") return;
  window.open(notice.url, "_blank", "noopener,noreferrer");
}

function normalizeNotice(raw, fallbackKind) {
  if (!raw || typeof raw !== "object" || !raw.enabled) return null;
  const kind = raw.kind || fallbackKind;
  const defaultTitle = kind === "version" ? "发现新版本" : kind === "maintenance" ? "维护公告" : "系统公告";
  const title = String(raw.title || defaultTitle).trim();
  const message = String(raw.message || raw.body || "").trim();
  const id = String(raw.id || `${kind}:${title}:${message}:${raw.version || ""}`).trim();
  return {
    id,
    kind,
    title,
    message,
    version: String(raw.version || "").trim(),
    url: String(raw.download_url || raw.url || "").trim(),
    actionText: String(raw.action_text || (kind === "version" ? "查看更新" : "知道了")).trim(),
    blocking: Boolean(raw.blocking),
    force: Boolean(raw.force || raw.required),
    severity: raw.severity || "info",
    pinned: Boolean(raw.pinned),
    enabled: true,
  };
}

function noticeEyebrow(notice) {
  if (notice?.kind === "version") return "版本更新";
  if (notice?.kind === "maintenance") return "维护公告";
  return "系统公告";
}

function formatAuthTime(value, fallback) {
  const timestamp = Number(value || 0);
  if (!timestamp) return fallback;
  return new Date(timestamp * 1000).toLocaleString();
}

function loadDismissedNotices() {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage?.getItem(DISMISSED_NOTICE_KEY);
    const values = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(values) ? values : []);
  } catch {
    return new Set();
  }
}

function saveDismissedNotices(values) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage?.setItem(DISMISSED_NOTICE_KEY, JSON.stringify([...values]));
  } catch {
    // localStorage can be unavailable in hardened WebViews; notices remain session-scoped.
  }
}
</script>

<template>
  <button
    class="client-auth-dock"
    :class="`is-${authTone}`"
    type="button"
    @click="openAuthStatus"
  >
    <span class="status-dot" aria-hidden="true"></span>
    <strong>{{ auth.authorized.value ? "授权有效" : auth.reasonText.value }}</strong>
  </button>

  <Teleport to="body">
    <div v-if="authOpen" class="client-dialog-backdrop" role="dialog" aria-modal="true">
      <section class="client-dialog auth-dialog-panel auth-gate-dialog">
        <div class="auth-dialog-sidebar">
          <div class="auth-brand">
            <span class="brand-mark" aria-hidden="true"></span>
            <div>
              <p class="eyebrow">客户端授权</p>
              <h2>{{ dialogTitle }}</h2>
            </div>
          </div>

          <div class="auth-flow-grid auth-dialog-flow">
            <div
              v-for="item in authStageItems"
              :key="item.label"
              class="auth-flow-item"
              :class="`is-${item.state}`"
            >
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </div>

        <div class="auth-dialog-main">
          <header class="client-dialog-head">
            <div>
              <p class="eyebrow">InkMoment 授权</p>
              <h2>{{ dialogTitle }}</h2>
            </div>
            <button
              v-if="canCloseAuthDialog"
              class="btn-ghost"
              type="button"
              @click="closeAuthDialog"
            >
              稍后再说
            </button>
          </header>

          <div v-if="!auth.configured.value" class="auth-warning">
            <strong>授权服务不可用</strong>
            <span>请联系管理员检查客户端授权服务器配置。</span>
          </div>

        <form v-if="authPanel === 'account'" class="auth-form" @submit.prevent="submitAccount">
          <div class="auth-tabs">
            <button type="button" :class="{ active: authMode === 'login' }" @click="authMode = 'login'">
              登录
            </button>
            <button type="button" :class="{ active: authMode === 'register' }" @click="authMode = 'register'">
              注册
            </button>
          </div>

          <label>
            <span>账号邮箱</span>
            <input v-model="email" type="email" autocomplete="email" required>
          </label>
          <label>
            <span>密码</span>
            <input v-model="password" type="password" autocomplete="current-password" minlength="8" required>
          </label>
          <label v-if="authMode === 'register'">
            <span>显示名</span>
            <input v-model="displayName" type="text" autocomplete="name">
          </label>

          <button class="btn-primary" type="submit" :disabled="auth.loading.value || !canSubmitAccount">
            <span v-if="auth.loading.value" class="btn-spinner" aria-hidden="true"></span>
            {{ auth.loading.value ? "处理中" : authMode === "register" ? "注册并绑定本机" : "登录" }}
          </button>
        </form>

        <section v-else-if="authPanel === 'redeem'" class="auth-form">
          <div class="auth-account-row">
            <div>
              <span>当前账号</span>
              <strong>{{ accountEmail }}</strong>
            </div>
            <div class="auth-inline-actions">
              <button class="btn-ghost" type="button" :disabled="auth.loading.value" @click="refreshAuthStatus">
                刷新
              </button>
              <button class="btn-ghost" type="button" :disabled="auth.loading.value" @click="auth.logout">
                退出
              </button>
            </div>
          </div>
          <label>
            <span>CDK 激活码</span>
            <input v-model="cdk" type="text" autocomplete="off" spellcheck="false">
          </label>
          <button class="btn-primary" type="button" :disabled="auth.loading.value || !canRedeem" @click="submitCdk">
            <span v-if="auth.loading.value" class="btn-spinner" aria-hidden="true"></span>
            {{ auth.loading.value ? "兑换中" : "兑换并开通" }}
          </button>
        </section>

        <section v-else-if="authPanel === 'expired'" class="auth-form">
          <div class="auth-expired-box">
            <strong>授权已过期</strong>
            <span>当前账号到期时间：{{ expiresText }}。兑换新的 CDK 后即可继续使用。</span>
          </div>
          <label>
            <span>新的 CDK 激活码</span>
            <input v-model="cdk" type="text" autocomplete="off" spellcheck="false">
          </label>
          <div class="auth-inline-actions">
            <button class="btn-primary" type="button" :disabled="auth.loading.value || !canRedeem" @click="submitCdk">
              兑换并恢复
            </button>
            <button class="btn-ghost" type="button" :disabled="auth.loading.value" @click="auth.logout">
              退出账号
            </button>
          </div>
        </section>

        <section v-else-if="authPanel === 'device'" class="auth-form">
          <div class="auth-help">
            <strong>此账号已经绑定其他设备</strong>
            <span>为了保护授权，同一账号需要先解除旧设备绑定，再在当前设备登录。若无法操作旧设备，请联系管理员后台解绑。</span>
          </div>
          <div class="auth-meta-grid">
            <div>
              <span>当前设备</span>
              <strong>{{ deviceName }}</strong>
            </div>
            <div>
              <span>设备指纹</span>
              <strong>{{ deviceFingerprint }}</strong>
            </div>
            <div>
              <span>处理方式</span>
              <strong>{{ auth.authenticated.value ? "可自助解绑" : "需先登录或联系管理员" }}</strong>
            </div>
          </div>
          <label v-if="auth.authenticated.value">
            <span>解绑原因</span>
            <input v-model="unbindReason" type="text" placeholder="例如更换电脑">
          </label>
          <div class="auth-inline-actions">
            <button
              v-if="auth.authenticated.value"
              class="btn-ghost btn-danger"
              type="button"
              :disabled="auth.loading.value"
              @click="requestUnbind"
            >
              解除绑定
            </button>
            <button class="btn-ghost" type="button" :disabled="auth.loading.value" @click="refreshAuthStatus">
              重新检查
            </button>
            <button class="btn-ghost" type="button" :disabled="auth.loading.value" @click="auth.logout">
              返回登录
            </button>
          </div>
        </section>

        <section v-else class="auth-form">
          <div class="auth-status-grid">
            <div>
              <span>账号</span>
              <strong>{{ accountEmail || "未登录" }}</strong>
            </div>
            <div>
              <span>到期时间</span>
              <strong>{{ expiresText }}</strong>
            </div>
            <div>
              <span>剩余天数</span>
              <strong>{{ remainingDays }} 天</strong>
            </div>
          </div>
          <div class="auth-meta-grid">
            <div>
              <span>本机设备</span>
              <strong>{{ deviceName }}</strong>
            </div>
            <div>
              <span>最近检查</span>
              <strong>{{ lastCheckedText }}</strong>
            </div>
            <div>
              <span>授权服务器</span>
              <strong>{{ auth.connectionText.value }}</strong>
            </div>
          </div>
          <p class="auth-ready">授权有效，可以继续使用当前功能。</p>
          <div class="auth-inline-actions">
            <button class="btn-primary" type="button" :disabled="auth.loading.value" @click="refreshAuthStatus">
              刷新授权状态
            </button>
            <button class="btn-ghost" type="button" :disabled="auth.loading.value" @click="auth.logout">
              退出登录
            </button>
          </div>
        </section>

          <p v-if="auth.message.value" class="start-note">{{ auth.message.value }}</p>
          <p v-if="auth.error.value" class="form-error">{{ auth.error.value }}</p>
        </div>

        <aside class="auth-dialog-inspector">
          <section class="inspector-card inspector-status-card">
            <p class="eyebrow">会话状态</p>
            <h2>{{ auth.reasonText.value }}</h2>
            <p>{{ auth.connectionText.value }}</p>
          </section>
          <section class="inspector-card auth-meta-grid auth-inspector-meta">
            <div>
              <span>到期时间</span>
              <strong>{{ expiresText }}</strong>
            </div>
            <div>
              <span>本机设备</span>
              <strong>{{ deviceName }}</strong>
            </div>
            <div>
              <span>最近检查</span>
              <strong>{{ lastCheckedText }}</strong>
            </div>
          </section>
        </aside>
      </section>
    </div>

    <div v-if="confirmingUnbind" class="client-dialog-backdrop is-confirm" role="dialog" aria-modal="true">
      <section class="client-dialog client-confirm-dialog">
        <header class="client-dialog-head">
          <div>
            <p class="eyebrow">设备解绑确认</p>
            <h2>确认解除当前账号设备绑定？</h2>
          </div>
        </header>
        <p class="client-dialog-copy">解除绑定会扣除 3 天使用时长，并需要重新登录后绑定当前设备。</p>
        <div class="auth-inline-actions">
          <button class="btn-ghost" type="button" :disabled="auth.loading.value" @click="confirmingUnbind = false">
            取消
          </button>
          <button class="btn-primary" type="button" :disabled="auth.loading.value" @click="confirmUnbind">
            <span v-if="auth.loading.value" class="btn-spinner" aria-hidden="true"></span>
            确认解绑
          </button>
        </div>
      </section>
    </div>

    <div v-if="activeNotice" class="client-dialog-backdrop notice-backdrop" role="dialog" aria-modal="true">
      <section class="client-dialog notice-dialog" :class="`is-${activeNotice.kind}`">
        <header class="client-dialog-head">
          <div>
            <p class="eyebrow">{{ noticeEyebrow(activeNotice) }}</p>
            <h2>{{ activeNotice.title }}</h2>
          </div>
          <span v-if="activeNotice.version" class="notice-version">v{{ activeNotice.version }}</span>
        </header>
        <p class="client-dialog-copy">{{ activeNotice.message || "请留意当前服务状态。" }}</p>
        <div class="auth-inline-actions">
          <button
            v-if="activeNotice.url"
            class="btn-primary"
            type="button"
            @click="openNoticeUrl(activeNotice)"
          >
            {{ activeNotice.actionText }}
          </button>
          <button
            v-if="!activeNotice.blocking && !activeNotice.force"
            class="btn-ghost"
            type="button"
            @click="dismissNotice(activeNotice)"
          >
            我知道了
          </button>
        </div>
      </section>
    </div>
  </Teleport>
</template>

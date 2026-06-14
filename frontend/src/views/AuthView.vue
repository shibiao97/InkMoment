<script setup>
import { computed, ref } from "vue";
import WorkflowSidebar from "../components/WorkflowSidebar.vue";

const props = defineProps({
  auth: {
    type: Object,
    required: true,
  },
});
const emit = defineEmits(["authorized"]);

const mode = ref("login");
const email = ref("");
const password = ref("");
const displayName = ref("");
const cdk = ref("");
const unbindReason = ref("");

const accountEmail = computed(() => props.auth.account.value?.email || "");
const statusReason = computed(() => (
  props.auth.status.value?.reason
  || props.auth.license.value?.reason
  || props.auth.lastErrorCode?.value
  || ""
));
const expiresText = computed(() => {
  const expiresAt = props.auth.license.value?.expires_at;
  if (!expiresAt) return "未开通";
  return new Date(Number(expiresAt) * 1000).toLocaleString();
});
const lastCheckedText = computed(() => {
  const checkedAt = Number(props.auth.status.value?.last_checked_at || 0);
  if (!checkedAt) return "尚未检查";
  return new Date(checkedAt * 1000).toLocaleString();
});
const remainingDays = computed(() => {
  const seconds = Number(props.auth.license.value?.remaining_seconds || 0);
  if (seconds <= 0) return 0;
  return Math.ceil(seconds / 86400);
});
const deviceName = computed(() => {
  const device = props.auth.device.value || {};
  return device.name || device.fingerprint || "未绑定";
});
const canSubmitAccount = computed(() => email.value.trim() && password.value.length >= 8);
const canRedeem = computed(() => cdk.value.trim().length >= 4);
const authTone = computed(() => {
  if (!props.auth.configured.value) return "blocked";
  if (props.auth.authorized.value) return "ready";
  if (["device_mismatch", "expired", "disabled"].includes(statusReason.value)) return "blocked";
  if (props.auth.authenticated.value) return "warning";
  return "pending";
});
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
const showDeviceHelp = computed(() => (
  statusReason.value === "device_mismatch"
  || props.auth.lastErrorCode?.value === "device_mismatch"
));

async function submitAccount() {
  if (!canSubmitAccount.value || props.auth.loading.value) return;
  if (mode.value === "register") {
    await props.auth.register(email.value.trim(), password.value, displayName.value.trim());
  } else {
    await props.auth.login(email.value.trim(), password.value);
  }
  if (props.auth.authorized.value) emit("authorized");
}

async function submitCdk() {
  if (!canRedeem.value || props.auth.loading.value) return;
  await props.auth.redeem(cdk.value.trim());
  if (props.auth.authorized.value) {
    cdk.value = "";
    emit("authorized");
  }
}

async function confirmUnbind() {
  if (props.auth.loading.value) return;
  const ok = window.confirm("解除设备绑定会扣除 3 天使用时长，并需要重新登录。确认继续？");
  if (!ok) return;
  await props.auth.unbindDevice(unbindReason.value.trim() || "用户自助换机");
}

async function refreshAuthStatus() {
  if (props.auth.loading.value) return;
  await props.auth.refresh(true);
}
</script>

<template>
  <main class="app-shell studio-shell flow-workbench auth-shell">
    <WorkflowSidebar
      active-step="landing"
      summary-label="授权门禁"
      :summary-value="auth.authorized.value ? '授权有效' : auth.reasonText.value"
      :summary-detail="accountEmail || '等待账号登录'"
    />

    <section class="studio-main flow-main flow-main-stack auth-main">
      <header class="flow-hero auth-hero">
        <div class="auth-brand">
          <span class="brand-mark" aria-hidden="true"></span>
          <div>
            <p class="eyebrow">InkMoment 授权</p>
            <h1>登录并确认授权</h1>
            <p class="subtitle">先完成账号、CDK 与本机设备绑定，再进入照片筛选工作台。</p>
          </div>
        </div>
      </header>

      <section class="studio-panel auth-panel">
        <div v-if="!auth.configured.value" class="auth-warning">
          <strong>授权服务不可用</strong>
          <span>请联系管理员处理客户端授权配置。</span>
        </div>

        <form v-if="!auth.authenticated.value" class="auth-form" @submit.prevent="submitAccount">
          <div class="auth-tabs">
            <button type="button" :class="{ active: mode === 'login' }" @click="mode = 'login'">
              登录
            </button>
            <button type="button" :class="{ active: mode === 'register' }" @click="mode = 'register'">
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
          <label v-if="mode === 'register'">
            <span>显示名</span>
            <input v-model="displayName" type="text" autocomplete="name">
          </label>

          <button class="btn-primary" type="submit" :disabled="auth.loading.value || !canSubmitAccount">
            {{ auth.loading.value ? "处理中" : mode === "register" ? "注册并绑定本机" : "登录" }}
          </button>

          <div v-if="showDeviceHelp" class="auth-help">
            <strong>设备绑定不一致</strong>
            <span>当前账号已绑定其他设备，需要先在原设备自助解绑，或在管理后台解除绑定后再登录。</span>
          </div>
        </form>

        <section v-else-if="!auth.authorized.value" class="auth-form">
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
            {{ auth.loading.value ? "兑换中" : "兑换并开通" }}
          </button>

          <details class="auth-device-box">
            <summary>更换设备</summary>
            <p>如果账号已绑定其他设备，需要先解除绑定。解除绑定会扣除 3 天使用时长。</p>
            <input v-model="unbindReason" type="text" placeholder="解绑原因，例如更换电脑">
            <button class="btn-ghost" type="button" :disabled="auth.loading.value" @click="confirmUnbind">
              解除绑定并扣除 3 天
            </button>
          </details>
        </section>

        <section v-else class="auth-form">
          <div class="auth-account-row">
            <div>
              <span>授权账号</span>
              <strong>{{ accountEmail }}</strong>
            </div>
            <button class="btn-ghost" type="button" :disabled="auth.loading.value" @click="auth.logout">
              退出
            </button>
          </div>
          <p class="auth-ready">授权有效，剩余约 {{ remainingDays }} 天。最近检查：{{ lastCheckedText }}</p>
        </section>

        <p v-if="auth.message.value" class="start-note">{{ auth.message.value }}</p>
        <p v-if="auth.error.value" class="form-error">{{ auth.error.value }}</p>
      </section>
    </section>

    <aside class="studio-inspector flow-inspector auth-inspector">
      <section class="inspector-card inspector-status-card">
        <p class="eyebrow">授权状态</p>
        <h2>{{ auth.reasonText.value }}</h2>
        <p>{{ auth.connectionText.value }}</p>
      </section>

      <section class="inspector-card auth-flow-panel">
        <div
          v-for="item in authStageItems"
          :key="item.label"
          class="auth-flow-item"
          :class="`is-${item.state}`"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </section>

      <section v-if="auth.authenticated.value" class="inspector-card auth-meta-grid auth-inspector-meta">
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

      <section class="inspector-card inspector-actions">
        <button class="btn-ghost" type="button" :disabled="auth.loading.value" @click="refreshAuthStatus">
          重新检查授权
        </button>
        <button v-if="auth.authenticated.value" class="btn-ghost" type="button" :disabled="auth.loading.value" @click="auth.logout">
          退出账号
        </button>
      </section>
    </aside>
  </main>
</template>

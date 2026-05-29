<script setup>
import { computed, ref } from "vue";

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
  <main class="auth-shell">
    <section class="auth-panel">
      <div class="auth-brand">
        <span class="brand-mark" aria-hidden="true"></span>
        <div>
          <p class="eyebrow">InkMoment 授权</p>
          <h1>登录并确认授权</h1>
        </div>
      </div>

      <div v-if="!auth.configured.value" class="auth-warning">
        <strong>授权服务不可用</strong>
        <span>请联系管理员处理客户端授权配置。</span>
      </div>

      <div class="auth-flow-grid">
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

      <div v-if="auth.authenticated.value" class="auth-meta-grid">
        <div>
          <span>到期时间</span>
          <strong>{{ expiresText }}</strong>
        </div>
        <div>
          <span>本机设备</span>
          <strong>{{ deviceName }}</strong>
        </div>
      </div>

      <p v-if="auth.message.value" class="start-note">{{ auth.message.value }}</p>
      <p v-if="auth.error.value" class="form-error">{{ auth.error.value }}</p>
    </section>
  </main>
</template>

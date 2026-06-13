import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";

import ClientDialogs from "./ClientDialogs.vue";

function createAuth(overrides = {}) {
  const status = ref(overrides.status || {
    configured: true,
    authenticated: false,
    authorized: false,
    reason: "unauthenticated",
    license: { authorized: false, reason: "unauthenticated" },
    device: { name: "MacBook", fingerprint: "device-a" },
  });
  const loading = ref(false);
  const error = ref("");
  const message = ref("");
  const lastErrorCode = ref(overrides.lastErrorCode || "");
  const account = computed(() => status.value.account || null);
  const license = computed(() => status.value.license || {});
  const device = computed(() => status.value.device || account.value?.device || {});
  const configured = computed(() => Boolean(status.value.configured));
  const authenticated = computed(() => Boolean(status.value.authenticated));
  const authorized = computed(() => Boolean(status.value.authorized));
  const reasonText = computed(() => {
    const reason = status.value.reason || license.value.reason;
    if (!authenticated.value) return "请登录账号";
    if (reason === "expired") return "账号使用期限已过期";
    if (reason === "device_mismatch") return "当前设备与账号绑定设备不一致";
    if (!authorized.value) return "账号尚未开通";
    return "授权有效";
  });
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
    limits: computed(() => ({})),
    serverUrl: computed(() => "https://auth.example.com"),
    connectionState: computed(() => "ready"),
    connectionText: computed(() => "已配置授权服务"),
    reasonText,
    refresh: vi.fn(),
    login: vi.fn(async () => true),
    register: vi.fn(async () => true),
    redeem: vi.fn(async () => true),
    unbindDevice: vi.fn(async () => true),
    logout: vi.fn(async () => true),
    startPolling: vi.fn(),
    stopPolling: vi.fn(),
    applyStatus: vi.fn(),
    markInvalid: vi.fn(),
  };
}

function mountDialog(auth, props = {}) {
  return mount(ClientDialogs, {
    props: {
      auth,
      authOpen: true,
      notices: null,
      ...props,
    },
    attachTo: document.body,
  });
}

describe("ClientDialogs", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("shows login and register actions in the account dialog", async () => {
    const auth = createAuth();
    const wrapper = mountDialog(auth);

    expect(document.body.textContent).toContain("登录 / 注册");
    expect(document.body.textContent).toContain("账号邮箱");

    await wrapper.getComponent(ClientDialogs);
    document.querySelectorAll(".auth-tabs button")[1].click();
    await wrapper.vm.$nextTick();
    setInputValue("input[type='email']", "user@example.com");
    setInputValue("input[type='password']", "password123");
    setInputValue("input[autocomplete='name']", "新用户");
    document.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await wrapper.vm.$nextTick();

    expect(auth.register).toHaveBeenCalledWith("user@example.com", "password123", "新用户");
  });

  it("shows cdk redeem dialog after login before activation", async () => {
    const auth = createAuth({
      status: {
        configured: true,
        authenticated: true,
        authorized: false,
        reason: "not_activated",
        account: { email: "user@example.com" },
        license: { authorized: false, reason: "not_activated" },
        device: { name: "MacBook" },
      },
    });
    const wrapper = mountDialog(auth);

    expect(document.body.textContent).toContain("兑换 CDK");
    setInputValue("input[spellcheck='false']", "INKMOMENT-1234");
    await wrapper.vm.$nextTick();
    document.querySelector(".auth-form .btn-primary").click();
    await wrapper.vm.$nextTick();

    expect(auth.redeem).toHaveBeenCalledWith("INKMOMENT-1234");
  });

  it("shows authorization status when license is valid", () => {
    const auth = createAuth({
      status: {
        configured: true,
        authenticated: true,
        authorized: true,
        reason: "active",
        account: { email: "user@example.com" },
        license: { authorized: true, reason: "active", remaining_seconds: 86400 * 5 },
        device: { name: "MacBook" },
      },
    });
    mountDialog(auth);

    expect(document.body.textContent).toContain("授权状态");
    expect(document.body.textContent).toContain("授权有效，可以继续使用当前功能");
  });

  it("shows device mismatch guidance and unbind confirmation", async () => {
    const auth = createAuth({
      status: {
        configured: true,
        authenticated: true,
        authorized: false,
        reason: "device_mismatch",
        account: { email: "user@example.com" },
        license: { authorized: false, reason: "device_mismatch" },
        device: { name: "MacBook", fingerprint: "device-a" },
      },
    });
    const wrapper = mountDialog(auth);

    expect(document.body.textContent).toContain("设备已绑定");
    expect(document.body.textContent).toContain("此账号已经绑定其他设备");

    document.querySelector(".btn-danger").click();
    await wrapper.vm.$nextTick();
    expect(document.body.textContent).toContain("设备解绑确认");

    document.querySelector(".client-confirm-dialog .btn-primary").click();
    await wrapper.vm.$nextTick();
    expect(auth.unbindDevice).toHaveBeenCalledWith("用户自助换机");
  });

  it("prioritizes device mismatch error code even when account cache is cleared", () => {
    const auth = createAuth({
      status: {
        configured: true,
        authenticated: false,
        authorized: false,
        reason: "device_mismatch",
        license: { authorized: false, reason: "device_mismatch" },
        device: { name: "MacBook", fingerprint: "device-a" },
      },
      lastErrorCode: "device_mismatch",
    });
    mountDialog(auth);

    expect(document.body.textContent).toContain("设备已绑定");
    expect(document.body.textContent).toContain("请联系管理员后台解绑");
  });

  it("shows expired authorization dialog with cdk recovery", () => {
    const auth = createAuth({
      status: {
        configured: true,
        authenticated: true,
        authorized: false,
        reason: "expired",
        account: { email: "user@example.com" },
        license: { authorized: false, reason: "expired", expires_at: 1000 },
        device: { name: "MacBook" },
      },
    });
    mountDialog(auth);

    expect(document.body.textContent).toContain("授权已过期");
    expect(document.body.textContent).toContain("新的 CDK 激活码");
  });

  it("shows maintenance and version notices from client notice payload", async () => {
    const auth = createAuth({
      status: {
        configured: true,
        authenticated: true,
        authorized: true,
        reason: "active",
        account: { email: "user@example.com" },
        license: { authorized: true, reason: "active" },
      },
    });
    const wrapper = mountDialog(auth, {
      authOpen: false,
      notices: {
        maintenance: {
          enabled: true,
          title: "今晚维护",
          message: "22:00 到 23:00 维护授权服务",
        },
        version_update: {
          enabled: true,
          title: "发现新版本",
          message: "建议升级",
          version: "1.2.0",
        },
      },
    });

    expect(document.body.textContent).toContain("维护公告");
    expect(document.body.textContent).toContain("今晚维护");

    document.querySelector(".notice-dialog .btn-ghost").click();
    await wrapper.vm.$nextTick();
    expect(document.body.textContent).toContain("版本更新");
    expect(document.body.textContent).toContain("发现新版本");
  });

  it("shows remote client notices before version update notices", async () => {
    const auth = createAuth({
      status: {
        configured: true,
        authenticated: true,
        authorized: true,
        reason: "active",
        account: { email: "user@example.com" },
        license: { authorized: true, reason: "active" },
      },
    });
    const wrapper = mountDialog(auth, {
      authOpen: false,
      notices: {
        maintenance: { enabled: false },
        remote_notices: [
          {
            id: "notice-a",
            enabled: true,
            title: "后台公告",
            body: "下载策略已经更新",
            pinned: true,
          },
        ],
        version_update: {
          enabled: true,
          title: "发现新版本",
          message: "建议升级",
          version: "1.2.0",
        },
      },
    });

    expect(document.body.textContent).toContain("系统公告");
    expect(document.body.textContent).toContain("后台公告");
    expect(document.body.textContent).toContain("下载策略已经更新");

    document.querySelector(".notice-dialog .btn-ghost").click();
    await wrapper.vm.$nextTick();

    expect(document.body.textContent).toContain("版本更新");
    expect(document.body.textContent).toContain("发现新版本");
  });
});

function setInputValue(selector, value) {
  const input = document.querySelector(selector);
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import AppFrame from "./components/AppFrame.vue";
import AppViewHost from "./components/AppViewHost.vue";
import BootShell from "./components/BootShell.vue";
import { useAppStartup } from "./composables/useAppStartup";
import { useAuthSession } from "./composables/useAuthSession";
import { useClientNotices } from "./composables/useClientNotices";
import { useDebugLogs } from "./composables/useDebugLogs";
import { useDesktopBackendMonitor } from "./composables/useDesktopBackendMonitor";
import { useFlowState } from "./composables/useFlowState";
import { useSessionReset } from "./composables/useSessionReset";
import { useTheme } from "./composables/useTheme";
import { useWorkflowCommands } from "./composables/useWorkflowCommands";

const globalBusy = ref(null);
const { resetting, resetError, resetCurrentSession } = useSessionReset();
const auth = useAuthSession();
const { clientNotices, loadClientNotices } = useClientNotices();
const { themeStyle } = useTheme();
const { currentView, startedPayload, enterProcessing, clearStartedPayload, resumeStep, enterPreview, enterArena, enterDone, enterHome } = useFlowState();
const { desktopBackendError, startDesktopBackendMonitor, stopDesktopBackendMonitor } = useDesktopBackendMonitor();
const {
  booting,
  bootMessage,
  bootError,
  authDialogOpen,
  bindAuthInvalidEvent,
  handleAuthAuthorized,
  resumeFromBackend,
  unbindAuthInvalidEvent,
} = useAppStartup({
  auth,
  enterProcessing,
  enterHome,
  resumeStep,
  clearStartedPayload,
  startDesktopBackendMonitor,
  onAuthInvalid: () => {
    resetError.value = "";
  },
});

const bannerText = computed(() => {
  if (booting.value) return bootMessage.value || "正在启动";
  if (resetting.value) return "正在回首页...";
  return resetError.value || desktopBackendError.value || bootError.value || auth.error.value;
});

const bannerError = computed(() => Boolean(
  resetError.value || desktopBackendError.value || bootError.value || auth.error.value,
));
const appInteractionLocked = computed(() => Boolean(globalBusy.value || (!booting.value && !auth.authorized.value)));

const { debugOpen, debugLoading, debugError, debugLogText, debugCopied, openDebugLogs, refreshDebugLogs, copyDebugLogs } = useDebugLogs({
  currentView,
  booting,
  bannerText,
  auth,
  desktopBackendError,
});

const { requestBackHome } = useWorkflowCommands({
  currentView,
  resetting,
  resetCurrentSession,
  clearStartedPayload,
  enterHome,
});

onMounted(() => {
  bindAuthInvalidEvent();
  loadClientNotices();
  resumeFromBackend();
});

onUnmounted(() => {
  unbindAuthInvalidEvent();
  auth.stopPolling();
  stopDesktopBackendMonitor();
});
</script>

<template>
  <AppFrame
    v-model:debug-open="debugOpen"
    v-model:auth-dialog-open="authDialogOpen"
    :theme-style="themeStyle"
    :app-interaction-locked="appInteractionLocked"
    :banner-text="bannerText"
    :banner-error="bannerError"
    :debug-loading="debugLoading"
    :debug-error="debugError"
    :debug-log-text="debugLogText"
    :debug-copied="debugCopied"
    :booting="booting"
    :auth="auth"
    :notices="clientNotices"
    :global-busy="globalBusy"
    @open-debug="openDebugLogs"
    @refresh-debug="refreshDebugLogs"
    @copy-debug="copyDebugLogs"
    @authorized="handleAuthAuthorized"
  >
    <AppViewHost
      v-if="!booting"
      :current-view="currentView"
      :started-payload="startedPayload"
      :returning-home="resetting"
      @job-started="enterProcessing"
      @back-home="requestBackHome"
      @continue-step="resumeStep"
      @enter-preview="enterPreview"
      @enter-arena="enterArena"
      @enter-done="enterDone"
      @busy-change="globalBusy = $event"
    />
    <BootShell v-else :boot-message="bootMessage" />
  </AppFrame>
</template>

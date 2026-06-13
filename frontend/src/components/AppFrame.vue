<script setup>
import { isTauriRuntime } from "../api/runtime";
import ClientDialogs from "./ClientDialogs.vue";
import DebugLogOverlay from "./DebugLogOverlay.vue";
import GlobalBusyOverlay from "./GlobalBusyOverlay.vue";

defineProps({
  themeStyle: {
    type: Object,
    default: () => ({}),
  },
  appInteractionLocked: {
    type: Boolean,
    default: false,
  },
  bannerText: {
    type: String,
    default: "",
  },
  bannerError: {
    type: Boolean,
    default: false,
  },
  debugOpen: {
    type: Boolean,
    default: false,
  },
  debugLoading: {
    type: Boolean,
    default: false,
  },
  debugError: {
    type: String,
    default: "",
  },
  debugLogText: {
    type: String,
    default: "",
  },
  debugCopied: {
    type: Boolean,
    default: false,
  },
  booting: {
    type: Boolean,
    default: false,
  },
  authDialogOpen: {
    type: Boolean,
    default: false,
  },
  auth: {
    type: Object,
    required: true,
  },
  notices: {
    type: Object,
    default: null,
  },
  globalBusy: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits([
  "update:debugOpen",
  "update:authDialogOpen",
  "open-debug",
  "refresh-debug",
  "copy-debug",
  "authorized",
]);
</script>

<template>
  <div class="theme-frame" :style="themeStyle" :inert="appInteractionLocked ? '' : null">
    <slot />

    <div v-if="bannerText" class="session-reset-banner" :class="{ error: bannerError }">{{ bannerText }}</div>
    <DebugLogOverlay
      v-if="isTauriRuntime()"
      :open="debugOpen"
      :loading="debugLoading"
      :error="debugError"
      :log-text="debugLogText"
      :copied="debugCopied"
      @open="emit('open-debug')"
      @close="emit('update:debugOpen', false)"
      @refresh="emit('refresh-debug')"
      @copy="emit('copy-debug')"
    />
    <ClientDialogs
      v-if="!booting"
      :auth-open="authDialogOpen"
      :auth="auth"
      :notices="notices"
      @update:auth-open="emit('update:authDialogOpen', $event)"
      @authorized="emit('authorized')"
    />
    <GlobalBusyOverlay :state="globalBusy" @cancel="globalBusy?.onCancel?.()" />
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { startJob } from "../api/inkmoment";
import EngineSwitch from "../components/EngineSwitch.vue";
import FolderSnapshot from "../components/FolderSnapshot.vue";
import ThemePicker from "../components/ThemePicker.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { useBranding } from "../composables/useBranding";
import { useFolderPeek } from "../composables/useFolderPeek";
import { useTheme } from "../composables/useTheme";

const { branding, loadingBranding } = useBranding();
const { themes, selectedTheme, theme } = useTheme();

const folder = ref("");
const engine = ref("fast");
const mode = ref("move");
const prescreenEnabled = ref(true);
const prescreenStrength = ref("advanced");
const faceAware = ref(true);
const thresholdNear = ref(10);
const thresholdFar = ref(6);
const nearMinutes = ref(5);
const startError = ref("");
const isStarting = ref(false);
const lastStartPayload = ref(null);

const {
  snapshot,
  statusText,
  statusState,
} = useFolderPeek(folder);

const faceAwareDisabled = computed(() => !prescreenEnabled.value || engine.value === "fast");

async function handleStart() {
  startError.value = "";
  lastStartPayload.value = null;

  if (!folder.value.trim()) {
    startError.value = "请填写文件夹路径";
    return;
  }

  if (engine.value === "tycoon") {
    startError.value = "Vue 迁移版暂未接入土豪模式模型配置，请先使用原页面。";
    return;
  }

  isStarting.value = true;
  try {
    const payload = {
      folder: folder.value.trim(),
      dry_run: false,
      wipe_cache: true,
      mode: mode.value,
      engine: engine.value,
      threshold_near: Number(thresholdNear.value),
      threshold_far: Number(thresholdFar.value),
      near_seconds: Number(nearMinutes.value) * 60,
      prescreen_enabled: prescreenEnabled.value,
      prescreen_strength: prescreenStrength.value,
      face_aware: engine.value === "expert" && faceAware.value,
      llm_model: "",
    };
    await startJob(payload);
    lastStartPayload.value = payload;
  } catch (error) {
    startError.value = error.message || "启动失败";
  } finally {
    isStarting.value = false;
  }
}
</script>

<template>
  <main class="app-shell" :style="{ '--accent': theme.accent }">
    <StatusBadge :label="statusText" :state="statusState" />

    <header class="topbar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true"></span>
        <span class="brand-name">{{ branding.app_name }}</span>
      </div>

      <div class="top-actions">
        <ThemePicker v-model="selectedTheme" :themes="themes" />
        <span class="site-tag">{{ branding.tagline }}</span>
      </div>
    </header>

    <section class="hero">
      <p class="eyebrow">{{ loadingBranding ? "加载中" : branding.hero_eyebrow }}</p>
      <h1>{{ branding.hero_title }}</h1>
      <p class="subtitle">{{ branding.hero_subtitle }}</p>
    </section>

    <form class="start-form" @submit.prevent="handleStart">
      <EngineSwitch v-model="engine" />

      <label class="field-label" for="folder-input">照片文件夹</label>
      <div class="field-row">
        <input
          id="folder-input"
          v-model="folder"
          type="text"
          placeholder="粘贴照片文件夹绝对路径"
          spellcheck="false"
          required
        >
        <button class="btn-primary" type="submit" :disabled="isStarting">
          {{ isStarting ? "启动中" : "开始" }}
        </button>
      </div>

      <FolderSnapshot :snapshot="snapshot" />

      <details class="advanced">
        <summary>更多选项</summary>
        <div class="advanced-body">
          <section class="option-section">
            <div class="option-label">归档方式</div>
            <label class="radio-row">
              <input v-model="mode" type="radio" value="move">
              <span><strong>移动</strong> · 原片直接归入 winners/ losers/</span>
            </label>
            <label class="radio-row">
              <input v-model="mode" type="radio" value="copy">
              <span><strong>复制</strong> · 原片保留，winners/ 为副本</span>
            </label>
          </section>

          <section class="option-section">
            <label class="check-row">
              <input v-model="prescreenEnabled" type="checkbox">
              <span>智能初筛 · 先自动淘汰明显的失焦 / 闭眼 / 过曝</span>
            </label>
            <label class="check-row" :class="{ 'is-disabled': faceAwareDisabled }">
              <input v-model="faceAware" type="checkbox" :disabled="faceAwareDisabled">
              <span>人脸感知 · 极速模式下自动关闭</span>
            </label>
          </section>

          <section class="option-section" :class="{ 'is-disabled': !prescreenEnabled }">
            <div class="option-label">初筛力度</div>
            <label class="radio-row">
              <input
                v-model="prescreenStrength"
                type="radio"
                value="standard"
                :disabled="!prescreenEnabled"
              >
              <span><strong>标准</strong> · 识别主体糊/严重歪斜/曝光问题</span>
            </label>
            <label class="radio-row">
              <input
                v-model="prescreenStrength"
                type="radio"
                value="advanced"
                :disabled="!prescreenEnabled"
              >
              <span><strong>进阶</strong> · 推荐档位，阈值更严</span>
            </label>
          </section>

          <section class="option-section sliders">
            <label>
              <span>同场景宽容度</span>
              <input v-model="thresholdNear" type="range" min="4" max="16" step="1">
              <output>{{ thresholdNear }}</output>
            </label>
            <label>
              <span>跨场景严格度</span>
              <input v-model="thresholdFar" type="range" min="3" max="12" step="1">
              <output>{{ thresholdFar }}</output>
            </label>
            <label>
              <span>同场景时间窗（分钟）</span>
              <input v-model="nearMinutes" type="range" min="1" max="30" step="1">
              <output>{{ nearMinutes }}</output>
            </label>
          </section>
        </div>
      </details>

      <p class="form-error">{{ startError }}</p>
      <p v-if="lastStartPayload" class="start-note">
        已向 Flask API 发起任务。Vue 迁移版的处理页将在后续迭代接入。
      </p>
    </form>
  </main>
</template>

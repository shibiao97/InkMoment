<script setup>
import { computed, onMounted } from "vue";
import { imageUrl } from "../api/http";
import StatusBadge from "../components/StatusBadge.vue";
import { formatBurstSpan, usePreviewGroups } from "../composables/usePreviewGroups";
import { useTheme } from "../composables/useTheme";

const emit = defineEmits(["back-home"]);

const { theme } = useTheme();
const {
  sections,
  title,
  statusLabel,
  statusState,
  thresholdNear,
  thresholdFar,
  nearMinutes,
  loading,
  regrouping,
  error,
  load,
  applyRegroup,
} = usePreviewGroups();

const groupCount = computed(() => {
  return sections.value.reduce((total, section) => total + section.groups.length, 0);
});

const regroupText = computed(() => {
  if (regrouping.value) return "重新分组中";
  return "用新阈值重新分组";
});

onMounted(load);
</script>

<template>
  <main class="app-shell preview-shell" :style="{ '--accent': theme.accent }">
    <StatusBadge :label="statusLabel" :state="statusState" />

    <header class="preview-topbar">
      <div>
        <p class="eyebrow">分组预览</p>
        <h1>{{ title }}</h1>
        <p class="preview-subtitle">
          金边照片是 AI 候选。这里先检查分组是否合理；如果连拍被拆散或混在一起，可以调整阈值后重新分组。
        </p>
      </div>
      <div class="preview-actions">
        <button class="btn-ghost" type="button" @click="emit('back-home')">回首页</button>
        <button class="btn-primary" type="button" :disabled="loading || regrouping" @click="load">
          刷新预览
        </button>
      </div>
    </header>

    <section class="preview-controls">
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
      <button class="btn-ghost" type="button" :disabled="loading || regrouping" @click="applyRegroup">
        {{ regroupText }}
      </button>
    </section>

    <section v-if="error" class="error-panel">
      <strong>分组预览失败</strong>
      <p>{{ error }}</p>
    </section>

    <section v-if="loading" class="preview-empty">
      正在读取分组预览...
    </section>
    <section v-else-if="!groupCount" class="preview-empty">
      没有需要人工选片的相似组，每张照片都已经独立成组。
    </section>
    <section v-else class="preview-sections">
      <div v-for="section in sections" :key="section.title" class="preview-section">
        <div class="album-chapter">
          <span class="album-chapter-name">{{ section.title }}</span>
          <span class="album-chapter-meta">{{ section.groups.length }} 组</span>
        </div>

        <div class="preview-grid">
          <article v-for="group in section.groups" :key="group.id" class="preview-card">
            <div class="pc-imgs">
              <img
                v-for="path in group.samples"
                :key="path"
                :src="imageUrl(path, 320)"
                :alt="group.id"
                :class="{ 'is-best': path === group.best_path }"
                loading="lazy"
              >
            </div>
            <div class="pc-meta">
              <span>连拍 {{ group.size }} 张</span>
              <span v-if="formatBurstSpan(group.span_seconds)" class="pc-meta-line">
                {{ formatBurstSpan(group.span_seconds) }}
              </span>
            </div>
          </article>
        </div>
      </div>
    </section>
  </main>
</template>

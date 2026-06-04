<script setup>
import { computed, onMounted } from "vue";
import { imageUrl } from "../api/http";
import ErrorPanel from "../components/ErrorPanel.vue";
import LoadingState from "../components/LoadingState.vue";
import StatusBadge from "../components/StatusBadge.vue";
import WorkflowSidebar from "../components/WorkflowSidebar.vue";
import { formatBurstSpan, usePreviewGroups } from "../composables/usePreviewGroups";

defineProps({
  returningHome: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["back-home", "continue-arena"]);

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
  <main class="app-shell studio-shell flow-workbench preview-shell">
    <WorkflowSidebar
      active-step="preview"
      summary-label="分组预览"
      :summary-value="`${groupCount.toLocaleString()} 组`"
      :summary-detail="`${nearMinutes} 分钟时间窗`"
    />

    <section class="studio-main flow-main">
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
          <button class="btn-ghost" type="button" :disabled="returningHome" @click="emit('back-home')">
            {{ returningHome ? "返回中" : "回首页" }}
          </button>
          <button class="btn-ghost" type="button" :disabled="loading || regrouping" @click="load">
            刷新预览
          </button>
          <button class="btn-primary" type="button" :disabled="loading || regrouping" @click="emit('continue-arena')">
            继续选片
          </button>
        </div>
      </header>

      <ErrorPanel title="分组预览失败" :message="error" />

      <section class="preview-workspace">
        <div class="preview-list-panel">
          <LoadingState
            v-if="loading"
            title="正在读取分组预览"
            description="正在加载连拍分组和 AI 候选照片。"
          />
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
        </div>

        <aside class="preview-controls">
          <div class="panel-title">
            <div>
              <p class="eyebrow">重新分组</p>
              <h2>调整相似度阈值</h2>
            </div>
          </div>
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
        </aside>
      </section>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted } from "vue";
import { imageUrl } from "../api/http";
import StatusBadge from "../components/StatusBadge.vue";
import { useDoneResults } from "../composables/useDoneResults";
import { useTheme } from "../composables/useTheme";

const emit = defineEmits(["back-home", "continue-arena"]);

const { theme } = useTheme();
const {
  status,
  winners,
  skipped,
  sections,
  total,
  kept,
  rejected,
  subtitle,
  statusLabel,
  statusState,
  loading,
  opening,
  error,
  load,
  openOutputFolder,
} = useDoneResults();

const winnersPath = computed(() => status.value?.folder ? `${status.value.folder}/winners` : "");
const losersPath = computed(() => status.value?.folder ? `${status.value.folder}/losers` : "");
const hasUnfinished = computed(() => (status.value?.unfinished_groups || 0) > 0);

onMounted(load);
</script>

<template>
  <main class="app-shell done-shell-vue" :style="{ '--accent': theme.accent }">
    <StatusBadge :label="statusLabel" :state="statusState" />

    <header class="done-topbar">
      <div>
        <p class="eyebrow">完成</p>
        <h1>这些是你留下的。</h1>
        <p class="done-subtitle">{{ subtitle }}</p>
      </div>
      <div class="done-actions">
        <button class="btn-ghost" type="button" :disabled="opening" @click="openOutputFolder">
          {{ opening ? "打开中" : "打开文件夹" }}
        </button>
        <button class="btn-ghost" type="button" @click="emit('back-home')">回首页</button>
      </div>
    </header>

    <section class="done-hero-panel">
      <strong>{{ total.toLocaleString() }}</strong>
      <span>→</span>
      <strong class="accent">{{ kept.toLocaleString() }}</strong>
    </section>

    <section class="done-stats-grid">
      <div>
        <strong>{{ kept.toLocaleString() }}</strong>
        <span>胜出</span>
      </div>
      <div>
        <strong>{{ rejected.toLocaleString() }}</strong>
        <span>放手</span>
      </div>
      <div>
        <strong>{{ status?.multi_groups || 0 }}</strong>
        <span>连拍组</span>
      </div>
      <div>
        <strong>{{ skipped.length }}</strong>
        <span>无法读取</span>
      </div>
    </section>

    <section v-if="error" class="error-panel">
      <strong>结果读取失败</strong>
      <p>{{ error }}</p>
    </section>

    <section class="done-paths-vue">
      <div>
        <span>胜出</span>
        <code>{{ winnersPath }}</code>
      </div>
      <div>
        <span>淘汰</span>
        <code>{{ losersPath }}</code>
      </div>
    </section>

    <section v-if="hasUnfinished" class="unfinished-notice-vue">
      <span>{{ status.unfinished_groups }} 组之前跳过了。</span>
      <button class="btn-primary" type="button" @click="emit('continue-arena')">回去处理</button>
    </section>

    <section v-if="loading" class="done-empty">
      正在读取完成结果...
    </section>
    <section v-else-if="!winners.length" class="done-empty">
      暂时没有胜出的照片。
    </section>
    <section v-else class="done-winners">
      <div class="winners-section-head">
        <h2 class="winners-section-title">这次留下的</h2>
        <span class="winners-count">{{ winners.length }} 张</span>
      </div>

      <div v-for="section in sections" :key="section.title" class="done-section">
        <div class="album-chapter">
          <span class="album-chapter-name">{{ section.title }}</span>
          <span class="album-chapter-meta">{{ section.items.length }} 张</span>
        </div>
        <div class="done-grid">
          <article v-for="item in section.items" :key="item.path" class="done-card">
            <img :src="imageUrl(item.path, 520)" :alt="item.name" loading="lazy">
            <span>{{ item.group_size > 1 ? `从 ${item.group_size} 张里` : "独张" }}</span>
          </article>
        </div>
      </div>
    </section>

    <details v-if="skipped.length" class="done-skipped">
      <summary>无法读取的照片（{{ skipped.length }}）</summary>
      <ul>
        <li v-for="item in skipped.slice(-50).reverse()" :key="`${item.path}-${item.reason}`">
          <span>{{ item.path.split(/[\\/]/).pop() }}</span>
          <code>{{ item.reason }}</code>
        </li>
      </ul>
    </details>
  </main>
</template>

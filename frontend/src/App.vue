<script setup>
import { computed, onMounted, ref } from "vue";

const themes = [
  { id: "garden", label: "小花园", accent: "#78a881" },
  { id: "notebook", label: "手账纸感", accent: "#8fae9a" },
  { id: "film", label: "胶片回忆", accent: "#d49b50" },
  { id: "cafe", label: "清晨咖啡馆", accent: "#e98f7e" },
  { id: "studio", label: "暖木工作室", accent: "#9a7651" },
];

const selectedTheme = ref("garden");
const branding = ref({
  app_name: "影刻",
  title_suffix: "InkMoment",
  tagline: "本地运行 · 不上传",
  hero_eyebrow: "Vue 迁移预览",
  hero_title: "桌面化之前，先把前端拆成组件。",
  hero_subtitle: "这一版保留 Flask API，只新增 Vue + Vite 的迁移骨架。",
});
const loadingBranding = ref(true);

const theme = computed(() => {
  return themes.find((item) => item.id === selectedTheme.value) || themes[0];
});

async function loadBranding() {
  loadingBranding.value = true;
  try {
    const response = await fetch("/api/branding");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    branding.value = { ...branding.value, ...(await response.json()) };
  } catch (error) {
    console.warn("品牌配置加载失败，使用 Vue 迁移默认文案:", error);
  } finally {
    loadingBranding.value = false;
  }
}

onMounted(loadBranding);
</script>

<template>
  <main class="app-shell" :style="{ '--accent': theme.accent }">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true"></span>
        <span class="brand-name">{{ branding.app_name }}</span>
      </div>

      <label class="theme-picker">
        <span>风格</span>
        <select v-model="selectedTheme" aria-label="选择页面风格">
          <option v-for="item in themes" :key="item.id" :value="item.id">
            {{ item.label }}
          </option>
        </select>
      </label>
    </header>

    <section class="hero">
      <p class="eyebrow">{{ loadingBranding ? "加载中" : branding.hero_eyebrow }}</p>
      <h1>{{ branding.hero_title }}</h1>
      <p class="subtitle">{{ branding.hero_subtitle }}</p>
    </section>

    <section class="migration-board" aria-label="迁移阶段">
      <article>
        <span class="step">01</span>
        <h2>Vue 前端骨架</h2>
        <p>先建立 Vite 开发服务器、API 代理和组件目录，保留现有静态页面作为稳定入口。</p>
      </article>
      <article>
        <span class="step">02</span>
        <h2>Flask API 模块化</h2>
        <p>后端继续承载 Python 图像能力，逐步拆出 routes / services，保持接口兼容。</p>
      </article>
      <article>
        <span class="step">03</span>
        <h2>Tauri 桌面壳</h2>
        <p>当前端和 API 边界稳定后，再用 Tauri 启动 Python sidecar 并打包桌面应用。</p>
      </article>
    </section>
  </main>
</template>

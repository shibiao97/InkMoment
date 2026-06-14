<script setup>
import WorkflowSidebar from "./WorkflowSidebar.vue";

defineProps({
  bootMessage: {
    type: String,
    default: "正在启动本地服务...",
  },
});
</script>

<template>
  <main class="app-shell studio-shell flow-workbench app-boot-shell">
    <WorkflowSidebar
      active-step="landing"
      summary-label="启动状态"
      summary-value="初始化中"
      summary-detail="本地服务准备中"
    />

    <section class="studio-main flow-main flow-main-stack boot-main">
      <header class="flow-hero boot-hero">
        <div>
          <p class="eyebrow">InkMoment</p>
          <h1>{{ bootMessage }}</h1>
          <p class="subtitle">正在连接本地分析引擎、载入授权状态与照片工作台。</p>
        </div>
      </header>

      <section class="studio-panel app-boot-panel">
        <span class="wait-spinner" aria-hidden="true"></span>
        <div>
          <p class="eyebrow">启动检查</p>
          <h2>准备真实桌面工作流</h2>
          <p>完成后会自动进入导入配置或继续上一次任务。</p>
        </div>
      </section>
    </section>

    <aside class="studio-inspector flow-inspector boot-inspector">
      <section class="inspector-card inspector-status-card">
        <p class="eyebrow">Runtime</p>
        <h2>本地运行</h2>
        <p>照片分析在当前设备完成，不上传原片。</p>
      </section>
      <section class="inspector-card boot-checklist">
        <span>后端服务</span>
        <span>授权会话</span>
        <span>主题资源</span>
      </section>
    </aside>
  </main>
</template>

<script setup>
defineProps({
  faceAwareDisabled: {
    type: Boolean,
    required: true,
  },
});

const mode = defineModel("mode", { type: String, required: true });
const prescreenEnabled = defineModel("prescreenEnabled", { type: Boolean, required: true });
const faceAware = defineModel("faceAware", { type: Boolean, required: true });
const prescreenStrength = defineModel("prescreenStrength", { type: String, required: true });
const thresholdNear = defineModel("thresholdNear", { type: [Number, String], required: true });
const thresholdFar = defineModel("thresholdFar", { type: [Number, String], required: true });
const nearMinutes = defineModel("nearMinutes", { type: [Number, String], required: true });
</script>

<template>
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
</template>

<script setup>
import { computed, onMounted } from "vue";
import { imageUrl } from "../api/http";
import ErrorPanel from "../components/ErrorPanel.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePrescreenReview } from "../composables/usePrescreenReview";
import { useTheme } from "../composables/useTheme";

defineProps({
  returningHome: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["back-home", "continue-preview"]);

const { theme } = useTheme();
const {
  activeReason,
  filteredItems,
  pendingItems,
  reasonFilters,
  stats,
  loading,
  error,
  confirming,
  confirmResult,
  grouping,
  isRestoring,
  load,
  restoreOne,
  restoreAllPending,
  confirmReview,
} = usePrescreenReview();

const statusLabel = computed(() => {
  if (grouping.value?.status === "running") return "正在生成分组";
  if (grouping.value?.status === "done") return "初筛已确认";
  if (error.value || grouping.value?.status === "error") return "需要处理";
  if (loading.value) return "读取初筛列表";
  return `${stats.value.pending.toLocaleString()} 张待复核`;
});

const statusState = computed(() => {
  if (error.value || grouping.value?.status === "error") return "error";
  if (loading.value || confirming.value || grouping.value?.status === "running") return "busy";
  if (grouping.value?.status === "done" || confirmResult.value) return "done";
  return "idle";
});

const confirmTitle = computed(() => {
  if (grouping.value?.status === "running") return "正在整理分组";
  if (grouping.value?.status === "done") return "复核已完成";
  if (grouping.value?.status === "error") return "分组生成失败";
  return "确认后继续";
});

const confirmDescription = computed(() => {
  if (grouping.value?.status === "running") {
    return "后台正在把保留照片重新分组，完成后就可以进入后续选片流程。";
  }
  if (grouping.value?.status === "done") {
    return `已生成 ${grouping.value.total || 0} 个分组，其中 ${grouping.value.multi || 0} 组需要继续人工选择。`;
  }
  if (grouping.value?.status === "error") {
    return grouping.value.error || "请回首页重新开始，或先使用原页面继续处理。";
  }
  return `${stats.value.pending} 张会保持放手，${stats.value.restored} 张会回到后续分组。`;
});

const hasPending = computed(() => pendingItems.value.length > 0);

onMounted(load);
</script>

<template>
  <main class="app-shell prescreen-shell" :style="{ '--accent': theme.accent }">
    <StatusBadge :label="statusLabel" :state="statusState" />

    <header class="prescreen-topbar">
      <div>
        <p class="eyebrow">初筛复核</p>
        <h1>先把明显误伤的照片捞回来</h1>
        <p class="prescreen-subtitle">
          自动初筛只负责拦下失焦、闭眼、过曝等明显问题。你可以把想保留的照片恢复到后续分组。
        </p>
      </div>
      <div class="prescreen-actions">
        <button class="btn-ghost" type="button" :disabled="returningHome" @click="emit('back-home')">
          {{ returningHome ? "返回中" : "回首页" }}
        </button>
        <button
          class="btn-ghost"
          type="button"
          :disabled="loading || confirming"
          @click="load"
        >
          刷新
        </button>
      </div>
    </header>

    <section class="prescreen-summary">
      <div>
        <strong>{{ stats.totalPhotos.toLocaleString() }}</strong>
        <span>本轮照片</span>
      </div>
      <div>
        <strong>{{ stats.rejected.toLocaleString() }}</strong>
        <span>初筛放手</span>
      </div>
      <div>
        <strong>{{ stats.restored.toLocaleString() }}</strong>
        <span>已恢复</span>
      </div>
      <div>
        <strong>{{ stats.pending.toLocaleString() }}</strong>
        <span>仍待确认</span>
      </div>
    </section>

    <ErrorPanel title="读取或操作失败" :message="error" />

    <section class="prescreen-confirm">
      <div>
        <span class="step-kind">continue</span>
        <h2>{{ confirmTitle }}</h2>
        <p>{{ confirmDescription }}</p>
      </div>
      <div v-if="grouping?.groups?.length" class="grouping-samples">
        <article v-for="group in grouping.groups.slice(0, 4)" :key="group.id">
          <strong>{{ group.size }}</strong>
          <span>张 / {{ group.id }}</span>
        </article>
      </div>
      <div class="prescreen-confirm-actions">
        <button
          class="btn-ghost"
          type="button"
          :disabled="!hasPending || loading || confirming"
          @click="restoreAllPending"
        >
          全部保留
        </button>
        <button
          v-if="grouping?.status === 'done' || (confirmResult && !confirmResult.async)"
          class="btn-primary"
          type="button"
          @click="emit('continue-preview')"
        >
          进入分组预览
        </button>
        <button
          v-else
          class="btn-primary"
          type="button"
          :disabled="loading || confirming || grouping?.status === 'running'"
          @click="confirmReview"
        >
          {{ confirming ? "确认中" : "确认并继续" }}
        </button>
      </div>
    </section>

    <nav v-if="reasonFilters.length > 1" class="reason-filters" aria-label="初筛原因">
      <button
        v-for="filter in reasonFilters"
        :key="filter.id"
        type="button"
        class="reason-chip"
        :class="{ active: activeReason === filter.id }"
        @click="activeReason = filter.id"
      >
        <span>{{ filter.label }}</span>
        <strong>{{ filter.count }}</strong>
      </button>
    </nav>

    <section v-if="loading" class="prescreen-empty">
      正在读取初筛结果...
    </section>
    <section v-else-if="!filteredItems.length" class="prescreen-empty">
      当前没有需要复核的自动放手照片。
    </section>
    <section v-else class="prescreen-grid">
      <article
        v-for="item in filteredItems"
        :key="item.key"
        class="prescreen-card"
        :class="{ restored: item.restored }"
      >
        <img :src="imageUrl(item.path, 520)" :alt="item.name" loading="lazy">
        <div class="prescreen-card-body">
          <div>
            <h2>{{ item.name }}</h2>
            <p>{{ item.reason }}</p>
          </div>
          <button
            class="btn-ghost"
            type="button"
            :disabled="item.restored || isRestoring(item) || confirming"
            @click="restoreOne(item)"
          >
            {{ item.restored ? "已恢复" : isRestoring(item) ? "恢复中" : "保留" }}
          </button>
        </div>
      </article>
    </section>
  </main>
</template>

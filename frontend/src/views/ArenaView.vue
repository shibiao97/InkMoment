<script setup>
import { computed, onMounted } from "vue";
import { imageUrl } from "../api/http";
import StatusBadge from "../components/StatusBadge.vue";
import { formatMeta, useArenaGroup } from "../composables/useArenaGroup";
import { useTheme } from "../composables/useTheme";

const emit = defineEmits(["back-home"]);

const { theme } = useTheme();
const {
  status,
  group,
  done,
  loading,
  busy,
  error,
  overallPercent,
  groupPercent,
  statusLabel,
  statusState,
  load,
  choose,
  skip,
  undo,
} = useArenaGroup();

const title = computed(() => {
  if (done.value) return "这轮选片已经完成";
  if (!group.value) return "准备进入选片";
  if (group.value.earliest_dt) return `连拍 ${group.value.total_images || 0} 张`;
  return `组 #${group.value.id_short || ""}`;
});

const leftMeta = computed(() => formatMeta(group.value?.left_meta, group.value?.right_meta));
const rightMeta = computed(() => formatMeta(group.value?.right_meta, group.value?.left_meta));
const canUndo = computed(() => Boolean(group.value?.can_undo));
const disableActions = computed(() => loading.value || busy.value || done.value || !group.value);

function basename(path) {
  if (!path) return "无图";
  return path.split(/[\\/]/).pop() || path;
}

function chooseLeft() {
  return choose(group.value?.right ? "right" : "neither");
}

function chooseRight() {
  if (!group.value?.right) return false;
  return choose("left");
}

onMounted(load);
</script>

<template>
  <main class="app-shell arena-shell" :style="{ '--accent': theme.accent }">
    <StatusBadge :label="statusLabel" :state="statusState" />

    <header class="arena-topbar">
      <div>
        <p class="eyebrow">人工选片</p>
        <h1>{{ title }}</h1>
        <p class="arena-folder">{{ status?.folder }}</p>
      </div>
      <div class="arena-actions">
        <button class="btn-ghost" type="button" @click="emit('back-home')">回首页</button>
        <button class="btn-ghost" type="button" :disabled="loading || busy" @click="load">刷新</button>
      </div>
    </header>

    <section class="arena-progress">
      <div>
        <span>总进度</span>
        <strong>{{ status?.finished_multi_groups || 0 }} / {{ status?.multi_groups || 0 }} 组</strong>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: `${overallPercent}%` }"></div>
      </div>
      <div>
        <span>当前组</span>
        <strong>{{ group?.decided || 0 }} / {{ group?.total_images || 0 }} 已决</strong>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: `${groupPercent}%` }"></div>
      </div>
    </section>

    <section v-if="error" class="error-panel">
      <strong>选片操作失败</strong>
      <p>{{ error }}</p>
    </section>

    <section v-if="done" class="arena-empty">
      选片已经完成。完成页还在迁移中，当前可先回首页或使用原页面查看结果。
    </section>
    <section v-else-if="loading" class="arena-empty">
      正在读取当前组...
    </section>
    <section v-else-if="!group" class="arena-empty">
      暂时没有可选的分组。
    </section>
    <section v-else class="arena-stage">
      <article class="arena-side">
        <div class="arena-photo">
          <img v-if="group.left" :src="imageUrl(group.left, 1200)" :alt="basename(group.left)">
        </div>
        <div class="arena-meta">
          <h2>{{ basename(group.left) }}</h2>
          <div class="meta-pills">
            <span
              v-for="item in leftMeta"
              :key="item.key"
              :class="{ diff: item.different }"
            >
              {{ item.value }}
            </span>
          </div>
        </div>
        <button class="btn-primary" type="button" :disabled="disableActions" @click="chooseLeft">
          留左边
        </button>
      </article>

      <article class="arena-side" :class="{ empty: !group.right }">
        <div class="arena-photo">
          <img v-if="group.right" :src="imageUrl(group.right, 1200)" :alt="basename(group.right)">
          <span v-else>右侧无图</span>
        </div>
        <div class="arena-meta">
          <h2>{{ basename(group.right) }}</h2>
          <div class="meta-pills">
            <span
              v-for="item in rightMeta"
              :key="item.key"
              :class="{ diff: item.different }"
            >
              {{ item.value }}
            </span>
          </div>
        </div>
        <button class="btn-primary" type="button" :disabled="disableActions || !group.right" @click="chooseRight">
          留右边
        </button>
      </article>
    </section>

    <section v-if="group && !done" class="arena-command-bar">
      <button class="btn-ghost" type="button" :disabled="disableActions || !group.right" @click="choose('neither')">
        都保留
      </button>
      <button class="btn-ghost" type="button" :disabled="disableActions" @click="choose('both')">
        都放手
      </button>
      <button class="btn-ghost" type="button" :disabled="disableActions" @click="skip">
        稍后再选
      </button>
      <button class="btn-ghost" type="button" :disabled="disableActions || !canUndo" @click="undo">
        撤销
      </button>
    </section>

    <section v-if="group?.members?.length" class="arena-strip">
      <article
        v-for="member in group.members"
        :key="member.path"
        class="strip-cell"
        :class="`strip-${member.status}`"
        :title="member.name"
      >
        <img :src="imageUrl(member.path, 160)" :alt="member.name" loading="lazy">
      </article>
    </section>
  </main>
</template>

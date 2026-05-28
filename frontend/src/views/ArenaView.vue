<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { imageUrl } from "../api/http";
import StatusBadge from "../components/StatusBadge.vue";
import { formatMeta, useArenaGroup } from "../composables/useArenaGroup";
import { useTheme } from "../composables/useTheme";

defineProps({
  returningHome: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["back-home", "done"]);

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
  if (group.value.left && !group.value.right && !group.value.finished) return "复核这张照片";
  if (group.value.earliest_dt) return `连拍 ${group.value.total_images || 0} 张`;
  return `组 #${group.value.id_short || ""}`;
});

const leftMeta = computed(() => formatMeta(group.value?.left_meta, group.value?.right_meta));
const rightMeta = computed(() => formatMeta(group.value?.right_meta, group.value?.left_meta));
const canUndo = computed(() => Boolean(group.value?.can_undo));
const disableActions = computed(() => loading.value || busy.value || done.value || !group.value);
const isSingleReview = computed(() => Boolean(group.value?.left && !group.value?.right && !group.value?.finished));
const zoomTarget = ref(null);
const zoomScale = ref(1);
const zoomedPath = computed(() => {
  if (!group.value || !zoomTarget.value) return "";
  return zoomTarget.value === "left" ? group.value.left : group.value.right;
});
const zoomedName = computed(() => basename(zoomedPath.value));

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

function openZoom(side) {
  if (!group.value?.[side]) return;
  zoomTarget.value = side;
  zoomScale.value = 1;
}

function closeZoom() {
  zoomTarget.value = null;
  zoomScale.value = 1;
}

function setZoom(nextScale) {
  zoomScale.value = Math.max(1, Math.min(4, Number(nextScale.toFixed(2))));
}

function handleKeydown(event) {
  if (event.defaultPrevented) return;
  const target = event.target;
  const isTyping = target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
  if (isTyping) return;

  if (event.key === "Escape" && zoomTarget.value) {
    event.preventDefault();
    closeZoom();
    return;
  }
  if (zoomTarget.value) {
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      setZoom(zoomScale.value + 0.5);
    } else if (event.key === "-" || event.key === "_") {
      event.preventDefault();
      setZoom(zoomScale.value - 0.5);
    } else if (event.key === "0") {
      event.preventDefault();
      setZoom(1);
    }
    return;
  }

  if (disableActions.value) return;
  const key = event.key.toLowerCase();
  if (isSingleReview.value) {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight" || key === "l" || key === "r") {
      event.preventDefault();
      choose("neither");
    } else if (key === "b" || key === "n") {
      event.preventDefault();
      choose("both");
    } else if (key === "s") {
      event.preventDefault();
      skip();
    } else if (key === "u" && canUndo.value) {
      event.preventDefault();
      undo();
    } else if (key === "1") {
      event.preventDefault();
      openZoom("left");
    }
    return;
  }

  if (event.key === "ArrowLeft" || key === "l") {
    event.preventDefault();
    chooseLeft();
  } else if (event.key === "ArrowRight" || key === "r") {
    event.preventDefault();
    chooseRight();
  } else if (key === "b") {
    event.preventDefault();
    choose("neither");
  } else if (key === "n") {
    event.preventDefault();
    choose("both");
  } else if (key === "s") {
    event.preventDefault();
    skip();
  } else if (key === "u" && canUndo.value) {
    event.preventDefault();
    undo();
  } else if (key === "1") {
    event.preventDefault();
    openZoom("left");
  } else if (key === "2") {
    event.preventDefault();
    openZoom("right");
  }
}

onMounted(() => {
  load();
  window.addEventListener("keydown", handleKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleKeydown);
});
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
        <button class="btn-ghost" type="button" :disabled="returningHome" @click="emit('back-home')">
          {{ returningHome ? "返回中" : "回首页" }}
        </button>
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
      <span>选片已经完成。</span>
      <button class="btn-primary" type="button" @click="emit('done')">查看结果</button>
    </section>
    <section v-else-if="loading" class="arena-empty">
      正在读取当前组...
    </section>
    <section v-else-if="!group" class="arena-empty">
      暂时没有可选的分组。
    </section>
    <section v-else class="arena-stage" :class="{ 'single-review': isSingleReview }">
      <article class="arena-side">
        <div class="arena-photo">
          <button
            v-if="group.left"
            class="arena-photo-button"
            type="button"
            @click="openZoom('left')"
          >
            <img :src="imageUrl(group.left, 1200)" :alt="basename(group.left)">
          </button>
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
          {{ isSingleReview ? "保留这张" : "留左边" }}
        </button>
      </article>

      <article v-if="!isSingleReview" class="arena-side" :class="{ empty: !group.right }">
        <div class="arena-photo">
          <button
            v-if="group.right"
            class="arena-photo-button"
            type="button"
            @click="openZoom('right')"
          >
            <img :src="imageUrl(group.right, 1200)" :alt="basename(group.right)">
          </button>
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
      <button class="btn-ghost" type="button" :disabled="disableActions || (!isSingleReview && !group.right)" @click="choose('neither')">
        {{ isSingleReview ? "保留这张" : "都保留" }}
      </button>
      <button class="btn-ghost" type="button" :disabled="disableActions" @click="choose('both')">
        {{ isSingleReview ? "放手这张" : "都放手" }}
      </button>
      <button class="btn-ghost" type="button" :disabled="disableActions" @click="skip">
        稍后再选
      </button>
      <button class="btn-ghost" type="button" :disabled="disableActions || !canUndo" @click="undo">
        撤销
      </button>
    </section>

    <section v-if="group && !done" class="arena-shortcuts">
      <template v-if="isSingleReview">
        <span>←/→ 保留</span>
        <span>B/N 放手</span>
        <span>S 稍后</span>
        <span>U 撤销</span>
        <span>1 放大</span>
      </template>
      <template v-else>
        <span>←/L 留左</span>
        <span>→/R 留右</span>
        <span>B 都保留</span>
        <span>N 都放手</span>
        <span>S 稍后</span>
        <span>U 撤销</span>
        <span>1/2 放大</span>
      </template>
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

    <Teleport to="body">
      <div
        v-if="zoomTarget && zoomedPath"
        class="zoom-overlay"
        role="dialog"
        aria-modal="true"
        @click.self="closeZoom"
      >
        <div class="zoom-topbar">
          <div>
            <span>{{ zoomTarget === "left" ? "左图" : "右图" }}</span>
            <strong>{{ zoomedName }}</strong>
          </div>
          <div class="zoom-actions">
            <button class="btn-ghost" type="button" @click="setZoom(zoomScale - 0.5)">缩小</button>
            <button class="btn-ghost" type="button" @click="setZoom(1)">{{ zoomScale.toFixed(1) }}×</button>
            <button class="btn-ghost" type="button" @click="setZoom(zoomScale + 0.5)">放大</button>
            <button class="btn-primary" type="button" @click="closeZoom">关闭</button>
          </div>
        </div>
        <div class="zoom-stage">
          <img
            :src="imageUrl(zoomedPath, 1800)"
            :alt="zoomedName"
            :style="{ transform: `scale(${zoomScale})` }"
          >
        </div>
      </div>
    </Teleport>
  </main>
</template>

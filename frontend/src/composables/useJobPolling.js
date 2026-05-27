import { computed, onBeforeUnmount, ref } from "vue";
import { cancelJob, getJob } from "../api/inkmoment";

const POLL_INTERVAL_MS = 700;

function formatElapsed(seconds) {
  if (seconds == null || Number.isNaN(seconds) || seconds < 0) return "";
  if (seconds < 60) return `${seconds.toFixed(1)} 秒`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds - minutes * 60);
  return `${minutes} 分 ${rest} 秒`;
}

export function useJobPolling() {
  const job = ref(null);
  const events = ref([]);
  const error = ref("");
  const isPolling = ref(false);
  const isCancelling = ref(false);
  const pollFailStreak = ref(0);
  let timer = null;
  let eventSeq = 0;

  const progressPercent = computed(() => {
    if (!job.value?.total) return 0;
    return Math.min(100, Math.round((job.value.done / job.value.total) * 100));
  });

  const elapsedText = computed(() => formatElapsed(job.value?.elapsed || 0));

  const isTerminal = computed(() => {
    return ["done", "error", "cancelled", "idle"].includes(job.value?.status);
  });

  function mergeEvents(nextEvents = []) {
    for (const event of nextEvents) {
      if (!event?.seq || event.seq <= eventSeq) continue;
      events.value.push(event);
      eventSeq = event.seq;
    }
    if (events.value.length > 80) {
      events.value = events.value.slice(-80);
    }
  }

  async function refresh() {
    try {
      const data = await getJob(eventSeq);
      pollFailStreak.value = 0;
      error.value = "";
      job.value = data;
      mergeEvents(data.events || []);
      if (typeof data.event_seq === "number" && data.event_seq > eventSeq && !data.events?.length) {
        eventSeq = data.event_seq;
      }
      if (isTerminal.value) stop();
    } catch (err) {
      pollFailStreak.value += 1;
      if (pollFailStreak.value >= 4) {
        error.value = err.message || "和后台失联了";
      }
    }
  }

  function start() {
    stop();
    isPolling.value = true;
    refresh();
    timer = window.setInterval(refresh, POLL_INTERVAL_MS);
  }

  function stop() {
    if (timer) {
      window.clearInterval(timer);
      timer = null;
    }
    isPolling.value = false;
  }

  async function requestCancel() {
    isCancelling.value = true;
    try {
      await cancelJob();
      await refresh();
    } finally {
      isCancelling.value = false;
    }
  }

  function reset() {
    stop();
    job.value = null;
    events.value = [];
    error.value = "";
    pollFailStreak.value = 0;
    eventSeq = 0;
  }

  onBeforeUnmount(stop);

  return {
    job,
    events,
    error,
    isPolling,
    isCancelling,
    progressPercent,
    elapsedText,
    start,
    stop,
    refresh,
    reset,
    requestCancel,
  };
}

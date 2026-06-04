import { computed, onBeforeUnmount, ref } from "vue";
import { cancelJob, getJob, streamJob } from "../api/inkmoment";

const POLL_INTERVAL_MS = 700;
const TERMINAL_STATUSES = new Set(["done", "error", "cancelled", "idle"]);

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
  const isStreaming = ref(false);
  const isCancelling = ref(false);
  const pollFailStreak = ref(0);
  let timer = null;
  let eventSource = null;
  let eventSeq = 0;
  let currentTaskId = "";
  let terminalBackfillPromise = null;
  let eventGeneration = 0;

  const progressPercent = computed(() => {
    if (!job.value?.total) return 0;
    return Math.min(100, Math.round((job.value.done / job.value.total) * 100));
  });

  const elapsedText = computed(() => formatElapsed(job.value?.elapsed || 0));

  const isTerminal = computed(() => {
    return TERMINAL_STATUSES.has(job.value?.status);
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

  function resetEventState() {
    events.value = [];
    eventSeq = 0;
    currentTaskId = "";
    eventGeneration += 1;
    terminalBackfillPromise = null;
  }

  function syncTaskCursor(data) {
    const nextTaskId = data?.task_id ? String(data.task_id) : "";
    if (!nextTaskId) return;
    if (currentTaskId && currentTaskId !== nextTaskId) {
      events.value = [];
      eventSeq = 0;
      eventGeneration += 1;
    }
    currentTaskId = nextTaskId;
  }

  function applyJobPayload(data) {
    pollFailStreak.value = 0;
    error.value = "";
    syncTaskCursor(data);
    job.value = data;
    mergeEvents(data.events || []);
    const terminal = isTerminalPayload(data);
    if (!terminal && typeof data.event_seq === "number" && data.event_seq > eventSeq && !data.events?.length) {
      eventSeq = data.event_seq;
    }
    if (terminal) {
      backfillTerminalEvents(data);
      stop();
    }
  }

  function isTerminalPayload(data) {
    return TERMINAL_STATUSES.has(data?.status);
  }

  function shouldBackfillTerminalEvents(data) {
    return (
      isTerminalPayload(data)
      && events.value.length === 0
      && !data.events?.length
      && Number(data.event_seq || 0) > 0
    );
  }

  function replaceEventHistory(nextEvents = []) {
    if (!nextEvents.length || nextEvents.length <= events.value.length) return;
    events.value = [];
    eventSeq = 0;
    mergeEvents([...nextEvents].sort((left, right) => (left.seq || 0) - (right.seq || 0)));
  }

  function backfillTerminalEvents(data) {
    if (!shouldBackfillTerminalEvents(data) || terminalBackfillPromise) return;
    const expectedTaskId = data?.task_id ? String(data.task_id) : currentTaskId;
    const generation = eventGeneration;
    const request = getJob(0)
      .then((snapshot) => {
        if (generation !== eventGeneration) return;
        const snapshotTaskId = snapshot?.task_id ? String(snapshot.task_id) : "";
        if (expectedTaskId && snapshotTaskId && snapshotTaskId !== expectedTaskId) return;
        syncTaskCursor(snapshot);
        job.value = snapshot || data;
        replaceEventHistory(snapshot?.events || []);
      })
      .catch((err) => {
        if (generation !== eventGeneration) return;
        if (events.value.length === 0) {
          error.value = err.message || "读取照片墙记录失败";
        }
      })
      .finally(() => {
        if (terminalBackfillPromise === request) {
          terminalBackfillPromise = null;
        }
      });
    terminalBackfillPromise = request;
  }

  async function refresh() {
    try {
      const data = await getJob(eventSeq);
      applyJobPayload(data);
    } catch (err) {
      pollFailStreak.value += 1;
      if (pollFailStreak.value >= 4) {
        error.value = err.message || "和后台失联了";
      }
    }
  }

  function start() {
    stop();
    error.value = "";
    resetEventState();
    if (!startStreaming()) {
      startPolling();
    }
  }

  function startStreaming() {
    const source = streamJob(eventSeq);
    if (!source) return false;
    eventSource = source;
    isStreaming.value = true;
    source.addEventListener("job", (event) => {
      try {
        applyJobPayload(JSON.parse(event.data || "{}"));
      } catch (err) {
        error.value = err.message || "后台事件解析失败";
      }
    });
    source.onerror = () => {
      closeStream();
      if (!isTerminal.value) startPolling();
    };
    return true;
  }

  function startPolling() {
    isPolling.value = true;
    refresh();
    timer = window.setInterval(refresh, POLL_INTERVAL_MS);
  }

  function stop() {
    closeStream();
    if (timer) {
      window.clearInterval(timer);
      timer = null;
    }
    isPolling.value = false;
  }

  function closeStream() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    isStreaming.value = false;
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
    error.value = "";
    pollFailStreak.value = 0;
    resetEventState();
  }

  onBeforeUnmount(stop);

  return {
    job,
    events,
    error,
    isPolling,
    isStreaming,
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

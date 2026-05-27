import { ref, watch } from "vue";
import { peekFolder } from "../api/inkmoment";

export function useFolderPeek(folder) {
  const snapshot = ref(null);
  const statusText = ref("引擎就绪");
  const statusState = ref("idle");
  const loading = ref(false);
  let timer = null;
  let token = 0;

  async function runPeek(value) {
    const currentToken = ++token;
    const normalized = value.trim();

    if (normalized.length < 2) {
      snapshot.value = null;
      statusText.value = "引擎就绪";
      statusState.value = "idle";
      return;
    }

    loading.value = true;
    statusText.value = "正在快速读取目录...";
    statusState.value = "busy";

    try {
      const result = await peekFolder(normalized);
      if (currentToken !== token) return;

      if (!result.ok || !result.count) {
        snapshot.value = null;
        statusText.value = result.error || "未在该目录找到照片";
        statusState.value = "idle";
        return;
      }

      snapshot.value = result;
      statusText.value = `已读取 ${Number(result.count).toLocaleString()} 张 · 待处理`;
      statusState.value = "idle";
    } catch (error) {
      if (currentToken !== token) return;
      snapshot.value = null;
      statusText.value = error.message || "目录读取失败";
      statusState.value = "error";
    } finally {
      if (currentToken === token) loading.value = false;
    }
  }

  watch(folder, (value) => {
    clearTimeout(timer);
    timer = setTimeout(() => runPeek(value || ""), 220);
  });

  return {
    snapshot,
    statusText,
    statusState,
    loading,
  };
}

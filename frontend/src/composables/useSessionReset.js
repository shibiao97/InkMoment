import { ref } from "vue";
import { resetSession } from "../api/inkmoment";

export function useSessionReset() {
  const resetting = ref(false);
  const resetError = ref("");

  async function resetCurrentSession() {
    resetting.value = true;
    resetError.value = "";
    try {
      await resetSession();
      return true;
    } catch (err) {
      resetError.value = err.message || "回首页重置失败";
      return false;
    } finally {
      resetting.value = false;
    }
  }

  return {
    resetting,
    resetError,
    resetCurrentSession,
  };
}

import { ref } from "vue";

import { getClientNotices } from "../api/inkmoment";

export function useClientNotices() {
  const clientNotices = ref(null);

  async function loadClientNotices() {
    try {
      clientNotices.value = await getClientNotices();
    } catch (err) {
      console.warn("load client notices failed", err);
    }
  }

  return {
    clientNotices,
    loadClientNotices,
  };
}

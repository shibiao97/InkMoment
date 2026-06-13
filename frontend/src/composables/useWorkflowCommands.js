export function useWorkflowCommands({
  currentView,
  resetting,
  resetCurrentSession,
  clearStartedPayload,
  enterHome,
  logger = console,
}) {
  async function requestBackHome() {
    if (resetting.value) return;
    if (currentView.value !== "landing") {
      const ok = await resetCurrentSession();
      if (!ok) logger.warn("reset_session failed; returning to landing anyway");
    }
    clearStartedPayload();
    enterHome();
  }

  return {
    requestBackHome,
  };
}

import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import { useWorkflowCommands } from "./useWorkflowCommands";

function createCommands(overrides = {}) {
  const currentView = ref(overrides.currentView || "landing");
  const resetting = ref(overrides.resetting || false);
  const resetCurrentSession = overrides.resetCurrentSession || vi.fn(async () => true);
  const clearStartedPayload = overrides.clearStartedPayload || vi.fn();
  const enterHome = overrides.enterHome || vi.fn(() => {
    currentView.value = "landing";
  });
  const logger = overrides.logger || { warn: vi.fn() };

  return {
    currentView,
    resetting,
    resetCurrentSession,
    clearStartedPayload,
    enterHome,
    logger,
    ...useWorkflowCommands({
      currentView,
      resetting,
      resetCurrentSession,
      clearStartedPayload,
      enterHome,
      logger,
    }),
  };
}

describe("useWorkflowCommands", () => {
  it("ignores duplicate back-home requests while resetting", async () => {
    const commands = createCommands({ currentView: "preview", resetting: true });

    await commands.requestBackHome();

    expect(commands.resetCurrentSession).not.toHaveBeenCalled();
    expect(commands.clearStartedPayload).not.toHaveBeenCalled();
    expect(commands.enterHome).not.toHaveBeenCalled();
  });

  it("returns home without backend reset when already landing", async () => {
    const commands = createCommands({ currentView: "landing" });

    await commands.requestBackHome();

    expect(commands.resetCurrentSession).not.toHaveBeenCalled();
    expect(commands.clearStartedPayload).toHaveBeenCalledTimes(1);
    expect(commands.enterHome).toHaveBeenCalledTimes(1);
  });

  it("resets the active backend session before returning home", async () => {
    const commands = createCommands({ currentView: "arena" });

    await commands.requestBackHome();

    expect(commands.resetCurrentSession).toHaveBeenCalledTimes(1);
    expect(commands.clearStartedPayload).toHaveBeenCalledTimes(1);
    expect(commands.enterHome).toHaveBeenCalledTimes(1);
    expect(commands.currentView.value).toBe("landing");
  });

  it("still returns home and logs a warning when backend reset fails", async () => {
    const logger = { warn: vi.fn() };
    const commands = createCommands({
      currentView: "processing",
      resetCurrentSession: vi.fn(async () => false),
      logger,
    });

    await commands.requestBackHome();

    expect(commands.resetCurrentSession).toHaveBeenCalledTimes(1);
    expect(logger.warn).toHaveBeenCalledWith("reset_session failed; returning to landing anyway");
    expect(commands.clearStartedPayload).toHaveBeenCalledTimes(1);
    expect(commands.enterHome).toHaveBeenCalledTimes(1);
  });
});

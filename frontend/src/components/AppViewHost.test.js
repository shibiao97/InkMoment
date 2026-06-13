import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import AppViewHost from "./AppViewHost.vue";

const viewStubs = {
  LandingView: {
    name: "LandingView",
    emits: ["job-started", "busy-change"],
    template: '<section data-testid="landing-view">Landing</section>',
  },
  ProcessingView: {
    name: "ProcessingView",
    props: ["startedPayload", "returningHome"],
    emits: ["back-home", "continue"],
    template: '<section data-testid="processing-view">Processing</section>',
  },
  PrescreenView: {
    name: "PrescreenView",
    props: ["returningHome"],
    emits: ["back-home", "continue-preview"],
    template: '<section data-testid="prescreen-view">Prescreen</section>',
  },
  PreviewView: {
    name: "PreviewView",
    props: ["returningHome"],
    emits: ["back-home", "continue-arena"],
    template: '<section data-testid="preview-view">Preview</section>',
  },
  ArenaView: {
    name: "ArenaView",
    props: ["returningHome"],
    emits: ["back-home", "done"],
    template: '<section data-testid="arena-view">Arena</section>',
  },
  DoneView: {
    name: "DoneView",
    props: ["returningHome"],
    emits: ["back-home", "continue-arena", "job-started"],
    template: '<section data-testid="done-view">Done</section>',
  },
};

function mountHost(props = {}) {
  return mount(AppViewHost, {
    props: {
      currentView: "landing",
      startedPayload: null,
      returningHome: false,
      ...props,
    },
    global: {
      stubs: viewStubs,
    },
  });
}

describe("AppViewHost", () => {
  it.each([
    ["landing", "landing-view"],
    ["processing", "processing-view"],
    ["prescreen", "prescreen-view"],
    ["preview", "preview-view"],
    ["arena", "arena-view"],
    ["done", "done-view"],
    ["missing", "done-view"],
  ])("renders %s as %s", (currentView, testId) => {
    const wrapper = mountHost({ currentView });

    expect(wrapper.get(`[data-testid='${testId}']`).exists()).toBe(true);
  });

  it("passes processing payload and returning-home state", () => {
    const startedPayload = { folder: "/tmp/photos", mode: "fast" };
    const wrapper = mountHost({
      currentView: "processing",
      startedPayload,
      returningHome: true,
    });
    const processing = wrapper.getComponent(viewStubs.ProcessingView);

    expect(processing.props("startedPayload")).toEqual(startedPayload);
    expect(processing.props("returningHome")).toBe(true);
  });

  it.each([
    ["prescreen", viewStubs.PrescreenView],
    ["preview", viewStubs.PreviewView],
    ["arena", viewStubs.ArenaView],
    ["done", viewStubs.DoneView],
  ])("passes returning-home state to %s", (currentView, component) => {
    const wrapper = mountHost({ currentView, returningHome: true });

    expect(wrapper.getComponent(component).props("returningHome")).toBe(true);
  });

  it("forwards landing events", async () => {
    const wrapper = mountHost({ currentView: "landing" });
    const landing = wrapper.getComponent(viewStubs.LandingView);
    const payload = { folder: "/tmp/photos" };

    landing.vm.$emit("job-started", payload);
    landing.vm.$emit("busy-change", { label: "读取照片" });
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("job-started")).toEqual([[payload]]);
    expect(wrapper.emitted("busy-change")).toEqual([[{ label: "读取照片" }]]);
  });

  it("forwards processing events", async () => {
    const wrapper = mountHost({ currentView: "processing" });
    const processing = wrapper.getComponent(viewStubs.ProcessingView);
    const nextStep = { kind: "preview" };

    processing.vm.$emit("back-home");
    processing.vm.$emit("continue", nextStep);
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("back-home")).toEqual([[]]);
    expect(wrapper.emitted("continue-step")).toEqual([[nextStep]]);
  });

  it("forwards workflow view events", async () => {
    const prescreen = mountHost({ currentView: "prescreen" });
    prescreen.getComponent(viewStubs.PrescreenView).vm.$emit("continue-preview");
    prescreen.getComponent(viewStubs.PrescreenView).vm.$emit("back-home");
    await prescreen.vm.$nextTick();
    expect(prescreen.emitted("enter-preview")).toEqual([[]]);
    expect(prescreen.emitted("back-home")).toEqual([[]]);

    const preview = mountHost({ currentView: "preview" });
    preview.getComponent(viewStubs.PreviewView).vm.$emit("continue-arena");
    preview.getComponent(viewStubs.PreviewView).vm.$emit("back-home");
    await preview.vm.$nextTick();
    expect(preview.emitted("enter-arena")).toEqual([[]]);
    expect(preview.emitted("back-home")).toEqual([[]]);

    const arena = mountHost({ currentView: "arena" });
    arena.getComponent(viewStubs.ArenaView).vm.$emit("done");
    arena.getComponent(viewStubs.ArenaView).vm.$emit("back-home");
    await arena.vm.$nextTick();
    expect(arena.emitted("enter-done")).toEqual([[]]);
    expect(arena.emitted("back-home")).toEqual([[]]);
  });

  it("forwards done view events", async () => {
    const wrapper = mountHost({ currentView: "done" });
    const done = wrapper.getComponent(viewStubs.DoneView);
    const payload = { folder: "/tmp/new-job" };

    done.vm.$emit("back-home");
    done.vm.$emit("continue-arena");
    done.vm.$emit("job-started", payload);
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("back-home")).toEqual([[]]);
    expect(wrapper.emitted("enter-arena")).toEqual([[]]);
    expect(wrapper.emitted("job-started")).toEqual([[payload]]);
  });
});

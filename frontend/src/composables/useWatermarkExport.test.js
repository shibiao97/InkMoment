import { beforeEach, describe, expect, it, vi } from "vitest";

import { getWatermarkTemplates, openWatermarkOutputFolder, previewWatermark } from "../api/inkmoment";
import { openDesktopPath } from "../api/runtime";
import { useWatermarkExport } from "./useWatermarkExport";

vi.mock("../api/inkmoment", () => ({
  cancelWatermark: vi.fn(),
  getWatermarkStatus: vi.fn(),
  getWatermarkTemplates: vi.fn(),
  openWatermarkOutputFolder: vi.fn(),
  previewWatermark: vi.fn(),
  startWatermark: vi.fn(),
}));

vi.mock("../api/runtime", () => ({
  openDesktopPath: vi.fn(),
}));

describe("useWatermarkExport", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads templates once and falls back to the first available template", async () => {
    getWatermarkTemplates.mockResolvedValue({
      templates: [
        { id: "B", name: "Minimal" },
        { id: "C", name: "Glass" },
      ],
    });

    const exportState = useWatermarkExport();
    const templates = await exportState.loadTemplates();
    const cached = await exportState.loadTemplates();

    expect(templates).toHaveLength(2);
    expect(cached).toBe(templates);
    expect(exportState.selectedTemplate.value).toBe("B");
    expect(getWatermarkTemplates).toHaveBeenCalledOnce();
  });

  it("keeps the newest preview result when requests finish out of order", async () => {
    let resolveFirst;
    getWatermarkTemplates.mockResolvedValue({ templates: [] });
    previewWatermark
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveFirst = resolve;
      }))
      .mockResolvedValueOnce({ preview_index: 2, total_winners: 5, image_url: "newer" });

    const exportState = useWatermarkExport();
    const first = exportState.refreshPreview(0);
    const second = exportState.refreshPreview(2);

    await second;
    resolveFirst({ preview_index: 0, total_winners: 9, image_url: "older" });
    await first;

    expect(exportState.preview.value.image_url).toBe("newer");
    expect(exportState.previewIndex.value).toBe(2);
    expect(exportState.totalWinners.value).toBe(5);
  });

  it("uses the desktop opener before falling back to the backend opener", async () => {
    openDesktopPath.mockResolvedValue(true);
    const exportState = useWatermarkExport();
    exportState.job.value = { status: "done", out_dir: "/tmp/watermark" };

    await expect(exportState.openOutputFolder()).resolves.toBe(true);

    expect(openDesktopPath).toHaveBeenCalledWith("/tmp/watermark");
    expect(openWatermarkOutputFolder).not.toHaveBeenCalled();
  });
});

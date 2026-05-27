import { onMounted, ref } from "vue";
import { getBranding } from "../api/inkmoment";

const DEFAULT_BRANDING = {
  app_name: "影刻",
  title_suffix: "InkMoment",
  tagline: "本地运行 · 不上传",
  hero_eyebrow: "在一摞照片里，留下那一刻",
  hero_title: "让 AI 替你过一遍，由你做最后的决定。",
  hero_subtitle: "先按相似度自动成组、淘汰明显失败片，剩下的两两摆上擂台，由你裁决。",
};

export function useBranding() {
  const branding = ref({ ...DEFAULT_BRANDING });
  const loadingBranding = ref(false);

  async function loadBranding() {
    loadingBranding.value = true;
    try {
      branding.value = { ...branding.value, ...(await getBranding()) };
    } catch (error) {
      console.warn("品牌配置加载失败，使用默认值:", error);
    } finally {
      loadingBranding.value = false;
    }
  }

  onMounted(loadBranding);

  return {
    branding,
    loadingBranding,
    loadBranding,
  };
}

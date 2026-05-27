import { computed, ref, watch } from "vue";

const THEME_KEY = "inkmoment.theme";

export const THEMES = [
  { id: "garden", label: "小花园", accent: "#78a881" },
  { id: "notebook", label: "手账纸感", accent: "#8fae9a" },
  { id: "film", label: "胶片回忆", accent: "#d49b50" },
  { id: "cafe", label: "清晨咖啡馆", accent: "#e98f7e" },
  { id: "studio", label: "暖木工作室", accent: "#9a7651" },
];

function storedTheme() {
  try {
    const value = window.localStorage?.getItem(THEME_KEY);
    return THEMES.some((theme) => theme.id === value) ? value : "garden";
  } catch {
    return "garden";
  }
}

export function useTheme() {
  const selectedTheme = ref(storedTheme());
  const theme = computed(() => {
    return THEMES.find((item) => item.id === selectedTheme.value) || THEMES[0];
  });

  watch(selectedTheme, (value) => {
    try {
      window.localStorage?.setItem(THEME_KEY, value);
    } catch {}
  }, { immediate: true });

  return {
    themes: THEMES,
    selectedTheme,
    theme,
  };
}

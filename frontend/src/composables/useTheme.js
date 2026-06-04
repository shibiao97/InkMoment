import { computed, ref, watch } from "vue";

const THEME_KEY = "inkmoment.theme";
const DEFAULT_THEME_ID = "garden";

export const THEMES = [
  {
    id: "garden",
    label: "清新绿",
    accent: "#36a66a",
    vars: {
      "--im-bg": "#f4fbf5",
      "--im-bg-wash": "rgba(196, 230, 203, 0.38)",
      "--im-surface": "#ffffff",
      "--im-surface-low": "#f8fcf7",
      "--im-surface-mid": "#e8f2e7",
      "--im-border": "#d7e7d6",
      "--im-border-strong": "#a9c9ad",
      "--im-text": "#14231a",
      "--im-muted": "#42594a",
      "--im-soft": "#708878",
      "--im-ink": "#173722",
      "--im-gold": "#c7a348",
      "--im-teal": "#36a66a",
      "--im-danger": "#b0443f",
    },
  },
  {
    id: "notebook",
    label: "精选金",
    accent: "#b88b14",
    vars: {
      "--im-bg": "#fbf8ee",
      "--im-bg-wash": "rgba(230, 205, 135, 0.3)",
      "--im-surface": "#fffdf8",
      "--im-surface-low": "#faf4e5",
      "--im-surface-mid": "#f0e4c6",
      "--im-border": "#e4d5ac",
      "--im-border-strong": "#cbb574",
      "--im-text": "#2b2414",
      "--im-muted": "#5e5239",
      "--im-soft": "#807154",
      "--im-ink": "#3a2d0e",
      "--im-gold": "#b88b14",
      "--im-teal": "#4d8a63",
      "--im-danger": "#b0443f",
    },
  },
  {
    id: "film",
    label: "中性灰",
    accent: "#5f6f69",
    vars: {
      "--im-bg": "#f5f6f4",
      "--im-bg-wash": "rgba(177, 188, 183, 0.24)",
      "--im-surface": "#ffffff",
      "--im-surface-low": "#f4f5f2",
      "--im-surface-mid": "#e6e9e4",
      "--im-border": "#d6dbd4",
      "--im-border-strong": "#adb8b1",
      "--im-text": "#1b211f",
      "--im-muted": "#4c5652",
      "--im-soft": "#737e78",
      "--im-ink": "#202826",
      "--im-gold": "#b2954d",
      "--im-teal": "#5f6f69",
      "--im-danger": "#a4453f",
    },
  },
  {
    id: "cafe",
    label: "复核红",
    accent: "#b0443f",
    vars: {
      "--im-bg": "#fff7f4",
      "--im-bg-wash": "rgba(232, 176, 163, 0.26)",
      "--im-surface": "#ffffff",
      "--im-surface-low": "#fff2ee",
      "--im-surface-mid": "#f4dcd6",
      "--im-border": "#eccbc3",
      "--im-border-strong": "#cf988e",
      "--im-text": "#2c1d1a",
      "--im-muted": "#654d48",
      "--im-soft": "#8b726d",
      "--im-ink": "#4a201d",
      "--im-gold": "#b6903f",
      "--im-teal": "#b0443f",
      "--im-danger": "#9c2720",
    },
  },
  {
    id: "studio",
    label: "墨黑",
    accent: "#202423",
    vars: {
      "--im-bg": "#f3f3f1",
      "--im-bg-wash": "rgba(78, 83, 80, 0.16)",
      "--im-surface": "#ffffff",
      "--im-surface-low": "#f4f4f2",
      "--im-surface-mid": "#e4e4e0",
      "--im-border": "#d6d6d0",
      "--im-border-strong": "#a9aaa4",
      "--im-text": "#151716",
      "--im-muted": "#4b504e",
      "--im-soft": "#747977",
      "--im-ink": "#101211",
      "--im-gold": "#a68843",
      "--im-teal": "#202423",
      "--im-danger": "#9f3932",
    },
  },
];

const selectedTheme = ref(storedTheme());
let themeWatcherStarted = false;

function storedTheme() {
  try {
    const value = window.localStorage?.getItem(THEME_KEY);
    return THEMES.some((theme) => theme.id === value) ? value : DEFAULT_THEME_ID;
  } catch {
    return DEFAULT_THEME_ID;
  }
}

function themeFor(id) {
  return THEMES.find((item) => item.id === id) || THEMES[0];
}

function themeVars(theme) {
  return {
    "--accent": theme.accent,
    ...(theme.vars || {}),
  };
}

function applyThemeVars(theme) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.dataset.theme = theme.id;
  for (const [name, value] of Object.entries(themeVars(theme))) {
    root.style.setProperty(name, value);
  }
  if (document.body) {
    document.body.dataset.theme = theme.id;
  }
}

function ensureThemeWatcher() {
  if (themeWatcherStarted) return;
  themeWatcherStarted = true;
  watch(selectedTheme, (value) => {
    try {
      window.localStorage?.setItem(THEME_KEY, value);
    } catch {
      // localStorage can be disabled in hardened WebView profiles.
    }
    applyThemeVars(themeFor(value));
  }, { immediate: true });
}

export function useTheme() {
  ensureThemeWatcher();
  const theme = computed(() => themeFor(selectedTheme.value));
  const themeStyle = computed(() => themeVars(theme.value));

  return {
    themes: THEMES,
    selectedTheme,
    theme,
    themeStyle,
  };
}

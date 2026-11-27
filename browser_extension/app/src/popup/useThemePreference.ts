import {webDarkTheme, webLightTheme} from "@fluentui/react-components";
import {useSyncExternalStore} from "react";

import type {ThemePreference} from "../shared/types";

declare global {
  interface Window {
    popupTheme: {
      getSnapshot(): ThemePreference;
      subscribe(notify: () => void): () => void;
      setPreference(value: ThemePreference): Promise<void>;
    };
  }
}

const darkMode = window.matchMedia("(prefers-color-scheme: dark)");

function subscribeDarkMode(notify: () => void) {
  darkMode.addEventListener("change", notify);
  return () => darkMode.removeEventListener("change", notify);
}

export function useThemePreference() {
  const {subscribe, getSnapshot, setPreference} = window.popupTheme;
  const themePreference = useSyncExternalStore(subscribe, getSnapshot);
  const prefersDark = useSyncExternalStore(subscribeDarkMode, () => darkMode.matches);
  const isDark = themePreference === "system" ? prefersDark : themePreference === "dark";

  return {themePreference, setThemePreference: setPreference, theme: isDark ? webDarkTheme : webLightTheme};
}

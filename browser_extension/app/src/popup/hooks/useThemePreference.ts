import { webDarkTheme, webLightTheme } from "@fluentui/react-components";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { ThemePreference } from "../../shared/types";

const THEME_PREFERENCE_STORAGE_KEY = "gd4bThemePreference";
const DARK_MODE_QUERY = "(prefers-color-scheme: dark)";

function isThemePreference(value: unknown): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

export function useThemePreference() {
  const [themePreference, setThemePreferenceState] = useState<ThemePreference>("system");
  const [prefersDark, setPrefersDark] = useState(() => window.matchMedia(DARK_MODE_QUERY).matches);

  useEffect(() => {
    void chrome.storage.local
      .get(THEME_PREFERENCE_STORAGE_KEY)
      .then((stored) => {
        const nextPreference = stored[THEME_PREFERENCE_STORAGE_KEY];
        if (isThemePreference(nextPreference)) {
          setThemePreferenceState(nextPreference);
        }
      })
      .catch(() => {
        // Ignore storage restore failures and keep the default.
      });
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia(DARK_MODE_QUERY);
    const handleChange = (event: MediaQueryListEvent) => {
      setPrefersDark(event.matches);
    };

    setPrefersDark(mediaQuery.matches);
    mediaQuery.addEventListener("change", handleChange);
    return () => {
      mediaQuery.removeEventListener("change", handleChange);
    };
  }, []);

  const resolvedThemePreference = themePreference === "system" ? (prefersDark ? "dark" : "light") : themePreference;

  useEffect(() => {
    const colorScheme = resolvedThemePreference === "dark" ? "dark" : "light";
    document.documentElement.style.colorScheme = colorScheme;
    document.body.style.colorScheme = colorScheme;
  }, [resolvedThemePreference]);

  const setThemePreference = useCallback(async (nextPreference: ThemePreference) => {
    setThemePreferenceState(nextPreference);
    await chrome.storage.local.set({
      [THEME_PREFERENCE_STORAGE_KEY]: nextPreference,
    });
  }, []);

  const theme = useMemo(
    () => (resolvedThemePreference === "dark" ? webDarkTheme : webLightTheme),
    [resolvedThemePreference],
  );

  return {
    themePreference,
    resolvedThemePreference,
    setThemePreference,
    theme,
  };
}

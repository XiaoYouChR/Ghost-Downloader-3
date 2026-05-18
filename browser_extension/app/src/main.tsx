import { FluentProvider } from "@fluentui/react-components";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./popup/App";
import { useThemePreference } from "./popup/hooks/useThemePreference";
import "./index.css";

function PopupRoot() {
  const { theme, themePreference, setThemePreference } = useThemePreference();

  return (
    <FluentProvider className="gd4b-provider" theme={theme}>
      <App
        themePreference={themePreference}
        onThemePreferenceChange={(nextPreference) => void setThemePreference(nextPreference)}
      />
    </FluentProvider>
  );
}

createRoot(document.getElementById("app") as HTMLElement).render(
  <StrictMode>
    <PopupRoot />
  </StrictMode>,
);

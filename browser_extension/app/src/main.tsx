import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./popup/App";
import "./index.css";

createRoot(document.getElementById("app") as HTMLElement).render(
  <StrictMode>
    <FluentProvider className="gd4b-provider" theme={webLightTheme}>
      <App />
    </FluentProvider>
  </StrictMode>,
);

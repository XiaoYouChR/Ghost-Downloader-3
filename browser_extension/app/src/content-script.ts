import {startPageMediaController} from "./page-media/controller";

(function installGhostDownloaderBridge() {
  window.addEventListener("message", (event) => {
    const payload = event.data;
    if (!payload || typeof payload !== "object" || payload.action !== "catCatchToBackground") {
      return;
    }

    chrome.runtime.sendMessage({
      type: "bridge_page_command",
      payload,
    });
  });

  startPageMediaController();
})();

// Separate from the page-media controller so cat-catch's message lifecycle stays
// decoupled from our attribution lifecycle.

export function installCatCatchBridge(): void {
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
}

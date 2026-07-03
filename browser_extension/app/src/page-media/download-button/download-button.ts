/*
 * Ghost Downloader — "download this media" overlay (ISOLATED world).
 * A floating button that locates the active <video> and asks the page-media attribution
 * engine (window.__gdPageMedia) to resolve the right stream, then hands it to the background.
 * Built as a standalone IIFE bundle (see scripts/build.mjs).
 */
import {findActiveMedia} from "./active-media";
import type {VideoSessionState} from "../types";

declare global {
  interface Window {
    GhostDownloaderMediaButton?: { installed: boolean };
  }
}

const IDLE_TIMEOUT_MS = 3000;
const FADE_DURATION_MS = 300;

(function installGhostDownloaderMediaButton() {
  if (window.GhostDownloaderMediaButton?.installed) { return; }
  if (!globalThis.chrome?.runtime?.sendMessage) { return; }

  const host = document.createElement("div");
  const root = host.attachShadow({ mode: "open" });
  let resetTimer = 0;
  let updateQueued = false;
  let enabled = false;
  let positionTimer = 0;
  let idleTimer = 0;
  let isVisible = false;
  let isHoveringButton = false;
  let mouseMoveQueued = false;
  let lastMouseX = -1;
  let lastMouseY = -1;

  host.id = "ghostDownloaderMediaDownload";
  Object.assign(host.style, {
    display: "none",
    left: "0",
    opacity: "0",
    position: "fixed",
    top: "0",
    transition: `opacity ${FADE_DURATION_MS}ms ease`,
    zIndex: "2147483647",
  });

  root.innerHTML = `
        <style>
            :host {
                font: 13px/18px "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
            }
            button {
                align-items: center;
                background: rgba(255, 255, 255, 0.96);
                border: 1px solid #d1d1d1;
                border-radius: 4px;
                box-shadow: 0 8px 20px rgba(0, 0, 0, 0.18), 0 1px 4px rgba(0, 0, 0, 0.12);
                color: #242424;
                cursor: pointer;
                display: inline-flex;
                font: inherit;
                font-weight: 600;
                gap: 6px;
                min-height: 32px;
                padding: 6px 10px;
                white-space: nowrap;
            }
            button:hover {
                background: #f5f5f5;
            }
            button:active {
                background: #e0e0e0;
            }
            button:disabled {
                cursor: default;
                opacity: 0.78;
            }
            .icon {
                width: 16px;
                height: 16px;
                flex: none;
            }
            .status {
                color: #0f6cbd;
            }
            .error {
                color: #b10e1c;
            }
        </style>
        <button type="button" title="${chrome.i18n.getMessage("sendCurrentMediaToGhostDownloader")}">
            <svg class="icon" viewBox="0 0 20 20" aria-hidden="true">
                <path fill="currentColor" d="M10 2.5a.75.75 0 0 1 .75.75v7.69l2.72-2.72a.75.75 0 1 1 1.06 1.06l-4 4a.75.75 0 0 1-1.06 0l-4-4a.75.75 0 0 1 1.06-1.06l2.72 2.72V3.25A.75.75 0 0 1 10 2.5Zm-5.25 11a.75.75 0 0 1 .75.75v1.25h9v-1.25a.75.75 0 0 1 1.5 0v2a.75.75 0 0 1-.75.75H4.75A.75.75 0 0 1 4 16.25v-2a.75.75 0 0 1 .75-.75Z"/>
            </svg>
            <span class="label">${chrome.i18n.getMessage("downloadThisMedia")}</span>
            <span class="status"></span>
        </button>
    `;

  const button = root.querySelector("button")!;
  const label = root.querySelector(".label")!;
  const status = root.querySelector(".status")!;

  function showButton(): void {
    if (isVisible) { return; }
    isVisible = true;
    host.style.display = "block";
    void host.offsetHeight;
    host.style.opacity = "1";
  }

  function hideButton(): void {
    if (!isVisible) { return; }
    isVisible = false;
    host.style.opacity = "0";
  }

  function resetIdleTimer(): void {
    clearTimeout(idleTimer);
    idleTimer = window.setTimeout(() => {
      if (!isHoveringButton) { hideButton(); }
    }, IDLE_TIMEOUT_MS);
  }

  host.addEventListener("transitionend", () => {
    if (host.style.opacity === "0") {
      host.style.display = "none";
    }
  });

  host.addEventListener("mouseenter", () => {
    isHoveringButton = true;
    clearTimeout(idleTimer);
  });

  host.addEventListener("mouseleave", () => {
    isHoveringButton = false;
    resetIdleTimer();
  });

  function isMouseOverVideo(): boolean {
    const active = findActiveMedia();
    if (!active) { return false; }
    const { rect } = active;
    return lastMouseX >= rect.left && lastMouseX <= rect.right
        && lastMouseY >= rect.top && lastMouseY <= rect.bottom;
  }

  function onMouseMoveFrame(): void {
    mouseMoveQueued = false;
    if (!enabled) { return; }
    if (isMouseOverVideo()) {
      showButton();
      resetIdleTimer();
      scheduleUpdate();
    }
  }

  function updatePosition(): void {
    updateQueued = false;
    if (!enabled || !isVisible) {
      return;
    }
    const selected = findActiveMedia();
    if (!selected) {
      hideButton();
      return;
    }

    const gap = 8;
    const buttonWidth = host.offsetWidth || 112;
    const buttonHeight = host.offsetHeight || 32;
    let left = Math.min(selected.rect.right - buttonWidth, innerWidth - buttonWidth - gap);
    let top = selected.rect.top - buttonHeight - gap;

    if (top < gap) {
      top = selected.rect.bottom + gap;
    }
    if (top + buttonHeight > innerHeight - gap) {
      left = selected.rect.right + gap;
      top = selected.rect.top;
      if (left + buttonWidth > innerWidth - gap) {
        left = selected.rect.left - buttonWidth - gap;
      }
    }

    host.style.left = `${Math.max(gap, Math.min(left, innerWidth - buttonWidth - gap))}px`;
    host.style.top = `${Math.max(gap, Math.min(top, innerHeight - buttonHeight - gap))}px`;
  }

  function enableOverlay(): void {
    enabled = true;
    if (document.documentElement && !host.isConnected) {
      document.documentElement.appendChild(host);
    }
    document.addEventListener("mousemove", onMouseMove, { passive: true });
    if (positionTimer) { clearInterval(positionTimer); }
    positionTimer = window.setInterval(() => {
      if (isVisible) { scheduleUpdate(); }
    }, 1000);
  }

  function disableOverlay(): void {
    enabled = false;
    hideButton();
    host.remove();
    document.removeEventListener("mousemove", onMouseMove);
    clearTimeout(idleTimer);
    if (positionTimer) {
      clearInterval(positionTimer);
      positionTimer = 0;
    }
  }

  function onMouseMove(event: MouseEvent): void {
    lastMouseX = event.clientX;
    lastMouseY = event.clientY;
    if (!mouseMoveQueued) {
      mouseMoveQueued = true;
      requestAnimationFrame(onMouseMoveFrame);
    }
  }

  function scheduleUpdate(): void {
    if (updateQueued) { return; }
    updateQueued = true;
    requestAnimationFrame(updatePosition);
  }

  function setStatus(text: string, failed = false): void {
    status.textContent = text;
    status.className = failed ? "status error" : "status";
    clearTimeout(resetTimer);
    if (text && !failed) {
      resetTimer = window.setTimeout(() => { status.textContent = ""; }, 1600);
    }
  }

  let downloadInFlight = false;
  async function downloadMedia(): Promise<void> {
    if (downloadInFlight) { return; }
    const media = findActiveMedia()?.media;
    if (!media) {
      setStatus(chrome.i18n.getMessage("errorNoMediaDetected"), true);
      return;
    }

    const pageMedia = window.__gdPageMedia;
    if (!pageMedia?.selectMediaForElement) {
      setStatus(chrome.i18n.getMessage("errorExtensionNotReady"), true);
      return;
    }

    downloadInFlight = true;
    (button as HTMLButtonElement).disabled = true;
    label.textContent = chrome.i18n.getMessage("resolving");
    setStatus("");

    const onState = (next: VideoSessionState) => {
      if (next === "waiting") { label.textContent = chrome.i18n.getMessage("waitingForResource"); }
      else if (next === "resolving" || next === "dispatched") { label.textContent = chrome.i18n.getMessage("sending"); }
    };

    try {
      const resolution = await pageMedia.selectMediaForElement(media, {
        poster: media.poster || "",
      }, onState);
      if (!resolution || resolution.kind === "refused") {
        setStatus(resolution?.message || chrome.i18n.getMessage("errorCannotLocateMedia"), true);
        return;
      }
      if (resolution.kind !== "selection") {
        setStatus(chrome.i18n.getMessage("errorCannotLocateMedia"), true);
        return;
      }
      const result = await chrome.runtime.sendMessage({
        type: "page_download_media",
        selection: resolution.selection,
        href: location.href,
        title: document.title,
      });
      const ok = Boolean(result?.ok);
      setStatus(ok ? chrome.i18n.getMessage("sent") : result?.message || chrome.i18n.getMessage("errorSendFailed"), !ok);
      pageMedia.markDispatchResult?.(media, ok, result?.message || "");
    } catch (error) {
      const message = error instanceof Error ? error.message : chrome.i18n.getMessage("errorSendFailed");
      setStatus(message, true);
      pageMedia.markDispatchResult?.(media, false, message);
    } finally {
      label.textContent = chrome.i18n.getMessage("downloadThisMedia");
      (button as HTMLButtonElement).disabled = false;
      downloadInFlight = false;
    }
  }

  button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    void downloadMedia();
  });

  addEventListener("resize", scheduleUpdate, { passive: true });
  addEventListener("scroll", scheduleUpdate, { passive: true });
  document.addEventListener("play", scheduleUpdate, true);
  document.addEventListener("pause", scheduleUpdate, true);
  document.addEventListener("loadedmetadata", scheduleUpdate, true);

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "media_button_set_enabled") { return; }
    Boolean(message.enabled) ? enableOverlay() : disableOverlay();
    sendResponse({ ok: true });
  });

  chrome.runtime.sendMessage({ type: "page_media_button_state" }, (result) => {
    const lastError = chrome.runtime.lastError;
    if (!lastError && result?.enabled === false) {
      disableOverlay();
      return;
    }
    enableOverlay();
  });

  window.GhostDownloaderMediaButton = {
    installed: true,
  };
})();

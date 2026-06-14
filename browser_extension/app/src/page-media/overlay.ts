/*
 * Ghost Downloader — "download this media" overlay (ISOLATED world).
 * A floating button that locates the active <video> and asks the page-media controller
 * (window.__gd3PageMedia) to resolve the right stream, then hands it to the background.
 * Built as a standalone IIFE bundle (see scripts/build.mjs).
 */
import type {VideoSessionState} from "./types";

declare global {
  interface Window {
    GhostDownloaderMediaButton?: { installed: boolean };
  }
}

type ActiveMedia = { media: HTMLVideoElement; rect: DOMRect; score: number };

(function installGhostDownloaderMediaButton() {
  if (window.GhostDownloaderMediaButton?.installed) { return; }
  if (!globalThis.chrome?.runtime?.sendMessage) { return; }

  const host = document.createElement("div");
  const root = host.attachShadow({ mode: "open" });
  let resetTimer = 0;
  let updateQueued = false;
  let enabled = false;

  host.id = "ghostDownloaderMediaDownload";
  Object.assign(host.style, {
    display: "none",
    left: "0",
    position: "fixed",
    top: "0",
    zIndex: "1000000000",
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
        <button type="button" title="发送当前媒体到 Ghost Downloader">
            <svg class="icon" viewBox="0 0 20 20" aria-hidden="true">
                <path fill="currentColor" d="M10 2.5a.75.75 0 0 1 .75.75v7.69l2.72-2.72a.75.75 0 1 1 1.06 1.06l-4 4a.75.75 0 0 1-1.06 0l-4-4a.75.75 0 0 1 1.06-1.06l2.72 2.72V3.25A.75.75 0 0 1 10 2.5Zm-5.25 11a.75.75 0 0 1 .75.75v1.25h9v-1.25a.75.75 0 0 1 1.5 0v2a.75.75 0 0 1-.75.75H4.75A.75.75 0 0 1 4 16.25v-2a.75.75 0 0 1 .75-.75Z"/>
            </svg>
            <span class="label">下载此媒体</span>
            <span class="status"></span>
        </button>
    `;

  const button = root.querySelector("button")!;
  const label = root.querySelector(".label")!;
  const status = root.querySelector(".status")!;

  function mediaRect(media: HTMLVideoElement): DOMRect | null {
    const rect = media.getBoundingClientRect();
    if (rect.width < 120 || rect.height < 80 || rect.bottom <= 0 || rect.right <= 0 || rect.top >= innerHeight || rect.left >= innerWidth) {
      return null;
    }
    return rect;
  }

  // Digit slots: playing (1e9) beats readyState (1e6) beats viewport area, so the user's
  // active video always wins over a paused full-screen poster.
  function mediaScore(media: HTMLVideoElement, rect: DOMRect): number {
    const playing = !media.paused && !media.ended ? 1_000_000_000 : 0;
    return playing + media.readyState * 1_000_000 + rect.width * rect.height;
  }

  function findActiveMedia(): ActiveMedia | null {
    let selected: ActiveMedia | null = null;
    for (const media of Array.from(document.querySelectorAll<HTMLVideoElement>("video"))) {
      const rect = mediaRect(media);
      if (!rect) { continue; }
      const score = mediaScore(media, rect);
      if (!selected || score > selected.score) {
        selected = { media, rect, score };
      }
    }
    return selected;
  }

  function updatePosition(): void {
    updateQueued = false;
    if (!enabled) {
      host.style.display = "none";
      return;
    }
    const selected = findActiveMedia();
    if (!selected) {
      host.style.display = "none";
      return;
    }

    host.style.display = "block";
    const gap = 8;
    const buttonWidth = host.offsetWidth || 112;
    const buttonHeight = host.offsetHeight || 32;
    let left = selected.rect.right + gap;
    let top = selected.rect.top;

    if (left + buttonWidth > innerWidth - gap) {
      left = Math.min(innerWidth - buttonWidth - gap, Math.max(gap, selected.rect.right - buttonWidth));
      top = selected.rect.top - buttonHeight - gap;
    }
    if (top < gap && selected.rect.left - buttonWidth - gap >= gap) {
      left = selected.rect.left - buttonWidth - gap;
      top = selected.rect.top;
    }
    if (top < gap) {
      top = selected.rect.bottom + gap;
    }

    host.style.left = `${Math.max(gap, Math.min(left, innerWidth - buttonWidth - gap))}px`;
    host.style.top = `${Math.max(gap, Math.min(top, innerHeight - buttonHeight - gap))}px`;
  }

  function enableOverlay(): void {
    enabled = true;
    if (document.documentElement && !host.isConnected) {
      document.documentElement.appendChild(host);
    }
    scheduleUpdate();
  }

  function disableOverlay(): void {
    enabled = false;
    host.style.display = "none";
    host.remove();
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
      // Matches TERMINAL_RESET_MS in controller.ts so toast fade and button re-enable line up.
      resetTimer = window.setTimeout(() => { status.textContent = ""; }, 1600);
    }
  }

  let downloadInFlight = false;
  async function downloadMedia(): Promise<void> {
    // Double-click would otherwise re-fire within the toast window before the auto-reset.
    if (downloadInFlight) { return; }
    const media = findActiveMedia()?.media;
    if (!media) {
      setStatus("未检测到媒体", true);
      return;
    }

    const pageMedia = window.__gd3PageMedia;
    if (!pageMedia?.resolveForElement) {
      setStatus("扩展未就绪", true);
      return;
    }

    downloadInFlight = true;
    (button as HTMLButtonElement).disabled = true;
    label.textContent = "正在解析";
    setStatus("");

    // Mirror controller state on the button so the user sees a "waiting" beat instead of staring at "正在解析".
    const onState = (next: VideoSessionState) => {
      if (next === "waiting") { label.textContent = "等待资源…"; }
      else if (next === "resolving" || next === "dispatched") { label.textContent = "正在发送"; }
    };

    try {
      const resolution = await pageMedia.resolveForElement(media, {
        poster: media.poster || "",
      }, onState);
      if (!resolution || resolution.kind === "refused") {
        // resolveForElement already moved the session to 'refused'; flipping to 'failed' would misreport why.
        setStatus(resolution?.message || "未能定位媒体", true);
        return;
      }
      if (resolution.kind !== "selection") {
        setStatus("未能定位媒体", true);
        return;
      }
      const result = await chrome.runtime.sendMessage({
        type: "page_download_media",
        selection: resolution.selection,
        href: location.href,
        title: document.title,
      });
      const ok = Boolean(result?.ok);
      setStatus(ok ? "已发送" : result?.message || "发送失败", !ok);
      pageMedia.markDispatchResult?.(media, ok, result?.message || "");
    } catch (error) {
      const message = error instanceof Error ? error.message : "发送失败";
      setStatus(message, true);
      pageMedia.markDispatchResult?.(media, false, message);
    } finally {
      label.textContent = "下载此媒体";
      (button as HTMLButtonElement).disabled = false;
      downloadInFlight = false;
      scheduleUpdate();
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
  setInterval(scheduleUpdate, 1000);

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "media_download_overlay_set_enabled") { return; }
    Boolean(message.enabled) ? enableOverlay() : disableOverlay();
    sendResponse({ ok: true });
  });

  chrome.runtime.sendMessage({ type: "page_media_overlay_state" }, (result) => {
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

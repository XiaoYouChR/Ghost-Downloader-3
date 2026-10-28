/*
 * Ghost Downloader — "download this media" overlay (ISOLATED world).
 * A floating button that locates the active <video> and asks the page-media attribution
 * engine (window.__gdPageMedia) to resolve the right stream, then hands it to the background.
 * Built as a standalone IIFE bundle (see scripts/build.mjs).
 */
import {findActiveMedia} from "./active-media";
import type {VideoSessionState} from "../types";
import {MEDIA_BUTTON_STYLE_KEY, type MediaButtonStyle} from "../../shared/types";

declare global {
  interface Window {
    GhostDownloaderMediaButton?: { installed: boolean };
  }
}

const IDLE_TIMEOUT_MS = 3000;
const FADE_DURATION_MS = 300;
const SENT_RESET_MS = 1600;
const ERROR_EXPAND_MS = 3000;
const TOOLTIP_DELAY_MS = 500;

type Phase = "idle" | "busy" | "sent" | "failed";

const PHASE_ICONS: Record<Phase, string> = {
  idle: `<svg viewBox="0 0 20 20" aria-hidden="true"><path fill="currentColor" d="M15.5 17a.5.5 0 0 1 .09 1H4.5a.5.5 0 0 1-.09-1H15.5M10 2a.5.5 0 0 1 .5.41V14.3l3.64-3.65a.5.5 0 0 1 .64-.06l.07.06c.17.17.2.44.06.63l-.06.07-4.5 4.5a.5.5 0 0 1-.25.14L10 16a.5.5 0 0 1-.4-.2l-4.46-4.45a.5.5 0 0 1 .64-.76l.07.06 3.65 3.64V2.5c0-.27.22-.5.5-.5"/></svg>`,
  busy: `<svg class="spinner" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-dasharray="30 18"/></svg>`,
  sent: `<svg viewBox="0 0 20 20" aria-hidden="true"><path fill="currentColor" d="M10 2a8 8 0 1 1 0 16 8 8 0 0 1 0-16m0 1a7 7 0 1 0 0 14 7 7 0 0 0 0-14m3.36 4.65c.17.17.2.44.06.63l-.06.07-4 4a.5.5 0 0 1-.64.07l-.07-.06-2-2a.5.5 0 0 1 .63-.77l.07.06L9 11.3l3.65-3.65c.2-.2.51-.2.7 0"/></svg>`,
  failed: `<svg viewBox="0 0 20 20" aria-hidden="true"><path fill="currentColor" d="M7.37 3.56a3 3 0 0 1 5.26 0l5.5 10A3 3 0 0 1 15.5 18h-11a3 3 0 0 1-2.63-4.44zm4.38.48a2 2 0 0 0-3.5 0l-5.5 10A2 2 0 0 0 4.5 17h11a2 2 0 0 0 1.75-2.96zM10 12.75a.75.75 0 1 1 0 1.5.75.75 0 0 1 0-1.5m0-6.25c.28 0 .5.22.5.5v4a.5.5 0 0 1-1 0V7c0-.28.22-.5.5-.5"/></svg>`,
};

const DISMISS_ICON = `<svg viewBox="0 0 12 12" aria-hidden="true"><path fill="currentColor" d="m2.09 2.22.06-.07a.5.5 0 0 1 .63-.06l.07.06L6 5.29l3.15-3.14a.5.5 0 1 1 .7.7L6.71 6l3.14 3.15c.18.17.2.44.06.63l-.06.07a.5.5 0 0 1-.63.06l-.07-.06L6 6.71 2.85 9.85a.5.5 0 0 1-.7-.7L5.29 6 2.15 2.85a.5.5 0 0 1-.06-.63l.06-.07z"/></svg>`;

(function installGhostDownloaderMediaButton() {
  if (window.GhostDownloaderMediaButton?.installed) { return; }
  if (!globalThis.chrome?.runtime?.sendMessage) { return; }

  const host = document.createElement("gd-media-button");
  const root = host.attachShadow({ mode: "open" });
  let resetTimer = 0;
  let expandTimer = 0;
  let tooltipTimer = 0;
  let updateQueued = false;
  let enabled = false;
  let positionTimer = 0;
  let idleTimer = 0;
  let isVisible = false;
  let isHoveringButton = false;
  let mouseMoveQueued = false;
  let lastMouseX = -1;
  let lastMouseY = -1;
  let dismissed = false;
  let dragOffsetX = 0;
  let dragOffsetY = 0;
  let style: MediaButtonStyle = "standard";
  let phase: Phase = "idle";
  let phaseText = "";
  let isErrorExpanded = false;
  const DRAG_THRESHOLD = 5;

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
            .wrapper {
                all: initial;
                position: relative;
                display: flex;
                align-items: stretch;
                border-radius: 4px;
                box-shadow: 0 8px 20px rgba(0, 0, 0, 0.18), 0 1px 4px rgba(0, 0, 0, 0.12);
                color: #242424;
                font-family: "Segoe UI Variable", "Segoe UI", -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", Roboto, "Helvetica Neue", sans-serif;
                font-size: 14px;
                font-weight: 400;
                line-height: 20px;
                -webkit-font-smoothing: antialiased;
            }
            button {
                all: unset;
                box-sizing: border-box;
                align-items: center;
                background: rgba(255, 255, 255, 0.96);
                border: 1px solid #d1d1d1;
                color: inherit;
                cursor: pointer;
                display: flex;
            }
            button:hover {
                background: #f5f5f5;
            }
            button:active {
                background: #e0e0e0;
            }
            button:focus-visible {
                outline: 2px solid #000000;
                outline-offset: -2px;
            }
            svg {
                display: block;
                flex: none;
            }
            .main {
                border-right: none;
                border-radius: 4px 0 0 4px;
                font-weight: 600;
                gap: 6px;
                height: 32px;
                padding: 0 12px;
                white-space: nowrap;
            }
            .main:disabled {
                cursor: default;
            }
            .icon svg {
                width: 20px;
                height: 20px;
            }
            .status:empty {
                display: none;
            }
            [data-phase="sent"] .status,
            [data-phase="sent"] .icon {
                color: #0e700e;
            }
            [data-phase="failed"] .status,
            [data-phase="failed"] .icon {
                color: #b10e1c;
            }
            [data-phase="busy"] .icon {
                color: #0f6cbd;
            }
            .spinner {
                animation: spin 1s linear infinite;
            }
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
            .close {
                border-left: none;
                border-radius: 0 4px 4px 0;
                color: #616161;
                justify-content: center;
                padding: 0 8px;
            }
            .close:hover {
                color: #242424;
            }
            .close svg {
                width: 12px;
                height: 12px;
            }
            [data-style="standard"] .icon {
                color: inherit;
            }
            [data-style="compact"] .label,
            [data-style="compact"]:not(.expanded) .status {
                display: none;
            }
            [data-style="compact"] .main {
                border-right: 1px solid #d1d1d1;
                border-radius: 4px;
                padding: 0 5px;
            }
            [data-style="compact"].expanded .main {
                padding-right: 12px;
            }
            [data-style="compact"] .close {
                display: none;
                position: absolute;
                top: -6px;
                right: -6px;
                width: 16px;
                height: 16px;
                padding: 0;
                border: 1px solid #d1d1d1;
                border-radius: 50%;
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.14);
            }
            [data-style="compact"] .close svg {
                width: 8px;
                height: 8px;
            }
            [data-style="compact"]:hover .close {
                display: flex;
            }
            .tooltip {
                position: absolute;
                top: calc(100% + 4px);
                right: 0;
                box-sizing: border-box;
                width: max-content;
                max-width: 240px;
                padding: 4px 11px 6px;
                border-radius: 4px;
                background: #ffffff;
                box-shadow: 0 0 2px rgba(0, 0, 0, 0.12), 0 8px 16px rgba(0, 0, 0, 0.14);
                color: #242424;
                font-size: 12px;
                font-weight: 400;
                line-height: 16px;
                pointer-events: none;
                white-space: normal;
                overflow-wrap: anywhere;
            }
            .tooltip.above {
                top: auto;
                bottom: calc(100% + 4px);
            }
            .tooltip[hidden] {
                display: none;
            }
        </style>
        <div class="wrapper">
            <button type="button" class="main" aria-label="${chrome.i18n.getMessage("downloadThisMedia")}">
                <span class="icon"></span>
                <span class="label"></span>
                <span class="status"></span>
            </button><button type="button" class="close" aria-label="${chrome.i18n.getMessage("cancel")}">${DISMISS_ICON}</button>
            <div class="tooltip" role="tooltip" hidden></div>
        </div>
    `;

  const wrapper = root.querySelector<HTMLElement>(".wrapper")!;
  const button = root.querySelector<HTMLButtonElement>(".main")!;
  const icon = root.querySelector(".icon")!;
  const label = root.querySelector(".label")!;
  const status = root.querySelector(".status")!;
  const closeBtn = root.querySelector<HTMLButtonElement>(".close")!;
  const tooltip = root.querySelector<HTMLElement>(".tooltip")!;
  let tooltipTarget: HTMLButtonElement | null = null;

  function tooltipText(): string {
    if (tooltipTarget === closeBtn) { return chrome.i18n.getMessage("cancel"); }
    if (style === "compact" && phase !== "idle") { return phaseText; }
    return chrome.i18n.getMessage("sendCurrentMediaToGhostDownloader");
  }

  function render(): void {
    wrapper.dataset.style = style;
    wrapper.dataset.phase = phase;
    wrapper.classList.toggle("expanded", isErrorExpanded);
    button.disabled = phase === "busy";
    icon.innerHTML = style === "compact" ? PHASE_ICONS[phase] : PHASE_ICONS.idle;
    label.textContent = phase === "busy" ? phaseText : chrome.i18n.getMessage("downloadThisMedia");
    status.textContent = phase === "sent" || phase === "failed" ? phaseText : "";
    tooltip.textContent = tooltipText();
    scheduleUpdate();
  }

  function setPhase(next: Phase, text = ""): void {
    phase = next;
    phaseText = text;
    clearTimeout(resetTimer);
    clearTimeout(expandTimer);
    isErrorExpanded = next === "failed";
    if (next === "sent") {
      resetTimer = window.setTimeout(() => setPhase("idle"), SENT_RESET_MS);
    }
    if (next === "failed") {
      expandTimer = window.setTimeout(() => {
        isErrorExpanded = false;
        render();
      }, ERROR_EXPAND_MS);
    }
    render();
  }

  function showTooltip(): void {
    tooltip.textContent = tooltipText();
    tooltip.classList.remove("above");
    tooltip.hidden = false;
    if (host.getBoundingClientRect().bottom + 4 + tooltip.offsetHeight > innerHeight - 8) {
      tooltip.classList.add("above");
    }
  }

  function hideTooltip(): void {
    clearTimeout(tooltipTimer);
    tooltipTarget = null;
    tooltip.hidden = true;
  }

  for (const target of [button, closeBtn]) {
    target.addEventListener("mouseenter", () => {
      hideTooltip();
      tooltipTarget = target;
      tooltipTimer = window.setTimeout(showTooltip, TOOLTIP_DELAY_MS);
    });
    target.addEventListener("mouseleave", hideTooltip);
  }

  function showButton(): void {
    if (isVisible || dismissed) { return; }
    isVisible = true;
    host.style.display = "block";
    void host.offsetHeight;
    host.style.opacity = "1";
  }

  function hideButton(): void {
    if (!isVisible) { return; }
    isVisible = false;
    hideTooltip();
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

    left += dragOffsetX;
    top += dragOffsetY;
    host.style.left = `${Math.max(gap, Math.min(left, innerWidth - buttonWidth - gap))}px`;
    host.style.top = `${Math.max(gap, Math.min(top, innerHeight - buttonHeight - gap))}px`;
  }

  function enableOverlay(): void {
    enabled = true;
    dismissed = false;
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

  let downloadInFlight = false;
  async function downloadMedia(): Promise<void> {
    if (downloadInFlight) { return; }
    const media = findActiveMedia()?.media;
    if (!media) {
      setPhase("failed", chrome.i18n.getMessage("errorNoMediaDetected"));
      return;
    }

    const pageMedia = window.__gdPageMedia;
    if (!pageMedia?.selectMediaForElement) {
      setPhase("failed", chrome.i18n.getMessage("errorExtensionNotReady"));
      return;
    }

    downloadInFlight = true;
    setPhase("busy", chrome.i18n.getMessage("resolving"));

    const onState = (next: VideoSessionState) => {
      if (next === "waiting") { setPhase("busy", chrome.i18n.getMessage("waitingForResource")); }
      else if (next === "resolving" || next === "dispatched") { setPhase("busy", chrome.i18n.getMessage("sending")); }
    };

    try {
      const resolution = await pageMedia.selectMediaForElement(media, {
        poster: media.poster || "",
        linkUrl: media.closest<HTMLAnchorElement>("a[href]")?.href ?? "",
      }, onState);
      if (!resolution || resolution.kind === "refused") {
        setPhase("failed", resolution?.message || chrome.i18n.getMessage("errorCannotLocateMedia"));
        return;
      }
      if (resolution.kind !== "selection") {
        setPhase("failed", chrome.i18n.getMessage("errorCannotLocateMedia"));
        return;
      }
      const result = await chrome.runtime.sendMessage({
        type: "page_download_media",
        selection: resolution.selection,
        href: location.href,
        title: document.title,
      });
      const ok = Boolean(result?.ok);
      if (ok) {
        setPhase("sent", chrome.i18n.getMessage("sent"));
      } else {
        setPhase("failed", result?.message || chrome.i18n.getMessage("errorSendFailed"));
      }
      pageMedia.markDispatchResult?.(media, ok, result?.message || "");
    } catch (error) {
      const message = error instanceof Error ? error.message : chrome.i18n.getMessage("errorSendFailed");
      setPhase("failed", message);
      pageMedia.markDispatchResult?.(media, false, message);
    } finally {
      downloadInFlight = false;
    }
  }

  closeBtn.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    dismissed = true;
    hideButton();
  });

  let dragStartX = 0;
  let dragStartY = 0;
  let dragStartLeft = 0;
  let dragStartTop = 0;
  let isDragging = false;
  let didDrag = false;

  function onDragMove(event: MouseEvent): void {
    const dx = event.clientX - dragStartX;
    const dy = event.clientY - dragStartY;
    if (!isDragging) {
      if (Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD) { return; }
      isDragging = true;
      host.style.transition = "none";
    }
    host.style.left = `${dragStartLeft + dx}px`;
    host.style.top = `${dragStartTop + dy}px`;
  }

  function onDragEnd(event: MouseEvent): void {
    document.removeEventListener("mousemove", onDragMove);
    document.removeEventListener("mouseup", onDragEnd);
    if (isDragging) {
      dragOffsetX += event.clientX - dragStartX;
      dragOffsetY += event.clientY - dragStartY;
      host.style.transition = `opacity ${FADE_DURATION_MS}ms ease`;
      didDrag = true;
      isDragging = false;
      scheduleUpdate();
    }
  }

  host.addEventListener("mousedown", (event) => {
    if ((event.composedPath()[0] as Element)?.closest?.(".close")) { return; }
    event.preventDefault();
    hideTooltip();
    dragStartX = event.clientX;
    dragStartY = event.clientY;
    dragStartLeft = parseFloat(host.style.left) || 0;
    dragStartTop = parseFloat(host.style.top) || 0;
    isDragging = false;
    didDrag = false;
    document.addEventListener("mousemove", onDragMove);
    document.addEventListener("mouseup", onDragEnd);
  });

  button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (didDrag) { didDrag = false; return; }
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

  chrome.storage.local.get({ [MEDIA_BUTTON_STYLE_KEY]: "standard" }, (result) => {
    style = result[MEDIA_BUTTON_STYLE_KEY] as MediaButtonStyle;
    render();
  });

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "local" || !changes[MEDIA_BUTTON_STYLE_KEY]) { return; }
    style = (changes[MEDIA_BUTTON_STYLE_KEY].newValue ?? "standard") as MediaButtonStyle;
    render();
  });

  render();

  window.GhostDownloaderMediaButton = {
    installed: true,
  };
})();

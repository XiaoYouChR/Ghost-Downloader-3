/*
 * Ghost Downloader — MSE attribution probe (MAIN world).
 * Proxy layout derived from cat-catch (catch-script/catch.js); upstream is GPL-3.0.
 * We post tagged, typed signals to the ISOLATED-world controller instead of capturing
 * buffers. Built as a standalone IIFE bundle (see scripts/build.mjs).
 */
import {postMediaSignal} from "./signals";

declare global {
  interface Window {
    __gd3MseAttributionInstalled?: boolean;
  }
}

type GhostXMLHttpRequest = XMLHttpRequest & { __gd3Url?: string };

(function installGhostDownloaderMseAttribution() {
  if (window.__gd3MseAttributionInstalled) { return; }
  window.__gd3MseAttributionInstalled = true;

  const mediaSourceIdByInstance = new WeakMap<MediaSource, string>();
  let mediaSourceCounter = 0;

  function mediaSourceId(mediaSource: MediaSource): string {
    let id = mediaSourceIdByInstance.get(mediaSource);
    if (id == null) {
      mediaSourceCounter += 1;
      id = `ms-${mediaSourceCounter}`;
      mediaSourceIdByInstance.set(mediaSource, id);
    }
    return id;
  }

  // Record blob URL → MediaSource so the controller can attribute <video>.src to a MS.
  if (typeof window.URL?.createObjectURL === "function" && typeof window.MediaSource !== "undefined") {
    const originalCreateObjectUrl = window.URL.createObjectURL;
    window.URL.createObjectURL = function patchedCreateObjectURL(source: Blob | MediaSource): string {
      const url = originalCreateObjectUrl(source);
      if (source instanceof MediaSource) {
        postMediaSignal({ kind: "mse_objecturl", mediaSourceId: mediaSourceId(source), objectUrl: url });
      }
      return url;
    };
  }

  if (typeof window.MediaSource !== "undefined") {
    const originalAddSourceBuffer = MediaSource.prototype.addSourceBuffer;
    MediaSource.prototype.addSourceBuffer = function patchedAddSourceBuffer(this: MediaSource, mimeType: string): SourceBuffer {
      const sourceBuffer = originalAddSourceBuffer.call(this, mimeType);
      const sourceId = mediaSourceId(this);
      postMediaSignal({ kind: "mse_source_buffer_added", mediaSourceId: sourceId, mimeType });
      try {
        const originalAppendBuffer = sourceBuffer.appendBuffer;
        sourceBuffer.appendBuffer = function patchedAppendBuffer(this: SourceBuffer, data: BufferSource): void {
          postMediaSignal({ kind: "mse_buffer_appended", mediaSourceId: sourceId, mimeType });
          return originalAppendBuffer.call(this, data);
        };
      } catch {
        // Frozen SourceBuffer prototype on some players.
      }
      return sourceBuffer;
    };
  }

  if (typeof window.fetch === "function") {
    const originalFetch = window.fetch;
    window.fetch = function patchedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
      const url = typeof input === "string"
        ? input
        : input instanceof Request
          ? input.url
          : String(input ?? "");
      const promise = originalFetch(input, init);
      promise.then((response) => {
        try {
          postMediaSignal({
            kind: "request_completed",
            url: response?.url || url,
            contentType: response?.headers?.get?.("content-type") ?? "",
          });
        } catch {
          // Opaque response.
        }
      }).catch(() => {});
      return promise;
    };
  }

  try {
    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function patchedOpen(this: GhostXMLHttpRequest, method: string, url: string | URL, ...rest: unknown[]): void {
      this.__gd3Url = String(url);
      return (originalOpen as (...args: unknown[]) => void).apply(this, [method, url, ...rest]);
    };
    XMLHttpRequest.prototype.send = function patchedSend(this: GhostXMLHttpRequest, body?: Document | XMLHttpRequestBodyInit | null): void {
      const xhr = this;
      const url = xhr.__gd3Url || "";
      xhr.addEventListener("loadend", () => {
        try {
          postMediaSignal({
            kind: "request_completed",
            url,
            contentType: xhr.getResponseHeader?.("content-type") ?? "",
          });
        } catch {
          // Opaque response.
        }
      });
      return originalSend.call(this, body);
    };
  } catch {
    // Frozen XHR prototype on some players.
  }
})();

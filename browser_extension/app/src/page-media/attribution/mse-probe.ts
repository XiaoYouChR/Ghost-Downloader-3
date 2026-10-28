/*
 * Ghost Downloader — MSE attribution probe (MAIN world).
 * Proxy layout derived from cat-catch (catch-script/catch.js); upstream is GPL-3.0.
 * We post tagged, typed signals to the ISOLATED-world attribution engine instead of
 * capturing buffers. Built as a standalone IIFE bundle (see scripts/build.mjs).
 */
import {postMediaSignal} from "./attribution-signal";
import {isMp4Head, MP4_HEAD_LIMIT, parseMp4Duration} from "./mp4-duration";

declare global {
  interface Window {
    __gdMseAttributionInstalled?: boolean;
  }
}

type GhostXMLHttpRequest = XMLHttpRequest & { __gdUrl?: string };

(function installGhostDownloaderMseAttribution() {
  if (window.__gdMseAttributionInstalled) { return; }
  window.__gdMseAttributionInstalled = true;

  const mediaSourceIdByInstance = new WeakMap<MediaSource, string>();
  let mediaSourceCounter = 0;

  // Hook each MediaSource instance, never MediaSource.prototype: CCTV's player stops
  // decrypting video when its prototype methods are not native.
  if (typeof window.URL?.createObjectURL === "function" && typeof window.MediaSource !== "undefined") {
    const originalCreateObjectUrl = window.URL.createObjectURL;
    window.URL.createObjectURL = function patchedCreateObjectURL(source: Blob | MediaSource): string {
      const url = originalCreateObjectUrl(source);
      if (!(source instanceof MediaSource)) { return url; }
      let mediaSourceId = mediaSourceIdByInstance.get(source);
      if (mediaSourceId == null) {
        mediaSourceCounter += 1;
        const id = `ms-${mediaSourceCounter}`;
        mediaSourceId = id;
        mediaSourceIdByInstance.set(source, id);
        try {
          const originalAddSourceBuffer = source.addSourceBuffer;
          source.addSourceBuffer = function patchedAddSourceBuffer(this: MediaSource, mimeType: string): SourceBuffer {
            const sourceBuffer = originalAddSourceBuffer.call(this, mimeType);
            postMediaSignal({ kind: "mse_source_buffer_added", mediaSourceId: id, mimeType });
            try {
              const originalAppendBuffer = sourceBuffer.appendBuffer;
              sourceBuffer.appendBuffer = function patchedAppendBuffer(this: SourceBuffer, data: BufferSource): void {
                postMediaSignal({ kind: "mse_buffer_appended", mediaSourceId: id, mimeType });
                return originalAppendBuffer.call(this, data);
              };
            } catch {
              // Frozen SourceBuffer prototype on some players.
            }
            return sourceBuffer;
          };
        } catch {
          // Frozen MediaSource prototype on some players.
        }
      }
      postMediaSignal({ kind: "mse_objecturl", mediaSourceId, objectUrl: url });
      return url;
    };
  }

  function toBytes(chunks: Uint8Array[]): Uint8Array {
    if (chunks.length === 1) { return chunks[0]; }
    const all = new Uint8Array(chunks.reduce((size, chunk) => size + chunk.length, 0));
    let offset = 0;
    for (const chunk of chunks) { all.set(chunk, offset); offset += chunk.length; }
    return all;
  }

  // An MP4's moov duration tells this file's video apart from a prefetched sibling's.
  async function probeContent(response: Response, url: string): Promise<void> {
    const contentLength = parseInt(response.headers.get("content-length") || "", 10);
    const contentType = response.headers.get("content-type") || "";
    if (contentLength > 2_000_000 && !/^(video|audio)\/|octet-stream/i.test(contentType)) { return; }
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    try {
      reader = response.clone().body?.getReader();
    } catch { return; /* Opaque response — clone() throws. */ }
    if (!reader) { return; }
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (size < MP4_HEAD_LIMIT) {
      const { done, value } = await reader.read();
      if (done || !value) { break; }
      chunks.push(value);
      size += value.length;
      // One chunk settles an m3u8; an MP4 needs its whole moov.
      if (!isMp4Head(chunks[0]) || parseMp4Duration(toBytes(chunks)) !== undefined) { break; }
    }
    reader.cancel().catch(() => {});
    const head = toBytes(chunks);
    const duration = parseMp4Duration(head);
    if (duration !== undefined) {
      postMediaSignal({ kind: "media_duration", url, duration });
      return;
    }
    if (head[0] !== 0x23) { return; }
    const text = new TextDecoder().decode(head);
    if (!text.startsWith("#EXTM3U")) { return; }
    postMediaSignal({
      kind: "stream_detected",
      url,
      isMaster: text.includes("#EXT-X-STREAM-INF"),
    });
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
          const resolvedUrl = response?.url || url;
          postMediaSignal({
            kind: "request_completed",
            url: resolvedUrl,
            contentType: response?.headers?.get?.("content-type") ?? "",
          });
          probeContent(response, resolvedUrl).catch(() => {});
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
      this.__gdUrl = String(url);
      return (originalOpen as (...args: unknown[]) => void).apply(this, [method, url, ...rest]);
    };
    XMLHttpRequest.prototype.send = function patchedSend(this: GhostXMLHttpRequest, body?: Document | XMLHttpRequestBodyInit | null): void {
      const xhr = this;
      xhr.addEventListener("loadend", () => {
        const resolvedUrl = xhr.responseURL || xhr.__gdUrl || "";
        try {
          postMediaSignal({
            kind: "request_completed",
            url: resolvedUrl,
            contentType: xhr.getResponseHeader?.("content-type") ?? "",
          });
        } catch {
          // Opaque response.
        }
        try {
          if ((xhr.responseType === "" || xhr.responseType === "text") && xhr.responseText?.startsWith("#EXTM3U")) {
            postMediaSignal({
              kind: "stream_detected",
              url: resolvedUrl,
              isMaster: xhr.responseText.includes("#EXT-X-STREAM-INF"),
            });
          }
        } catch { /* responseText throws on non-text responseType. */ }
        try {
          if (xhr.responseType === "arraybuffer" && xhr.response instanceof ArrayBuffer) {
            const head = new Uint8Array(xhr.response, 0, Math.min(xhr.response.byteLength, MP4_HEAD_LIMIT));
            const duration = parseMp4Duration(head);
            if (duration !== undefined) { postMediaSignal({ kind: "media_duration", url: resolvedUrl, duration }); }
          }
        } catch { /* Detached buffer — the player transferred it to a worker. */ }
      });
      return originalSend.call(this, body);
    };
  } catch {
    // Frozen XHR prototype on some players.
  }
})();

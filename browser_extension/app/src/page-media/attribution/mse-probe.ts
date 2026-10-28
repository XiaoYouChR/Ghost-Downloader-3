/*
 * Ghost Downloader — MSE attribution probe (MAIN world).
 * Proxy layout derived from cat-catch (catch-script/catch.js); upstream is GPL-3.0.
 * We post tagged, typed signals to the ISOLATED-world attribution engine instead of
 * capturing buffers. Built as a standalone IIFE bundle (see scripts/build.mjs).
 */
import {postMediaSignal} from "./attribution-signal";
import {isMp4Head, MP4_HEAD_LIMIT, parseMdatTail, parseMp4Duration} from "./mp4";

declare global {
  interface Window {
    __gdMseAttributionInstalled?: boolean;
  }
}

type GhostXMLHttpRequest = XMLHttpRequest & { __gdUrl?: string };
type Head = { url: string; bytes: Uint8Array };

const MDAT_TAIL_LENGTH = 32;
const HEADS_CAP = 16;

(function installGhostDownloaderMseAttribution() {
  if (window.__gdMseAttributionInstalled) { return; }
  window.__gdMseAttributionInstalled = true;

  const mediaSourceIdByInstance = new WeakMap<MediaSource, string>();
  let mediaSourceCounter = 0;

  // Remuxing players (TikTok) copy sample bytes verbatim, so the MP4 heads they fetched name where appended samples came from.
  const recentHeads: Head[] = [];

  function addHead(url: string, bytes: Uint8Array): Head {
    const head = { url, bytes };
    recentHeads.push(head);
    if (recentHeads.length > HEADS_CAP) { recentHeads.shift(); }
    return head;
  }

  function hasBytes(haystack: Uint8Array, needle: Uint8Array): boolean {
    for (let i = haystack.indexOf(needle[0]); i >= 0 && i + needle.length <= haystack.length; i = haystack.indexOf(needle[0], i + 1)) {
      let j = 1;
      while (j < needle.length && haystack[i + j] === needle[j]) { j += 1; }
      if (j === needle.length) { return true; }
    }
    return false;
  }

  // Every holder, not the newest: videos sharing a sound carry identical audio bytes.
  function sourceUrlsOf(tail: Uint8Array): string[] {
    return [...new Set(recentHeads.filter((head) => hasBytes(head.bytes, tail)).map((head) => head.url))];
  }

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
              let sourceUrls: string[] = [];
              sourceBuffer.appendBuffer = function patchedAppendBuffer(this: SourceBuffer, data: BufferSource): void {
                postMediaSignal({ kind: "mse_buffer_appended", mediaSourceId: id, mimeType });
                try {
                  const bytes = data instanceof ArrayBuffer ? new Uint8Array(data) : new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
                  const tail = parseMdatTail(bytes, MDAT_TAIL_LENGTH);
                  if (!tail) {
                    // An init segment starts the next video in a reused SourceBuffer, so the match starts over.
                    sourceUrls = [];
                  } else if (sourceUrls.length !== 1) {
                    const found = sourceUrlsOf(tail);
                    // Each later segment can only narrow the holders down.
                    const narrowed = sourceUrls.length === 0 ? found : sourceUrls.filter((url) => found.includes(url));
                    if (narrowed.length > 0 && narrowed.length !== sourceUrls.length) {
                      sourceUrls = narrowed;
                      postMediaSignal({ kind: "mse_buffer_matched", mediaSourceId: id, mimeType, urls: sourceUrls });
                    }
                  }
                } catch { /* Detached buffer. */ }
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
    let mp4Head: Head | undefined;
    while (size < MP4_HEAD_LIMIT) {
      const { done, value } = await reader.read();
      if (done || !value) { break; }
      chunks.push(value);
      size += value.length;
      // One chunk settles an m3u8; an MP4 is read on for the first samples sourceUrlsOf looks for.
      if (!isMp4Head(chunks[0])) { break; }
      // Grown chunk by chunk: the player appends its first segments before the head is complete.
      if (mp4Head) { mp4Head.bytes = toBytes(chunks); } else { mp4Head = addHead(url, toBytes(chunks)); }
    }
    reader.cancel().catch(() => {});
    const head = mp4Head?.bytes ?? toBytes(chunks);
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
            const head = new Uint8Array(xhr.response.slice(0, MP4_HEAD_LIMIT));
            if (isMp4Head(head)) { addHead(resolvedUrl, head); }
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

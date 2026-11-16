/*
 * Ghost Downloader — MSE attribution probe (MAIN world).
 * Proxy layout derived from cat-catch (catch-script/catch.js); upstream is GPL-3.0.
 * We post tagged, typed signals to the ISOLATED-world attribution engine instead of
 * capturing buffers. Built as a standalone IIFE bundle (see scripts/build.mjs).
 */
import {postMediaSignal} from "./attribution-signal";
import {hasMdat, isInitSegment, isMp4Head, isMp4Segment, MP4_HEAD_LIMIT, parseMdatTail, parseMp4Duration} from "./mp4";
import {isCatCatchMedia} from "../../shared/cat-catch";
import {fileExtension, filenameFromUrl, mimeFromUrl} from "../../shared/utils";
import {isVimeoPlaylistUrl} from "../resolution/url-classify";

declare global {
  interface Window {
    __gdMseAttributionInstalled?: boolean;
  }
}

type GhostXMLHttpRequest = XMLHttpRequest & { __gdUrl?: string; __gdDone?: boolean };
type Head = { url: string; bytes: Uint8Array; hasMoov: boolean };

const MDAT_TAIL_LENGTH = 32;
const HEADS_CAP = 16;
const PER_URL_HEADS_CAP = 2;

(function installGhostDownloaderMseAttribution() {
  if (window.__gdMseAttributionInstalled) { return; }
  window.__gdMseAttributionInstalled = true;

  const mediaSourceIdByInstance = new WeakMap<MediaSource, string>();
  let mediaSourceCounter = 0;

  // Remuxing players (TikTok) copy sample bytes verbatim, so the MP4 heads they fetched name where appended samples came from.
  const recentHeads: Head[] = [];

  function addHead(url: string, bytes: Uint8Array, hasMoov: boolean): Head {
    let sameUrlCount = 0;
    let oldestSameUrlIndex = -1;
    for (let i = 0; i < recentHeads.length; i += 1) {
      if (recentHeads[i].url === url) {
        sameUrlCount += 1;
        if (oldestSameUrlIndex < 0) { oldestSameUrlIndex = i; }
      }
    }
    if (sameUrlCount >= PER_URL_HEADS_CAP && oldestSameUrlIndex >= 0) {
      recentHeads.splice(oldestSameUrlIndex, 1);
    }
    const head = { url, bytes, hasMoov };
    recentHeads.push(head);
    if (recentHeads.length > HEADS_CAP) { recentHeads.shift(); }
    return head;
  }

  function isMediaRequest(url: string, contentType: string): boolean {
    if (!/^https?:/i.test(url)) { return false; }
    const mime = contentType.split(";")[0]?.trim().toLowerCase() || mimeFromUrl(url);
    return isCatCatchMedia(fileExtension(filenameFromUrl(url)), mime);
  }

  function hasRangeParam(url: string): boolean {
    try {
      const parsed = new URL(url);
      return parsed.searchParams.has("bytestart") || parsed.searchParams.has("byteend");
    } catch {
      return false;
    }
  }

  // Repeated silent AAC frames are byte-identical across unrelated videos.
  function isDistinctive(tail: Uint8Array): boolean {
    return new Set(tail).size >= MDAT_TAIL_LENGTH / 2;
  }

  function hasBytes(haystack: Uint8Array, needle: Uint8Array): boolean {
    for (let i = haystack.indexOf(needle[0]); i >= 0 && i + needle.length <= haystack.length; i = haystack.indexOf(needle[0], i + 1)) {
      let j = 1;
      while (j < needle.length && haystack[i + j] === needle[j]) { j += 1; }
      if (j === needle.length) { return true; }
    }
    return false;
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
              let isProgressiveLocked = false;
              sourceBuffer.appendBuffer = function patchedAppendBuffer(this: SourceBuffer, data: BufferSource): void {
                try {
                  const bytes = data instanceof ArrayBuffer ? new Uint8Array(data) : new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
                  if (isInitSegment(bytes)) {
                    // An init segment starts the next video in a reused SourceBuffer, so the old match must not outlive it.
                    if (sourceUrls.length > 0) { postMediaSignal({ kind: "mse_buffer_matched", mediaSourceId: id, mimeType, urls: [] }); }
                    sourceUrls = [];
                    isProgressiveLocked = false;
                  }
                  const tail = !isProgressiveLocked ? parseMdatTail(bytes, MDAT_TAIL_LENGTH) : undefined;
                  if (tail && isDistinctive(tail)) {
                    const matches = recentHeads.filter((head) => hasBytes(head.bytes, tail));
                    const found = [...new Set(matches.map((head) => head.url))];
                    if (found.length > 0) {
                      const narrowed = sourceUrls.length === 0 ? found : sourceUrls.filter((url) => found.includes(url));
                      // Progressive MP4s stay strictly narrowing-only so TikTok shared-sound reels cannot flip;
                      // range-sliced DASH segments switch when CDN failover or ABR moves to another URL.
                      const next = narrowed.length > 0 ? narrowed : (matches.every((head) => !head.hasMoov) ? found : []);
                      if (next.length > 0 && (next.length !== sourceUrls.length || next.some((u, i) => u !== sourceUrls[i]))) {
                        sourceUrls = next;
                        isProgressiveLocked = next.length === 1 && matches.some((head) => head.url === next[0] && head.hasMoov);
                        postMediaSignal({ kind: "mse_buffer_matched", mediaSourceId: id, mimeType, urls: sourceUrls });
                      }
                    }
                  }
                } catch { /* Detached buffer. */ }
                if (sourceUrls.length !== 1) {
                  postMediaSignal({ kind: "mse_buffer_appended", mediaSourceId: id, mimeType });
                }
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
    if (!/^https?:/i.test(url)) { return; }
    const contentLength = parseInt(response.headers.get("content-length") || "", 10);
    const contentType = response.headers.get("content-type") || "";
    if (/^(application\/(json|ld\+json|javascript|x-javascript|wasm|x-www-form-urlencoded|grpc)|text\/(html|css|javascript|event-stream)|image\/|font\/)/i.test(contentType)) { return; }
    if (contentLength > 2_000_000 && !/^(video|audio)\/|octet-stream/i.test(contentType)) { return; }
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    try {
      reader = response.clone().body?.getReader();
    } catch { return; /* Opaque response — clone() throws. */ }
    if (!reader) { return; }
    const isRangeSlice = response.status === 206 || hasRangeParam(url);
    const chunks: Uint8Array[] = [];
    let size = 0;
    let mp4Head: Head | undefined;
    try {
      while (size < MP4_HEAD_LIMIT) {
        const { done, value } = await reader.read();
        if (done || !value) { break; }
        chunks.push(value);
        size += value.length;
        const current = toBytes(chunks);
        if (current.length < 8) { continue; }
        // One chunk settles an m3u8; MP4 heads and range segments stay open up to MP4_HEAD_LIMIT for sample matching.
        if (!isMp4Head(current) && !(isRangeSlice && isMp4Segment(current))) { break; }
        // Grown chunk by chunk: the player may append first segments before the head finishes arriving.
        if (hasMdat(current)) {
          const hasMoov = isInitSegment(current);
          if (mp4Head) {
            mp4Head.bytes = current;
            mp4Head.hasMoov = hasMoov;
          } else {
            mp4Head = addHead(url, current, hasMoov);
          }
        }
      }
    } finally {
      reader.cancel().catch(() => {});
    }
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
          if (!response || !response.ok) { return; }
          const resolvedUrl = response.url || url;
          if (isVimeoPlaylistUrl(resolvedUrl)) { postMediaSignal({ kind: "stream_detected", url: resolvedUrl, isMaster: true }); }
          const contentType = response.headers?.get?.("content-type") ?? "";
          if (isMediaRequest(resolvedUrl, contentType)) {
            postMediaSignal({
              kind: "request_completed",
              url: resolvedUrl,
              contentType,
            });
          }
          probeContent(response, resolvedUrl).catch(() => {});
        } catch {
          // Opaque response.
        }
      }).catch(() => {});
      return promise;
    };
  }

  try {
    const hookedXhrs = new WeakSet<XMLHttpRequest>();
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function patchedOpen(this: GhostXMLHttpRequest, method: string, url: string | URL, ...rest: unknown[]): void {
      this.__gdUrl = String(url);
      this.__gdDone = false;
      if (!hookedXhrs.has(this)) {
        hookedXhrs.add(this);
        const xhr = this;
        // Fire on readystatechange DONE (before load / loadend) so recentHeads and request_completed
        // land before players appendBuffer synchronously inside onload.
        xhr.addEventListener("readystatechange", () => {
          if (xhr.readyState !== 4 || xhr.__gdDone) { return; }
          xhr.__gdDone = true;
          if (xhr.status < 200 || xhr.status >= 300) { return; }
          const resolvedUrl = xhr.responseURL || xhr.__gdUrl || "";
          if (isVimeoPlaylistUrl(resolvedUrl)) { postMediaSignal({ kind: "stream_detected", url: resolvedUrl, isMaster: true }); }
          let contentType = "";
          try {
            contentType = xhr.getResponseHeader?.("content-type") ?? "";
            if (isMediaRequest(resolvedUrl, contentType)) {
              postMediaSignal({
                kind: "request_completed",
                url: resolvedUrl,
                contentType,
              });
            }
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
              const preview = new Uint8Array(xhr.response, 0, Math.min(xhr.response.byteLength, 16));
              const isRangeSlice = xhr.status === 206 || hasRangeParam(resolvedUrl);
              if (isMp4Head(preview) || (isRangeSlice && isMp4Segment(preview))) {
                const head = new Uint8Array(xhr.response.slice(0, MP4_HEAD_LIMIT));
                if (hasMdat(head)) { addHead(resolvedUrl, head, isInitSegment(head)); }
                const duration = parseMp4Duration(head);
                if (duration !== undefined) { postMediaSignal({ kind: "media_duration", url: resolvedUrl, duration }); }
              }
            }
          } catch { /* Detached buffer — the player transferred it to a worker. */ }
        });
      }
      return (originalOpen as (...args: unknown[]) => void).apply(this, [method, url, ...rest]);
    };
  } catch {
    // Frozen XHR prototype on some players.
  }
})();

/*
 * Ghost Downloader — MSE attribution probe.
 * Proxy layout derived from cat-catch (catch-script/catch.js); upstream is GPL-3.0.
 * We post tagged messages to the ISOLATED-world controller instead of capturing buffers.
 */
(function installGhostDownloaderMseAttribution() {
    if (window.__gd3MseAttributionInstalled) { return; }
    window.__gd3MseAttributionInstalled = true;

    const SIGNAL_KEY = "__gd3MediaSignal";
    const mediaSourceIdByInstance = new WeakMap();
    let mediaSourceCounter = 0;

    function post(payload) {
        try {
            window.postMessage({ [SIGNAL_KEY]: true, ...payload }, "*");
        } catch {
            // Detached frame.
        }
    }

    function mediaSourceId(mediaSource) {
        let id = mediaSourceIdByInstance.get(mediaSource);
        if (id == null) {
            mediaSourceCounter += 1;
            id = `ms-${mediaSourceCounter}`;
            mediaSourceIdByInstance.set(mediaSource, id);
        }
        return id;
    }

    // Record blob URL → MediaSource so the controller can correlate <video>.src to a MS.
    if (typeof window.URL?.createObjectURL === "function" && typeof window.MediaSource !== "undefined") {
        const originalCreateObjectUrl = window.URL.createObjectURL;
        window.URL.createObjectURL = function patchedCreateObjectURL(source) {
            const url = originalCreateObjectUrl.call(this, source);
            if (source instanceof MediaSource) {
                post({ kind: "mse_objecturl", mediaSourceId: mediaSourceId(source), objectUrl: url });
            }
            return url;
        };
    }

    if (typeof window.MediaSource !== "undefined") {
        const originalAddSourceBuffer = MediaSource.prototype.addSourceBuffer;
        MediaSource.prototype.addSourceBuffer = function patchedAddSourceBuffer(mimeType) {
            const sourceBuffer = originalAddSourceBuffer.apply(this, arguments);
            const msId = mediaSourceId(this);
            post({ kind: "mse_source_buffer_added", mediaSourceId: msId, mimeType });
            try {
                const originalAppendBuffer = sourceBuffer.appendBuffer;
                sourceBuffer.appendBuffer = function patchedAppendBuffer(data) {
                    const byteLength = data?.byteLength ?? 0;
                    post({ kind: "mse_buffer_appended", mediaSourceId: msId, mimeType, byteLength });
                    return originalAppendBuffer.apply(this, arguments);
                };
            } catch {
                // Frozen SourceBuffer prototype on some players.
            }
            return sourceBuffer;
        };
    }

    if (typeof window.fetch === "function") {
        const originalFetch = window.fetch;
        window.fetch = function patchedFetch(input) {
            const url = typeof input === "string"
                ? input
                : input instanceof Request
                    ? input.url
                    : String(input ?? "");
            const promise = originalFetch.apply(this, arguments);
            promise.then((response) => {
                try {
                    post({
                        kind: "fetch_completed",
                        url: response?.url || url,
                        status: response?.status ?? 0,
                        contentType: response?.headers?.get?.("content-type") ?? "",
                        contentLength: Number(response?.headers?.get?.("content-length") ?? 0),
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
        XMLHttpRequest.prototype.open = function patchedOpen(method, url) {
            this.__gd3Url = String(url);
            return originalOpen.apply(this, arguments);
        };
        XMLHttpRequest.prototype.send = function patchedSend() {
            const xhr = this;
            const url = xhr.__gd3Url || "";
            xhr.addEventListener("loadend", () => {
                try {
                    post({
                        kind: "xhr_completed",
                        url,
                        status: xhr.status ?? 0,
                        contentType: xhr.getResponseHeader?.("content-type") ?? "",
                        contentLength: Number(xhr.getResponseHeader?.("content-length") ?? 0),
                    });
                } catch { /* opaque response */ }
            });
            return originalSend.apply(this, arguments);
        };
    } catch {
        // Frozen XHR prototype on some players.
    }

    post({ kind: "attribution_ready" });
})();

(function installBridge() {
  let mediaElements: Array<HTMLVideoElement | HTMLAudioElement> = [];
  let mediaSources: string[] = [];

  function resolveEventHref(event: MessageEvent): string {
    const payload = event.data as { href?: unknown } | null;
    if (typeof payload?.href === "string" && payload.href) {
      return payload.href;
    }

    try {
      const sourceWindow = event.source as Window | null;
      const href = sourceWindow?.location?.href;
      if (typeof href === "string" && href) {
        return href;
      }
    } catch {
      // Ignore cross-origin source lookups.
    }

    return location.href;
  }

  function collectMediaElements() {
    const elements: Array<HTMLVideoElement | HTMLAudioElement> = [];
    const sources: string[] = [];

    document.querySelectorAll("video, audio").forEach((element) => {
      const media = element as HTMLVideoElement | HTMLAudioElement;
      if (!media.currentSrc) {
        return;
      }
      elements.push(media);
      sources.push(media.currentSrc);
    });

    document.querySelectorAll("iframe").forEach((frame) => {
      try {
        frame.contentDocument?.querySelectorAll("video, audio").forEach((element) => {
          const media = element as HTMLVideoElement | HTMLAudioElement;
          if (!media.currentSrc) {
            return;
          }
          elements.push(media);
          sources.push(media.currentSrc);
        });
      } catch {
        // Ignore cross-origin frames.
      }
    });

    mediaElements = elements;
    mediaSources = sources;
  }

  function getMediaState(index: number) {
    collectMediaElements();
    if (mediaElements.length === 0) {
      return { count: 0 };
    }

    const normalizedIndex = index >= 0 && index < mediaElements.length ? index : 0;
    const media = mediaElements[normalizedIndex];
    const duration = Number.isFinite(media.duration) ? media.duration : 0;
    const progress = duration > 0 ? (media.currentTime / duration) * 100 : 0;

    return {
      count: mediaElements.length,
      src: mediaSources,
      currentTime: media.currentTime,
      duration,
      time: progress,
      volume: media.volume,
      paused: media.paused,
      loop: media.loop,
      speed: media.playbackRate,
      muted: media.muted,
      type: media.tagName.toLowerCase(),
    };
  }

  function getMedia(index: number) {
    collectMediaElements();
    if (mediaElements.length === 0) {
      return null;
    }
    const normalizedIndex = index >= 0 && index < mediaElements.length ? index : 0;
    return mediaElements[normalizedIndex] ?? null;
  }

  function ignorePromiseRejection(value: unknown) {
    if (value && typeof (value as Promise<unknown>).catch === "function") {
      void (value as Promise<unknown>).catch(() => {
        // Ignore page API rejections to stay aligned with upstream behavior.
      });
    }
  }

  function secToTime(value: number) {
    const totalSeconds = Math.floor(value);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) {
      return `${hours}-${String(minutes).padStart(2, "0")}-${String(seconds).padStart(2, "0")}`;
    }
    return `${String(minutes).padStart(2, "0")}-${String(seconds).padStart(2, "0")}`;
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || typeof message !== "object") {
      return;
    }

    if (message.Message === "getVideoState") {
      sendResponse(getMediaState(Number(message.index ?? 0)));
      return true;
    }

    const media = getMedia(Number(message.index ?? 0));
    if (!media) {
      sendResponse({ ok: false, message: "media_not_found" });
      return true;
    }

    if (message.Message === "speed") {
      media.playbackRate = Number(message.speed ?? 1) || 1;
      sendResponse({ ok: true });
      return true;
    }
    if (message.Message === "play") {
      void media.play().then(() => sendResponse({ ok: true })).catch(() => sendResponse({ ok: false, message: "play_failed" }));
      return true;
    }
    if (message.Message === "pause") {
      media.pause();
      sendResponse({ ok: true });
      return true;
    }
    if (message.Message === "loop") {
      media.loop = Boolean(message.action);
      sendResponse({ ok: true });
      return true;
    }
    if (message.Message === "muted") {
      media.muted = Boolean(message.action);
      sendResponse({ ok: true });
      return true;
    }
    if (message.Message === "setVolume") {
      media.volume = Math.max(0, Math.min(1, Number(message.volume ?? 1)));
      sendResponse({ ok: true });
      return true;
    }
    if (message.Message === "setTime") {
      const progress = Math.max(0, Math.min(100, Number(message.time ?? 0)));
      const duration = Number.isFinite(media.duration) ? media.duration : 0;
      media.currentTime = duration > 0 ? (progress / 100) * duration : 0;
      sendResponse({ ok: true });
      return true;
    }
    if (message.Message === "pip") {
      if (!(media instanceof HTMLVideoElement)) {
        sendResponse({ ok: false, state: false, message: "pip_requires_video" });
        return true;
      }
      if (document.pictureInPictureElement) {
        try {
          ignorePromiseRejection(document.exitPictureInPicture());
          sendResponse({ ok: true, state: false });
        } catch {
          sendResponse({ ok: false, state: true, message: "pip_exit_failed" });
        }
        return true;
      }
      try {
        ignorePromiseRejection(media.requestPictureInPicture());
        sendResponse({ ok: true, state: true });
      } catch {
        sendResponse({ ok: false, state: false, message: "pip_enter_failed" });
      }
      return true;
    }
    if (message.Message === "fullScreen") {
      if (document.fullscreenElement) {
        try {
          ignorePromiseRejection(document.exitFullscreen());
          sendResponse({ ok: true, state: false });
        } catch {
          sendResponse({ ok: false, state: true, message: "fullscreen_exit_failed" });
        }
        return true;
      }
      sendResponse({ ok: true, state: true });
      window.setTimeout(() => {
        try {
          ignorePromiseRejection(media.requestFullscreen());
        } catch {
          // Ignore fullscreen entry failures to stay aligned with upstream behavior.
        }
      }, 500);
      return true;
    }
    if (message.Message === "screenshot") {
      if (!(media instanceof HTMLVideoElement)) {
        sendResponse({ ok: false, message: "screenshot_requires_video" });
        return true;
      }
      try {
        const canvas = document.createElement("canvas");
        canvas.width = media.videoWidth;
        canvas.height = media.videoHeight;
        canvas.getContext("2d")?.drawImage(media, 0, 0, canvas.width, canvas.height);
        const link = document.createElement("a");
        link.href = canvas.toDataURL("image/jpeg");
        link.download = `${location.hostname}-${secToTime(media.currentTime)}.jpg`;
        link.click();
      } catch {
        // Ignore screenshot errors.
        sendResponse({ ok: false, message: "screenshot_failed" });
        return true;
      }
      sendResponse({ ok: true });
      return true;
    }
  });

  window.addEventListener("message", (event) => {
    const payload = event.data;
    if (!payload || typeof payload !== "object" || typeof payload.action !== "string") {
      return;
    }

    if (payload.action === "catCatchAddMedia" && typeof payload.url === "string") {
      const href = resolveEventHref(event);
      chrome.runtime.sendMessage({
        type: "bridge_page_media",
        payload: {
          url: payload.url,
          href,
          filename: payload.filename,
          mime: payload.mime,
          ext: payload.ext,
          requestHeaders: {
            referer: payload.referer ?? href,
          },
          requestId: payload.requestId,
        },
      });
      return;
    }

    if (payload.action === "catCatchToBackground") {
      const forwarded = { ...payload };
      delete forwarded.action;
      chrome.runtime.sendMessage({
        type: "bridge_page_command",
        payload: forwarded,
      });
    }
  });
})();

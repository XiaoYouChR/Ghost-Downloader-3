// Pure media discovery for the overlay: locate the <video> the user most likely wants
// to download. Split out of overlay.ts so the overlay owns only UI + messaging, not the
// scoring heuristic that picks which video is "active".

export type ActiveMedia = { media: HTMLVideoElement; rect: DOMRect; score: number };

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

export function findActiveMedia(): ActiveMedia | null {
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

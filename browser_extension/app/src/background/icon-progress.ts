import type {TaskSummary} from "../shared/types";

let baseIcon16: ImageBitmap | null = null;
let baseIcon32: ImageBitmap | null = null;
let indeterminateAngle = 0;
let indeterminateTimer: number | null = null;
let isShowingProgress = false;

const BRAND_COLOR = "#0078d4";
const TRACK_COLOR = "rgba(0, 0, 0, 0.12)";
const ARC_LENGTH = Math.PI / 2;
const FRAME_INTERVAL_MS = 80;
const ANGLE_STEP = Math.PI / 12;

export async function loadBaseIcons(): Promise<void> {
  try {
    const response = await fetch(chrome.runtime.getURL("icon48.png"));
    const blob = await response.blob();
    baseIcon16 = await createImageBitmap(blob, { resizeWidth: 16, resizeHeight: 16 });
    baseIcon32 = await createImageBitmap(blob, { resizeWidth: 32, resizeHeight: 32 });
  } catch {
    // Icon load failure is non-fatal — progress ring just won't render.
  }
}

function drawIcon(size: number, icon: ImageBitmap, arc: { start: number; end: number }): ImageData {
  const canvas = new OffscreenCanvas(size, size);
  const ctx = canvas.getContext("2d")!;

  ctx.drawImage(icon, 0, 0, size, size);

  const lineWidth = size >= 32 ? 2 : 1.5;
  const center = size / 2;
  const radius = center - lineWidth / 2 - 0.5;

  ctx.lineWidth = lineWidth;
  ctx.lineCap = "round";

  ctx.beginPath();
  ctx.arc(center, center, radius, 0, Math.PI * 2);
  ctx.strokeStyle = TRACK_COLOR;
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(center, center, radius, arc.start, arc.end);
  ctx.strokeStyle = BRAND_COLOR;
  ctx.stroke();

  return ctx.getImageData(0, 0, size, size);
}

function pushIcon(arc: { start: number; end: number }): void {
  if (!baseIcon16 || !baseIcon32) {
    return;
  }
  chrome.action.setIcon({
    imageData: {
      16: drawIcon(16, baseIcon16, arc),
      32: drawIcon(32, baseIcon32, arc),
    },
  });
}

function resetIcon(): void {
  if (!isShowingProgress) {
    return;
  }
  stopIndeterminate();
  isShowingProgress = false;
  chrome.action.setIcon({
    path: { 16: "icon16.png", 32: "icon32.png", 48: "icon48.png", 128: "icon128.png" },
  });
}

function startIndeterminate(): void {
  if (indeterminateTimer !== null) {
    return;
  }
  indeterminateTimer = self.setInterval(() => {
    indeterminateAngle = (indeterminateAngle + ANGLE_STEP) % (Math.PI * 2);
    pushIcon({ start: indeterminateAngle, end: indeterminateAngle + ARC_LENGTH });
  }, FRAME_INTERVAL_MS);
}

function stopIndeterminate(): void {
  if (indeterminateTimer !== null) {
    self.clearInterval(indeterminateTimer);
    indeterminateTimer = null;
  }
  indeterminateAngle = 0;
}

export function updateIconForTasks(tasks: TaskSummary[]): void {
  const running = tasks.filter((t) => t.status === "running");
  if (running.length === 0) {
    resetIcon();
    return;
  }

  isShowingProgress = true;

  let knownTotal = 0;
  let knownReceived = 0;
  for (const t of running) {
    if (t.fileSize > 0) {
      knownTotal += t.fileSize;
      knownReceived += t.receivedBytes;
    }
  }

  if (knownTotal > 0) {
    stopIndeterminate();
    const progress = Math.min(knownReceived / knownTotal, 1);
    const startAngle = -Math.PI / 2;
    pushIcon({ start: startAngle, end: startAngle + progress * Math.PI * 2 });
  } else {
    startIndeterminate();
  }
}

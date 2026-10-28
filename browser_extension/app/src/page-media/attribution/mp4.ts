// Past this, the moov sits at the file's end (non-faststart) and the duration stays unknown.
export const MP4_HEAD_LIMIT = 256 * 1024;

type Box = { type: string; start: number; end: number };

function parseBoxes(view: DataView, from: number, to: number): Box[] {
  const boxes: Box[] = [];
  let offset = from;
  while (offset + 8 <= to) {
    let size = view.getUint32(offset);
    const type = String.fromCharCode(
      view.getUint8(offset + 4), view.getUint8(offset + 5), view.getUint8(offset + 6), view.getUint8(offset + 7),
    );
    let header = 8;
    if (size === 1) {
      if (offset + 16 > to) { break; }
      size = Number(view.getBigUint64(offset + 8));
      header = 16;
    } else if (size === 0) {
      size = to - offset;
    }
    if (size < header) { break; }
    boxes.push({ type, start: offset + header, end: offset + size });
    offset += size;
  }
  return boxes;
}

export function isMp4Head(bytes: Uint8Array): boolean {
  return bytes.length >= 8 && bytes[4] === 0x66 && bytes[5] === 0x74 && bytes[6] === 0x79 && bytes[7] === 0x70;
}

// Seconds from mvhd, or mehd for fragmented files whose mvhd leaves the duration at 0.
export function parseMp4Duration(bytes: Uint8Array): number | undefined {
  if (!isMp4Head(bytes)) { return undefined; }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const moov = parseBoxes(view, 0, view.byteLength).find((box) => box.type === "moov");
  if (!moov) { return undefined; }
  const children = parseBoxes(view, moov.start, Math.min(moov.end, view.byteLength));
  const mvhd = children.find((box) => box.type === "mvhd");
  if (!mvhd || mvhd.start + 32 > view.byteLength) { return undefined; }
  const isV1 = view.getUint8(mvhd.start) === 1;
  const timescale = view.getUint32(mvhd.start + (isV1 ? 20 : 12));
  let duration = isV1 ? Number(view.getBigUint64(mvhd.start + 24)) : view.getUint32(mvhd.start + 16);
  if (duration === 0 || duration === 0xffffffff) {
    const mvex = children.find((box) => box.type === "mvex");
    const mehd = mvex && parseBoxes(view, mvex.start, Math.min(mvex.end, view.byteLength)).find((box) => box.type === "mehd");
    if (mehd && mehd.start + 12 <= view.byteLength) {
      duration = view.getUint8(mehd.start) === 1 ? Number(view.getBigUint64(mehd.start + 4)) : view.getUint32(mehd.start + 4);
    }
  }
  return timescale > 0 && duration > 0 ? duration / timescale : undefined;
}

export function isInitSegment(bytes: Uint8Array): boolean {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  return parseBoxes(view, 0, view.byteLength).some((box) => box.type === "moov");
}

// The tail of a media segment's samples: entropy-coded bytes, unlike the head's encoder SEI that repeats across videos.
export function parseMdatTail(bytes: Uint8Array, length: number): Uint8Array | undefined {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const mdat = parseBoxes(view, 0, view.byteLength).find((box) => box.type === "mdat");
  if (!mdat || mdat.end > bytes.length || mdat.end - mdat.start < length) { return undefined; }
  return bytes.subarray(mdat.end - length, mdat.end);
}

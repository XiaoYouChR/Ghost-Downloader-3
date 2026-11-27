type NetworkResponseMeta = {
  size: number;
  hasSize: boolean;
  isAttachment: boolean;
  mime: string;
  filename: string;
  supportsRange: boolean;
  cookie: string;
};

export function basenameOf(path: string): string {
  const trimmed = path.trim();
  if (!trimmed) { return ""; }
  const slashIndex = Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\"));
  return slashIndex >= 0 ? trimmed.slice(slashIndex + 1) : trimmed;
}

export function toResponseMeta(headers: chrome.webRequest.HttpHeader[] | undefined): NetworkResponseMeta {
  const meta: NetworkResponseMeta = { size: 0, hasSize: false, isAttachment: false, mime: "", filename: "", supportsRange: false, cookie: "" };
  let contentLengthSize = 0;
  let contentRangeSize = 0;
  const cookies: string[] = [];
  for (const header of headers ?? []) {
    const name = (header.name ?? "").toLowerCase();
    const value = (header.value ?? "").trim();
    if (name === "content-length") {
      const size = Number.parseInt(value, 10);
      meta.hasSize = Number.isFinite(size) && size >= 0;
      contentLengthSize = Number.isFinite(size) && size > 0 ? size : contentLengthSize;
    } else if (name === "content-type") {
      meta.mime = value.split(";")[0]?.trim().toLowerCase() ?? "";
    } else if (name === "content-disposition") {
      meta.isAttachment = value.split(";", 1)[0].trim().toLowerCase() === "attachment";
      const match = /filename\*\s*=\s*UTF-8''([^;]+)|filename\s*=\s*"?([^";]+)"?/i.exec(value);
      const filename = match?.[1] ?? match?.[2] ?? "";
      try {
        meta.filename = basenameOf(decodeURIComponent(filename));
      } catch {
        meta.filename = basenameOf(filename);
      }
    } else if (name === "accept-ranges") {
      meta.supportsRange = value.toLowerCase().includes("bytes");
    } else if (name === "content-range") {
      const size = Number.parseInt(value.split("/")[1] ?? "", 10);
      contentRangeSize = Number.isFinite(size) && size > 0 ? size : contentRangeSize;
      meta.supportsRange = true;
    } else if (name === "set-cookie") {
      const pair = value.split(";", 1)[0]?.trim() ?? "";
      const eqIndex = pair.indexOf("=");
      if (eqIndex > 0 && eqIndex < pair.length - 1) {
        cookies.push(pair);
      }
    }
  }
  meta.size = contentRangeSize || contentLengthSize;
  meta.cookie = cookies.join("; ");
  return meta;
}

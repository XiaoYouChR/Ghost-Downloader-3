import type {ResolveContext} from "../strategy";
import type {Resolution} from "../types";

// YouTube serves media via SABR/cipher-gated requests the page player signs itself, so the
// captured URLs aren't re-downloadable. We hand the page URL to the desktop's yt-dlp instead
// of resolving a direct URL — hence ctx's attributed URLs are deliberately ignored.
export function resolveYouTube(ctx: ResolveContext): Resolution {
  return { kind: "selection", selection: { kind: "external", pageUrl: ctx.pageUrl.href, tool: "ytdlp" } };
}

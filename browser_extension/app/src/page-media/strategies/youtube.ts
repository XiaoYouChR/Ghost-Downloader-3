import type {ResolveContext} from "../strategy";
import type {Resolution} from "../types";

// YouTube's media URLs are SABR/cipher-gated and not re-downloadable, so we delegate the page
// URL to the desktop's yt-dlp and ignore captured URLs.
export function resolveYouTube(ctx: ResolveContext): Resolution {
  return { kind: "selection", selection: { kind: "external", pageUrl: ctx.pageUrl.href } };
}

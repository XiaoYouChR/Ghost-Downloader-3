import type {ResolveContext} from "../strategy";
import type {Resolution} from "../../types";

// Hover previews on the home and search pages play inside the card's <a href="/watch?v=...">,
// while location.href is still the listing page.
function matchVideoLink(linkUrl: string): boolean {
  if (!linkUrl) { return false; }
  const url = new URL(linkUrl);
  return (url.pathname === "/watch" && url.searchParams.has("v")) || url.pathname.startsWith("/shorts/");
}

// YouTube's media URLs are SABR/cipher-gated and not re-downloadable, so we delegate the page
// URL to the desktop's yt-dlp and ignore captured URLs.
export function selectYouTube(ctx: ResolveContext): Resolution {
  const pageUrl = matchVideoLink(ctx.hints.linkUrl) ? ctx.hints.linkUrl : ctx.pageUrl.href;
  return { kind: "selection", selection: { kind: "external", pageUrl } };
}

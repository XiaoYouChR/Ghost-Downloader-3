import type {ResolveContext} from "../strategy";
import type {Resolution} from "../types";

export function resolveYouTube(ctx: ResolveContext): Resolution {
  return { kind: "selection", selection: { kind: "external", pageUrl: ctx.pageUrl.href } };
}

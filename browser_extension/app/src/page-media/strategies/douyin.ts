import {douyinKindOf, hostEndsWith} from "../url-classify";
import {newestBy, postBindResources} from "../strategy";
import type {MediaStrategy, ResolveContext} from "../strategy";
import type {Resolution} from "../types";

// Until the next reel's MSE binds and correlation locks the URL, the prefetched URL is
// still provisionally owned by the previous reel's session. modal_id is what survives
// that window.
export class DouyinStrategy implements MediaStrategy {
  readonly id = "douyin";

  matches(pageUrl: URL): boolean {
    return pageUrl.hostname === "www.douyin.com" || pageUrl.hostname.endsWith(".douyin.com");
  }

  resolve(ctx: ResolveContext): Resolution {
    const post = postBindResources(ctx.clicked).filter((r) => hostEndsWith(r.url, "douyinvod.com"));

    if (ctx.clicked.formKind === "muxed") {
      const muxed = newestBy(post.filter((r) => douyinKindOf(r.url) === "muxed"), (r) => r.capturedAt);
      if (muxed) {
        return { kind: "selection", selection: { kind: "single", url: muxed.url, formKind: "muxed" } };
      }
      const fromModalId = this.findByModalId(ctx, "muxed");
      if (fromModalId) {
        return { kind: "selection", selection: { kind: "single", url: fromModalId, formKind: "muxed" } };
      }
      return { kind: "pending", reason: "等待 Douyin 单 MP4 URL" };
    }

    if (ctx.clicked.formKind === "dash") {
      const video = newestBy(post.filter((r) => douyinKindOf(r.url) === "video"), (r) => r.capturedAt);
      const audio = newestBy(post.filter((r) => douyinKindOf(r.url) === "audio"), (r) => r.capturedAt);
      if (video && audio) {
        return { kind: "selection", selection: { kind: "merge", video: video.url, audio: audio.url } };
      }
      return { kind: "pending", reason: "等待 Douyin 音视频分轨齐全" };
    }

    // formKind unknown — MSE hasn't reported yet.
    if (post.length === 0) {
      const fromModalId = this.findByModalId(ctx, "muxed");
      if (fromModalId) {
        return { kind: "selection", selection: { kind: "single", url: fromModalId, formKind: "unknown" } };
      }
      return { kind: "pending", reason: "等待嗅探到当前视频资源" };
    }
    const muxed = newestBy(post.filter((r) => douyinKindOf(r.url) === "muxed"), (r) => r.capturedAt);
    if (muxed) {
      return { kind: "selection", selection: { kind: "single", url: muxed.url, formKind: "unknown" } };
    }
    const video = newestBy(post.filter((r) => douyinKindOf(r.url) === "video"), (r) => r.capturedAt);
    const audio = newestBy(post.filter((r) => douyinKindOf(r.url) === "audio"), (r) => r.capturedAt);
    if (video && audio) {
      return { kind: "selection", selection: { kind: "merge", video: video.url, audio: audio.url } };
    }
    return { kind: "refused", message: "无法判定 Douyin 当前媒体形态，请在资源嗅探页选择" };
  }

  // Ledger query crosses session boundaries — that's what lets us pick the prefetched
  // URL even when it's still provisionally owned by the previous reel.
  private findByModalId(ctx: ResolveContext, kind: "muxed" | "video" | "audio"): string | undefined {
    const modalId = ctx.pageUrl.searchParams.get("modal_id");
    if (!modalId || modalId.length < 4) { return undefined; }
    const matches = ctx.findUrlsByDiscriminator(`__vid=${modalId}`);
    const filtered = matches.filter((m) => douyinKindOf(m.url) === kind);
    return newestBy(filtered, (m) => m.capturedAt)?.url;
  }
}

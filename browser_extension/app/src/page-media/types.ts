export type VideoSessionState =
  | "inert"
  | "armed"
  | "ready"
  | "waiting"
  | "resolving"
  | "dispatched"
  | "failed"
  | "refused";

// muxed = one SourceBuffer with A+V interleaved; dash = separate video/audio buffers.
export type VideoSessionFormKind = "muxed" | "dash" | "unknown";

export type AttributionTier = 0 | 1 | 2 | 3 | "mse";

// Metadata about one 归属 URL (Attributed URL) within a session; the URL itself is the map key.
export type AttributedUrlMeta = {
  contentType: string;
  capturedAt: number;
  tier: AttributionTier;
  lockedByMse: boolean;
};

export type MseAttributionSignal =
  | { kind: "mse_objecturl"; mediaSourceId: string; objectUrl: string }
  | { kind: "mse_source_buffer_added"; mediaSourceId: string; mimeType: string }
  | { kind: "mse_buffer_appended"; mediaSourceId: string; mimeType: string }
  | { kind: "request_completed"; url: string; contentType: string }
  | { kind: "media_metadata"; urls: string[]; duration: number; videoWidth: number; videoHeight: number; posterUrl: string };

export type VideoSession = {
  id: string;
  elementRef: WeakRef<HTMLMediaElement>;
  src: string;
  state: VideoSessionState;
  startedAt: number;
  // performance.now() at bindBlobToMediaSource; strategies filter capturedAt > lastBoundAt.
  lastBoundAt: number;
  attributedUrls: Map<string, AttributedUrlMeta>;
  mimeTypes: Set<string>;
  mediaSourceIds: Set<string>;
  idHints: Set<string>;
  formKind: VideoSessionFormKind;
};

export type Selection =
  | { kind: "single"; url: string; formKind: VideoSessionFormKind }
  | { kind: "stream"; url: string }
  | { kind: "merge"; video: string; audio: string }
  // The page URL handed to the desktop's yt-dlp, which extracts the media itself (YouTube/SABR).
  | { kind: "external"; pageUrl: string };

export type Resolution =
  | { kind: "selection"; selection: Selection }
  | { kind: "pending"; reason: string }
  | { kind: "refused"; message: string };

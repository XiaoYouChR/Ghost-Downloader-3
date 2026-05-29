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

export type VideoSessionResource = {
  contentType: string;
  capturedAt: number;
  tier: AttributionTier;
  lockedByMse: boolean;
};

export type MseAttributionSignal =
  | { kind: "attribution_ready" }
  | { kind: "mse_objecturl"; mediaSourceId: string; objectUrl: string }
  | { kind: "mse_source_buffer_added"; mediaSourceId: string; mimeType: string }
  | { kind: "mse_buffer_appended"; mediaSourceId: string; mimeType: string; byteLength: number }
  | { kind: "fetch_completed"; url: string; status: number; contentType: string; contentLength: number }
  | { kind: "xhr_completed"; url: string; status: number; contentType: string; contentLength: number };

export type VideoSession = {
  id: string;
  elementRef: WeakRef<HTMLMediaElement>;
  src: string;
  state: VideoSessionState;
  startedAt: number;
  // performance.now() at bindBlobToMediaSource; strategies filter capturedAt > lastBoundAt.
  lastBoundAt: number;
  resources: Map<string, VideoSessionResource>;
  mimeTypes: Set<string>;
  mediaSourceIds: Set<string>;
  discriminators: Set<string>;
  formKind: VideoSessionFormKind;
};

export type Selection =
  | { kind: "single"; url: string; formKind: VideoSessionFormKind }
  | { kind: "stream"; url: string }
  | { kind: "merge"; video: string; audio: string };

export type Resolution =
  | { kind: "selection"; selection: Selection }
  | { kind: "pending"; reason: string }
  | { kind: "refused"; message: string };

export type PopupView = "tasks" | "resources" | "advanced" | "settings";
export type TaskAction = "toggle_pause" | "redownload" | "open_file" | "open_folder" | "cancel";

export type DesktopConnectionState =
  | "missing_token"
  | "connecting"
  | "authenticating"
  | "connected"
  | "unauthorized"
  | "disconnected";

export type ResourceFilter = "all" | "video" | "audio" | "streaming";
export type ResourceScope = "current" | "other";
export type ResourceCollectionState = "restoring" | "ready" | "unavailable";

export type AdvancedFeatureKey =
  | "recorder"
  | "webrtc"
  | "recorder2"
  | "mobileUserAgent"
  | "search"
  | "catch";

export interface GenericTaskSummary {
  taskId: string;
  title: string;
  status: string;
  progress: number;
  receivedBytes: number;
  fileSize: number;
  speed: number;
  createdAt: number;
  resolvePath: string;
  parentPath: string;
  canPause: boolean;
  canOpenFile: boolean;
  canOpenFolder: boolean;
  fileExt: string;
  packName: string;
}

export interface CapturedResource {
  id: string;
  tabId: number;
  url: string;
  pageTitle: string;
  pageUrl: string;
  filename: string;
  mime: string;
  size: number;
  referer: string;
  requestHeaders: Record<string, string>;
  capturedAt: number;
  sentToDesktopAt?: number;
}

export interface TaskCounters {
  total: number;
  active: number;
  completed: number;
}

export interface FeatureStateMap {
  recorder: boolean;
  webrtc: boolean;
  recorder2: boolean;
  mobileUserAgent: boolean;
  search: boolean;
  catch: boolean;
}

export interface MediaTabOption {
  tabId: number;
  title: string;
  domain: string;
}

export interface MediaItemOption {
  index: number;
  label: string;
  type: "video" | "audio";
}

export interface MediaPlaybackState {
  available: boolean;
  stale: boolean;
  message: string;
  tabId: number | null;
  mediaIndex: number;
  frameId: number;
  count: number;
  currentTime: number;
  duration: number;
  progress: number;
  volume: number;
  paused: boolean;
  loop: boolean;
  muted: boolean;
  speed: number;
  mediaType: "video" | "audio" | "";
}

export interface PopupStatePayload {
  connectionState: DesktopConnectionState;
  connectionMessage: string;
  desktopVersion: string;
  token: string;
  serverUrl: string;
  interceptDownloads: boolean;
  tasks: GenericTaskSummary[];
  taskCounters: TaskCounters;
  resourceState: ResourceCollectionState;
  resourceStateMessage: string;
  currentResources: CapturedResource[];
  otherResources: CapturedResource[];
  tabId: number | null;
  activePageDomain: string;
  featureStates: FeatureStateMap;
  mediaTabs: MediaTabOption[];
  mediaItems: MediaItemOption[];
  selectedMediaTabId: number | null;
  selectedMediaIndex: number;
  mediaPlaybackState: MediaPlaybackState;
}

export interface DesktopRequestResult {
  ok: boolean;
  message?: string;
  taskId?: string;
}

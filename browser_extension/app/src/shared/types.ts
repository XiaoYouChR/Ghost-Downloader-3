export type PopupView = "tasks" | "resources" | "images" | "advanced" | "settings";
export type TaskAction = "toggle_pause" | "redownload" | "open_file" | "open_folder" | "cancel" | "open_when_done";
export type MediaAction =
  | "toggle_play"
  | "set_speed"
  | "pip"
  | "screenshot"
  | "toggle_loop"
  | "toggle_muted"
  | "set_volume"
  | "set_time"
  | "fullscreen";
export type ThemePreference = "system" | "light" | "dark";

export type DesktopConnectionState =
  | "missing_token"
  | "connecting"
  | "authenticating"
  | "connected"
  | "unauthorized"
  | "disconnected";

export type ResourceFilter = "all" | "video" | "audio";
export type ResourceScope = "current" | "other";
export type ResourceCollectionState = "restoring" | "ready" | "unavailable";

export type AdvancedFeatureKey =
  | "recorder"
  | "webrtc"
  | "recorder2"
  | "mobileUserAgent"
  | "search"
  | "catch";

export interface TaskSummary {
  taskId: string;
  name: string;
  status: string;
  progress: number;
  receivedBytes: number;
  fileSize: number;
  speed: number;
  createdAt: number;
  canPause: boolean;
  canOpenFile: boolean;
  canOpenFolder: boolean;
  shouldOpenWhenDone: boolean;
  fileExt: string;
  packName: string;
}

export interface Resource {
  id: string;
  tabId: number;
  url: string;
  pageTitle: string;
  pageUrl: string;
  filename: string;
  mime: string;
  size: number;
  supportsRange: boolean;
  referer: string;
  requestHeaders: Record<string, string>;
  capturedAt: number;
  sentToDesktopAt?: number;
  duration?: number;
  videoWidth?: number;
  videoHeight?: number;
  posterUrl?: string;
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

export interface MediaItemOption {
  index: number;
  label: string;
}

export interface MediaPlaybackState {
  isAvailable: boolean;
  message: string;
  tabId: number | null;
  mediaIndex: number;
  currentTime: number;
  duration: number;
  progress: number;
  volume: number;
  isPaused: boolean;
  shouldLoop: boolean;
  isMuted: boolean;
  speed: number;
}

export interface PopupState {
  connectionState: DesktopConnectionState;
  connectionMessage: string;
  desktopVersion: string;
  token: string;
  serverUrl: string;
  shouldTakeDownloads: boolean;
  isMediaButtonEnabled: boolean;
  tasks: TaskSummary[];
  taskCounters: TaskCounters;
  resourceState: ResourceCollectionState;
  resourceStateMessage: string;
  currentResources: Resource[];
  otherResources: Resource[];
  tabId: number | null;
  activePageDomain: string;
  featureStates: FeatureStateMap;
  mediaItems: MediaItemOption[];
  mediaPlaybackState: MediaPlaybackState;
  pendingTaskCount: number;
}

export interface ScannedImage {
  src: string;
  naturalWidth: number;
  naturalHeight: number;
  alt: string;
}

export interface CommandResult {
  ok: boolean;
  message?: string;
  taskId?: string;
  playbackState?: MediaPlaybackState;
}

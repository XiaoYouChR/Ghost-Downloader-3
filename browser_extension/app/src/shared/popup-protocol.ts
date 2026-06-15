import type {
  AdvancedFeatureKey,
  PopupView,
  TaskAction,
} from "./types";

// The typed seam between the popup and the service worker. Both ends import PopupCommand:
// the popup builds one and dispatches it; the service worker dispatches it through a single
// exhaustive switch. Commands split by result family — a StateCommand mutates then reprojects
// the popup state, an ActionCommand is a one-shot that returns a DesktopRequestResult. The
// family is encoded in the type, so the result type follows from the command with no per-
// command result map to keep in sync.

export type StateCommand =
  | { type: "popup_get_state"; view: PopupView; tabId?: number | null }
  | { type: "popup_set_token"; view: PopupView; token: string }
  | { type: "popup_set_server_url"; view: PopupView; serverUrl: string }
  | { type: "popup_refresh_connection"; view: PopupView }
  | { type: "popup_set_intercept_downloads"; view: PopupView; enabled: boolean }
  | { type: "popup_set_media_download_overlay"; view: PopupView; enabled: boolean }
  | { type: "popup_set_media_index"; tabId: number; index: number };

export type ActionCommand =
  | { type: "popup_request_pairing" }
  | { type: "popup_task_action"; taskId: string; action: TaskAction }
  | { type: "popup_send_resource"; resourceId: string }
  | { type: "popup_merge_resources"; resourceIds: string[] }
  | { type: "popup_toggle_feature"; feature: AdvancedFeatureKey; tabId: number };

export type PopupCommand = StateCommand | ActionCommand;

import { ADVANCED_FEATURES } from "../shared/constants";

export const PROTOCOL_VERSION = 1;
export const RECONNECT_ALARM = "gd3-reconnect";
export const RESOURCE_LIMIT = 120;
export const HEADER_SNAPSHOT_LIMIT = 80;
export const HEADER_EXPIRATION_MS = 2 * 60 * 1000;
export const BRIDGE_PERSIST_DEBOUNCE_MS = 240;
export const MEDIA_SCAN_INTERVAL_MS = 4000;
export const MEDIA_FAILURE_THRESHOLD = 3;
export const MAIN_FRAME_ID = 0;

export const PAIR_TOKEN_KEY = "pairToken";
export const SERVER_URL_KEY = "desktopServerUrl";
export const INTERCEPT_DOWNLOADS_KEY = "interceptDownloads";
export const FEATURE_TAB_STATE_KEY = "featureTabState";
export const MEDIA_TARGET_KEY = "mediaControlTarget";

export const BRIDGE_RESOURCE_CACHE_KEY = "bridgeResourceCacheByTab";
export const BRIDGE_HEADER_SNAPSHOTS_KEY = "bridgeHeaderSnapshots";
export const BRIDGE_LAST_ACTIVE_TAB_KEY = "bridgeLastActiveTabId";

export const FEATURE_KEYS = ADVANCED_FEATURES.map((item) => item.key);

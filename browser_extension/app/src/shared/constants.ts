import type {AdvancedFeatureKey} from "./types";
import {CAT_CATCH_SCRIPT_FEATURES} from "./cat-catch";

export const DEFAULT_SERVER_URL = "ws://127.0.0.1:14370";
export const EXTENSION_VERSION = chrome.runtime.getManifest().version;

export const ADVANCED_FEATURES: Array<{
  key: AdvancedFeatureKey;
  title: string;
  description: string;
  reloadRequired?: boolean;
}> = [
  {
    key: "recorder",
    title: chrome.i18n.getMessage("videoRecording"),
    description: chrome.i18n.getMessage("videoRecordingDescription"),
  },
  {
    key: "webrtc",
    title: chrome.i18n.getMessage("recordWebRTC"),
    description: chrome.i18n.getMessage("recordWebRTCDescription"),
    reloadRequired: CAT_CATCH_SCRIPT_FEATURES.webrtc.reloadRequired,
  },
  {
    key: "recorder2",
    title: chrome.i18n.getMessage("screenCapture"),
    description: chrome.i18n.getMessage("screenCaptureDescription"),
  },
  {
    key: "mobileUserAgent",
    title: chrome.i18n.getMessage("mobileUserAgent"),
    description: chrome.i18n.getMessage("mobileUserAgentDescription"),
    reloadRequired: true,
  },
  {
    key: "search",
    title: chrome.i18n.getMessage("deepSearch"),
    description: chrome.i18n.getMessage("deepSearchDescription"),
    reloadRequired: CAT_CATCH_SCRIPT_FEATURES.search.reloadRequired,
  },
  {
    key: "catch",
    title: chrome.i18n.getMessage("cacheCapture"),
    description: chrome.i18n.getMessage("cacheCaptureDescription"),
    reloadRequired: CAT_CATCH_SCRIPT_FEATURES.catch.reloadRequired,
  },
];

export const PLAYBACK_RATE_OPTIONS = [0.5, 1, 1.5, 2];

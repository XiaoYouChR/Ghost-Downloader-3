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
    title: "视频录制",
    description: "录制网页中的视频内容",
  },
  {
    key: "webrtc",
    title: "录制 WebRTC",
    description: "录制 WebRTC 实时通信内容",
    reloadRequired: CAT_CATCH_SCRIPT_FEATURES.webrtc.reloadRequired,
  },
  {
    key: "recorder2",
    title: "屏幕捕捉",
    description: "捕捉屏幕、窗口或标签页",
  },
  {
    key: "mobileUserAgent",
    title: "模拟手机",
    description: "模拟移动设备访问页面",
    reloadRequired: true,
  },
  {
    key: "search",
    title: "深度搜索",
    description: "深入分析页面请求资源",
    reloadRequired: CAT_CATCH_SCRIPT_FEATURES.search.reloadRequired,
  },
  {
    key: "catch",
    title: "缓存捕捉",
    description: "捕捉浏览器缓存的资源",
    reloadRequired: CAT_CATCH_SCRIPT_FEATURES.catch.reloadRequired,
  },
];

export const PLAYBACK_RATE_OPTIONS = [0.5, 1, 1.5, 2];

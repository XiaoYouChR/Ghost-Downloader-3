import type { AdvancedFeatureKey, FeatureStateMap } from "../shared/types";
import {
  FEATURE_KEYS,
  FEATURE_TAB_STATE_KEY,
  MAIN_FRAME_ID,
} from "./constants";
import {
  localStorageGet,
  localStorageSet,
  reloadTab,
} from "./chrome-helpers";

type ScriptDefinition = {
  script: string;
  refresh: boolean;
  allFrames: boolean;
  world: "MAIN" | "ISOLATED";
  injectI18n: boolean;
};

const MOBILE_USER_AGENT =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1";

const SCRIPT_FEATURES: Record<Exclude<AdvancedFeatureKey, "mobileUserAgent">, ScriptDefinition> = {
  recorder: {
    script: "recorder.js",
    refresh: false,
    allFrames: true,
    world: "MAIN",
    injectI18n: true,
  },
  webrtc: {
    script: "webrtc.js",
    refresh: true,
    allFrames: true,
    world: "MAIN",
    injectI18n: true,
  },
  recorder2: {
    script: "recorder2.js",
    refresh: false,
    allFrames: false,
    world: "ISOLATED",
    injectI18n: true,
  },
  search: {
    script: "search.js",
    refresh: true,
    allFrames: true,
    world: "MAIN",
    injectI18n: false,
  },
  catch: {
    script: "catch.js",
    refresh: true,
    allFrames: true,
    world: "MAIN",
    injectI18n: true,
  },
};

export function createFeatureBridge() {
  const featureTabs = Object.fromEntries(
    FEATURE_KEYS.map((key) => [key, new Set<number>()]),
  ) as Record<AdvancedFeatureKey, Set<number>>;

  function createFeatureStateMap(tabId: number | null): FeatureStateMap {
    return FEATURE_KEYS.reduce((state, key) => {
      state[key] = tabId != null && featureTabs[key].has(tabId);
      return state;
    }, {} as FeatureStateMap);
  }

  function featureStoragePayload(): Record<AdvancedFeatureKey, number[]> {
    return FEATURE_KEYS.reduce((state, key) => {
      state[key] = Array.from(featureTabs[key]);
      return state;
    }, {} as Record<AdvancedFeatureKey, number[]>);
  }

  async function persistFeatureTabs(): Promise<void> {
    await localStorageSet({ [FEATURE_TAB_STATE_KEY]: featureStoragePayload() });
  }

  async function updateSessionRules(tabId: number, enabled: boolean): Promise<void> {
    return new Promise((resolve, reject) => {
      chrome.declarativeNetRequest.updateSessionRules(
        enabled
          ? {
              removeRuleIds: [tabId],
              addRules: [
                {
                  id: tabId,
                  action: {
                    type: "modifyHeaders",
                    requestHeaders: [
                      {
                        header: "User-Agent",
                        operation: "set",
                        value: MOBILE_USER_AGENT,
                      },
                    ],
                  },
                  condition: {
                    tabIds: [tabId],
                    resourceTypes: Object.values(chrome.declarativeNetRequest.ResourceType),
                  },
                },
              ],
            }
          : {
              removeRuleIds: [tabId],
            },
        () => {
          const lastError = chrome.runtime.lastError;
          if (lastError) {
            reject(new Error(lastError.message));
            return;
          }
          resolve();
        },
      );
    });
  }

  async function executeScriptFiles(tabId: number, definition: ScriptDefinition, frameIds?: number[]): Promise<void> {
    const files = definition.injectI18n
      ? ["catch-script/i18n.js", `catch-script/${definition.script}`]
      : [`catch-script/${definition.script}`];
    await chrome.scripting.executeScript({
      target: definition.allFrames
        ? frameIds
          ? { tabId, frameIds }
          : { tabId, allFrames: true }
        : { tabId, frameIds: frameIds ?? [MAIN_FRAME_ID] },
      files,
      injectImmediately: true,
      world: definition.world as chrome.scripting.ExecutionWorld,
    });
  }

  async function applyMobileUserAgent(tabId: number): Promise<void> {
    await chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      injectImmediately: true,
      world: "MAIN",
      args: [MOBILE_USER_AGENT],
      func: (userAgent: string) => {
        Object.defineProperty(navigator, "userAgent", {
          value: userAgent,
          writable: false,
        });
      },
    });
  }

  function featureKeyFromScript(scriptName: string): AdvancedFeatureKey | null {
    switch (scriptName) {
      case "recorder.js":
        return "recorder";
      case "webrtc.js":
        return "webrtc";
      case "recorder2.js":
        return "recorder2";
      case "search.js":
        return "search";
      case "catch.js":
        return "catch";
      default:
        return null;
    }
  }

  async function setFeatureEnabled(key: AdvancedFeatureKey, tabId: number, enabled: boolean): Promise<string> {
    if (key === "mobileUserAgent") {
      if (enabled) {
        featureTabs.mobileUserAgent.add(tabId);
        await updateSessionRules(tabId, true);
        await persistFeatureTabs();
        await reloadTab(tabId);
        return "已启用模拟手机，将在刷新后生效";
      }
      featureTabs.mobileUserAgent.delete(tabId);
      await updateSessionRules(tabId, false);
      await persistFeatureTabs();
      await reloadTab(tabId);
      return "已关闭模拟手机";
    }

    const definition = SCRIPT_FEATURES[key];
    if (!definition) {
      return "";
    }

    if (enabled) {
      featureTabs[key].add(tabId);
      await persistFeatureTabs();
      if (definition.refresh) {
        await reloadTab(tabId);
        return "功能已开启，页面刷新后生效";
      }
      await executeScriptFiles(tabId, definition);
      return "功能已开启";
    }

    featureTabs[key].delete(tabId);
    await persistFeatureTabs();
    if (definition.refresh) {
      await reloadTab(tabId);
      return "功能已关闭";
    }
    return "功能后台状态已关闭，页面中的面板可在网页内自行关闭";
  }

  async function loadPersistentState() {
    const localState = await localStorageGet<{
      [FEATURE_TAB_STATE_KEY]: Partial<Record<AdvancedFeatureKey, number[]>>;
    }>({
      [FEATURE_TAB_STATE_KEY]: {},
    });

    const storedFeatureTabs = localState[FEATURE_TAB_STATE_KEY] ?? {};
    for (const key of FEATURE_KEYS) {
      featureTabs[key] = new Set<number>((storedFeatureTabs[key] ?? []).filter((value): value is number => Number.isInteger(value)));
    }

    for (const tabId of featureTabs.mobileUserAgent) {
      try {
        await updateSessionRules(tabId, true);
      } catch {
        featureTabs.mobileUserAgent.delete(tabId);
      }
    }
    await persistFeatureTabs();
  }

  async function toggleFeature(key: AdvancedFeatureKey, tabId: number): Promise<string> {
    const enabled = !featureTabs[key].has(tabId);
    return setFeatureEnabled(key, tabId, enabled);
  }

  async function handleBridgeScriptCommand(payload: Record<string, any>, sender: chrome.runtime.MessageSender) {
    if (payload.Message !== "script" || typeof payload.script !== "string") {
      return;
    }
    const tabId = sender.tab?.id;
    const key = featureKeyFromScript(String(payload.script));
    if (!tabId || !key || !featureTabs[key].has(tabId)) {
      return;
    }
    await setFeatureEnabled(key, tabId, false);
  }

  function handleTabRemoved(tabId: number) {
    for (const key of FEATURE_KEYS) {
      featureTabs[key].delete(tabId);
    }
    void updateSessionRules(tabId, false).catch(() => {
      // Ignore cleanup errors.
    });
    void persistFeatureTabs();
  }

  function handleNavigationCommitted(details: chrome.webNavigation.WebNavigationFramedCallbackDetails) {
    if (details.tabId <= 0 || !/^https?:/i.test(details.url)) {
      return;
    }

    for (const key of FEATURE_KEYS) {
      if (key === "mobileUserAgent") {
        continue;
      }
      if (!featureTabs[key].has(details.tabId)) {
        continue;
      }
      const definition = SCRIPT_FEATURES[key as Exclude<AdvancedFeatureKey, "mobileUserAgent">];
      if (!definition) {
        continue;
      }
      if (!definition.allFrames && details.frameId !== MAIN_FRAME_ID) {
        continue;
      }
      void executeScriptFiles(details.tabId, definition, definition.allFrames ? [details.frameId] : [MAIN_FRAME_ID]).catch(() => {
        // Ignore injection failures.
      });
    }

    if (details.frameId === MAIN_FRAME_ID && featureTabs.mobileUserAgent.has(details.tabId)) {
      void applyMobileUserAgent(details.tabId).catch(() => {
        // Ignore UA override failures.
      });
    }
  }

  return {
    createFeatureStateMap,
    handleBridgeScriptCommand,
    handleNavigationCommitted,
    handleTabRemoved,
    loadPersistentState,
    toggleFeature,
  };
}

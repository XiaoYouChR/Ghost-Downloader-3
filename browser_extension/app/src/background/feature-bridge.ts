import type {AdvancedFeatureKey, FeatureStateMap} from "../shared/types";
import {CAT_CATCH_SCRIPT_FEATURES, MOBILE_USER_AGENT} from "../shared/cat-catch";
import {FEATURE_KEYS, FEATURE_TAB_STATE_KEY, MAIN_FRAME_ID,} from "./constants";
import {loadLocalState, queryTabs, saveLocalState, reloadTab,} from "./chrome-helpers";

type ScriptFeatureKey = keyof typeof CAT_CATCH_SCRIPT_FEATURES;
const SCRIPT_FEATURE_KEYS = Object.keys(CAT_CATCH_SCRIPT_FEATURES) as ScriptFeatureKey[];
const FLUENT_PANEL_FEATURES = new Set<ScriptFeatureKey>(["recorder", "webrtc", "catch"]);

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

  async function saveFeatureTabs(): Promise<void> {
    await saveLocalState({
      [FEATURE_TAB_STATE_KEY]: Object.fromEntries(FEATURE_KEYS.map((key) => [key, Array.from(featureTabs[key])])),
    });
  }

  async function setSessionRule(tabId: number, enabled: boolean): Promise<void> {
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

  async function runScriptFiles(
    tabId: number,
    key: ScriptFeatureKey,
    frameIds?: number[],
  ): Promise<void> {
    const feature = CAT_CATCH_SCRIPT_FEATURES[key];
    const usesFluentPanel = FLUENT_PANEL_FEATURES.has(key);
    const target = feature.allFrames
      ? frameIds
        ? { tabId, frameIds }
        : { tabId, allFrames: true }
      : { tabId, frameIds: frameIds ?? [MAIN_FRAME_ID] };
    const world = feature.world as chrome.scripting.ExecutionWorld;
    const files = [
      ...(feature.i18n ? ["catch-script/i18n.js"] : []),
      ...(usesFluentPanel ? ["catch-script/fluent-ui.js"] : []),
      `catch-script/${feature.script}`,
    ];
    if (usesFluentPanel) {
      await chrome.scripting.executeScript({
        args: [chrome.runtime.getURL("icon48.png")],
        func: (iconUrl: string) => {
          Reflect.set(window, "CatCatchFluentUIIcon", iconUrl);
        },
        injectImmediately: true,
        target,
        world,
      });
    }
    await chrome.scripting.executeScript({
      files,
      injectImmediately: true,
      target,
      world,
    });
  }

  async function setFeatureEnabled(key: AdvancedFeatureKey, tabId: number, enabled: boolean): Promise<string> {
    if (key === "mobileUserAgent") {
      if (enabled) {
        featureTabs.mobileUserAgent.add(tabId);
      } else {
        featureTabs.mobileUserAgent.delete(tabId);
      }
      await setSessionRule(tabId, enabled);
      await saveFeatureTabs();
      await reloadTab(tabId);
      return enabled ? chrome.i18n.getMessage("mobileUserAgentEnabled") : chrome.i18n.getMessage("mobileUserAgentDisabled");
    }

    const scriptKey = key as ScriptFeatureKey;
    if (enabled) {
      featureTabs[scriptKey].add(tabId);
    } else {
      featureTabs[scriptKey].delete(tabId);
    }
    await saveFeatureTabs();

    if (CAT_CATCH_SCRIPT_FEATURES[scriptKey].reloadRequired) {
      await reloadTab(tabId);
      return enabled ? chrome.i18n.getMessage("featureEnabledAfterReload") : chrome.i18n.getMessage("featureDisabled");
    }
    if (!enabled) {
      return chrome.i18n.getMessage("featureBackgroundDisabled");
    }
    await runScriptFiles(tabId, scriptKey);
    return chrome.i18n.getMessage("featureEnabled");
  }

  async function loadPersistentState() {
    const localState = await loadLocalState<{
      [FEATURE_TAB_STATE_KEY]: Partial<Record<AdvancedFeatureKey, number[]>>;
    }>({
      [FEATURE_TAB_STATE_KEY]: {},
    });

    const storedFeatureTabs = localState[FEATURE_TAB_STATE_KEY] ?? {};
    for (const key of FEATURE_KEYS) {
      featureTabs[key] = new Set<number>((storedFeatureTabs[key] ?? []).filter((value): value is number => Number.isInteger(value)));
    }

    // featureTabs is a cache of tab-level state; tabs can close while the SW is suspended,
    // leaving stale entries that would re-apply DNR rules or trigger script injection on
    // a tab that no longer exists. Reconcile against the live tab list before re-applying.
    const liveTabs = await queryTabs({});
    const liveTabIds = new Set(liveTabs.filter(tab => tab.id != null).map(tab => tab.id!));

    for (const key of FEATURE_KEYS) {
      for (const tabId of featureTabs[key]) {
        if (liveTabIds.has(tabId)) {
          continue;
        }
        featureTabs[key].delete(tabId);
        if (key === "mobileUserAgent") {
          void setSessionRule(tabId, false).catch(() => {
            // Ignore cleanup errors for orphaned rules.
          });
        }
      }
    }

    for (const tabId of featureTabs.mobileUserAgent) {
      try {
        await setSessionRule(tabId, true);
      } catch {
        featureTabs.mobileUserAgent.delete(tabId);
      }
    }
    await saveFeatureTabs();
  }

  async function toggleFeature(key: AdvancedFeatureKey, tabId: number): Promise<string> {
    const enabled = !featureTabs[key].has(tabId);
    return setFeatureEnabled(key, tabId, enabled);
  }

  async function onBridgeScriptCommand(payload: Record<string, any>, sender: chrome.runtime.MessageSender) {
    if (payload.Message !== "script" || typeof payload.script !== "string") {
      return;
    }
    const tabId = sender.tab?.id;
    const scriptKey = payload.script.replace(/\.js$/i, "") as ScriptFeatureKey;
    if (!tabId || !SCRIPT_FEATURE_KEYS.includes(scriptKey) || !featureTabs[scriptKey].has(tabId)) {
      return;
    }
    await setFeatureEnabled(scriptKey, tabId, false);
  }

  function onTabRemoved(tabId: number) {
    for (const key of FEATURE_KEYS) {
      featureTabs[key].delete(tabId);
    }
    void setSessionRule(tabId, false).catch(() => {
      // Ignore cleanup errors.
    });
    void saveFeatureTabs();
  }

  function onNavigationCommitted(details: chrome.webNavigation.WebNavigationFramedCallbackDetails) {
    if (details.tabId <= 0 || !/^https?:/i.test(details.url)) {
      return;
    }

    if (featureTabs.mobileUserAgent.has(details.tabId)) {
      void chrome.scripting.executeScript({
        args: [MOBILE_USER_AGENT],
        target: { tabId: details.tabId, frameIds: [details.frameId] },
        func: (userAgent: string) => {
          Object.defineProperty(navigator, "userAgent", { value: userAgent, writable: false });
        },
        injectImmediately: true,
        world: "MAIN",
      }).catch(() => {
        // Ignore injection failures.
      });
    }

    for (const key of SCRIPT_FEATURE_KEYS) {
      if (!featureTabs[key].has(details.tabId)) {
        continue;
      }
      const feature = CAT_CATCH_SCRIPT_FEATURES[key];
      if (!feature.allFrames && details.frameId !== MAIN_FRAME_ID) {
        continue;
      }
      void runScriptFiles(
        details.tabId,
        key,
        feature.allFrames ? [details.frameId] : [MAIN_FRAME_ID],
      ).catch(() => {
        // Ignore injection failures.
      });
    }
  }

  return {
    createFeatureStateMap,
    onBridgeScriptCommand,
    onNavigationCommitted,
    onTabRemoved,
    loadPersistentState,
    toggleFeature,
  };
}

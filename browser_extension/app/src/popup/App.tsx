import { makeStyles } from "@fluentui/react-components";
import { useState } from "react";

import type { PopupView, ThemePreference } from "../shared/types";
import { AdvancedPage } from "./components/AdvancedPage";
import { DownloadsPage } from "./components/DownloadsPage";
import { Header } from "./components/Header";
import { ResourcesPage } from "./components/ResourcesPage";
import { SettingsPage } from "./components/SettingsPage";
import { ToastHost } from "./components/ToastHost";
import { usePopupBridge } from "./hooks/usePopupBridge";

const useStyles = makeStyles({
  root: {
    position: "relative",
    display: "flex",
    width: "100%",
    height: "100%",
    flexDirection: "column",
    overflow: "hidden",
  },
  content: {
    flex: 1,
    overflowY: "auto",
  },
});

export function App({
  themePreference,
  resolvedThemePreference,
  onThemePreferenceChange,
}: {
  themePreference: ThemePreference;
  resolvedThemePreference: Exclude<ThemePreference, "system">;
  onThemePreferenceChange: (nextPreference: ThemePreference) => void;
}) {
  const styles = useStyles();
  const [currentView, setCurrentView] = useState<PopupView>("tasks");
  const bridge = usePopupBridge(currentView);

  return (
    <div className={styles.root}>
      <Header
        currentView={currentView}
        connectionState={bridge.connectionState}
        connectionMessage={bridge.connectionMessage}
        interceptEnabled={bridge.interceptDownloads}
        interceptBusy={bridge.isUpdatingIntercept}
        onViewChange={setCurrentView}
        onInterceptToggle={(enabled) => void bridge.setInterceptDownloads(enabled)}
      />

      <main className={styles.content}>
        {currentView === "tasks" ? (
          <DownloadsPage
            tasks={bridge.sortedTasks}
            isTaskBusy={bridge.isTaskBusy}
            onTaskAction={(taskId, action) => void bridge.performTaskAction(taskId, action)}
          />
        ) : null}

        {currentView === "resources" ? (
          <ResourcesPage
            currentResources={bridge.currentResources}
            otherResources={bridge.otherResources}
            activePageDomain={bridge.activePageDomain}
            resourceState={bridge.resourceState}
            resourceStateMessage={bridge.resourceStateMessage}
            connected={bridge.isConnected}
            isResourceBusy={bridge.isResourceBusy}
            onSendResource={(resourceId) => void bridge.sendResource(resourceId)}
            onMergeResources={(resourceIds) => bridge.mergeResources(resourceIds)}
          />
        ) : null}

        {currentView === "advanced" ? (
          <AdvancedPage
            featureStates={bridge.featureStates}
            isFeatureBusy={bridge.isFeatureBusy}
            onFeatureToggle={(feature) => void bridge.toggleFeature(feature)}
            mediaTabs={bridge.mediaTabs}
            mediaItems={bridge.mediaItems}
            selectedMediaTabId={bridge.selectedMediaTabId}
            selectedMediaIndex={bridge.selectedMediaIndex}
            mediaPlaybackState={bridge.mediaPlaybackState}
            mediaBusy={bridge.isUpdatingMedia}
            onMediaTabChange={(tabId) => void bridge.setMediaTarget(tabId, -1)}
            onMediaItemChange={(index) => void bridge.setMediaTarget(bridge.selectedMediaTabId, index)}
            onMediaAction={(action, value) => void bridge.performMediaAction(action, value)}
          />
        ) : null}

        {currentView === "settings" ? (
          <SettingsPage
            connectionState={bridge.connectionState}
            connectionMessage={bridge.connectionMessage}
            desktopVersion={bridge.desktopVersion}
            token={bridge.token}
            serverUrl={bridge.serverUrl}
            savingToken={bridge.isSavingToken}
            savingServerUrl={bridge.isSavingServerUrl}
            refreshingConnection={bridge.isRefreshingConnection}
            onSaveToken={bridge.saveToken}
            onSaveServerUrl={bridge.saveServerUrl}
            onRefreshConnection={bridge.refreshConnection}
            themePreference={themePreference}
            resolvedThemePreference={resolvedThemePreference}
            onThemePreferenceChange={onThemePreferenceChange}
          />
        ) : null}
      </main>

      <ToastHost message={bridge.flashMessage} tone={bridge.flashTone} />
    </div>
  );
}

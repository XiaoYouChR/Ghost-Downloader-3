import {makeStyles} from "@fluentui/react-components";
import {useEffect, useState} from "react";

import type {PopupView, ThemePreference} from "../shared/types";
import {AdvancedPage} from "./pages/AdvancedPage";
import {DownloadsPage} from "./pages/DownloadsPage";
import {Header} from "./components/Header";
import {ImagesPage} from "./pages/ImagesPage";
import {ResourcesPage} from "./pages/ResourcesPage";
import {SettingsPage} from "./pages/SettingsPage";
import {ToastHost} from "./components/ToastHost";
import {launchDesktop} from "./launch-desktop";
import {usePopupBridge} from "./usePopupBridge";

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
    display: "flex",
    flexDirection: "column",
    flex: 1,
    overflowY: "auto",
  },
});

export function App({
  themePreference,
  onThemePreferenceChange,
}: {
  themePreference: ThemePreference;
  onThemePreferenceChange: (nextPreference: ThemePreference) => void;
}) {
  const styles = useStyles();
  const [currentView, setCurrentView] = useState<PopupView>("tasks");
  const bridge = usePopupBridge(currentView);

  useEffect(() => {
    chrome.runtime.sendMessage({ type: "popup_mounted" }, (response) => {
      void chrome.runtime.lastError;
      if (response?.autoLaunch) {
        launchDesktop();
      }
    });
  }, []);

  return (
    <div className={styles.root}>
      <Header
        currentView={currentView}
        connectionState={bridge.connectionState}
        connectionMessage={bridge.connectionMessage}
        isMediaButtonEnabled={bridge.isMediaButtonEnabled}
        isMediaButtonBusy={bridge.isUpdatingMediaButton}
        shouldTakeDownloads={bridge.shouldTakeDownloads}
        isTakeDownloadsBusy={bridge.isUpdatingTakeDownloads}
        pendingTaskCount={bridge.pendingTaskCount}
        onViewChange={setCurrentView}
        onMediaButtonToggle={(enabled) => void bridge.setMediaButtonEnabled(enabled)}
        onTakeDownloadsToggle={(enabled) => void bridge.setShouldTakeDownloads(enabled)}
        onLaunchDesktop={launchDesktop}
      />

      <main className={styles.content}>
        {currentView === "tasks" ? (
          <DownloadsPage
            tasks={bridge.sortedTasks}
            isTaskBusy={bridge.isTaskBusy}
            onTaskAction={(taskId, action) => void bridge.sendTaskAction(taskId, action)}
          />
        ) : null}

        {currentView === "images" ? (
          <ImagesPage
            connected={bridge.isConnected}
            onSendImages={(images) => bridge.sendImages(images)}
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
            mediaItems={bridge.mediaItems}
            mediaPlaybackState={bridge.mediaPlaybackState}
            onMediaItemChange={(index) => void bridge.setMediaIndex(index)}
            onMediaAction={(action, value) => void bridge.sendMediaAction(action, value)}
          />
        ) : null}

        {currentView === "settings" ? (
          <SettingsPage
            desktopVersion={bridge.desktopVersion}
            token={bridge.token}
            serverUrl={bridge.serverUrl}
            savingToken={bridge.isSavingToken}
            savingServerUrl={bridge.isSavingServerUrl}
            refreshingConnection={bridge.isRefreshingConnection}
            requestingPairing={bridge.isRequestingPairing}
            onSaveToken={bridge.saveToken}
            onSaveServerUrl={bridge.saveServerUrl}
            onRefreshConnection={bridge.refreshConnection}
            onRequestPairing={bridge.requestPairing}
            themePreference={themePreference}
            onThemePreferenceChange={onThemePreferenceChange}
          />
        ) : null}
      </main>

      <ToastHost message={bridge.toastMessage} intent={bridge.toastIntent} />
    </div>
  );
}

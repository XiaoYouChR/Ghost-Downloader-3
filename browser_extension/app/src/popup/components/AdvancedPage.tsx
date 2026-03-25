import { Body1Strong, MessageBar, MessageBarBody, MessageBarTitle, makeStyles } from "@fluentui/react-components";

import { ADVANCED_FEATURES } from "../../shared/constants";
import type {
  AdvancedFeatureKey,
  FeatureStateMap,
  MediaItemOption,
  MediaPlaybackState,
  MediaTabOption,
} from "../../shared/types";
import { FeatureToggleCard } from "./FeatureToggleCard";
import { MediaControlPanel } from "./MediaControlPanel";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: "16px",
    padding: "16px",
  },
  messageLayout: {
    display: "flex",
    alignItems: "flex-start",
    gap: "12px",
  },
  section: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
});

export function AdvancedPage({
  featureStates,
  isFeatureBusy,
  onFeatureToggle,
  mediaTabs,
  mediaItems,
  selectedMediaTabId,
  selectedMediaIndex,
  mediaPlaybackState,
  mediaBusy,
  onMediaTabChange,
  onMediaItemChange,
  onMediaAction,
}: {
  featureStates: FeatureStateMap;
  isFeatureBusy: (featureKey: AdvancedFeatureKey) => boolean;
  onFeatureToggle: (feature: AdvancedFeatureKey) => void;
  mediaTabs: MediaTabOption[];
  mediaItems: MediaItemOption[];
  selectedMediaTabId: number | null;
  selectedMediaIndex: number;
  mediaPlaybackState: MediaPlaybackState;
  mediaBusy?: boolean;
  onMediaTabChange: (tabId: number) => void;
  onMediaItemChange: (index: number) => void;
  onMediaAction: (action: string, value?: number | boolean) => void;
}) {
  const styles = useStyles();
  return (
    <div className={styles.root}>
      <MessageBar intent="info">
        <div className={styles.messageLayout}>
          <MessageBarBody>
            <MessageBarTitle>高级功能</MessageBarTitle>
            按需开启，部分功能需要页面注入或特殊权限
          </MessageBarBody>
        </div>
      </MessageBar>

      <MediaControlPanel
        mediaTabs={mediaTabs}
        mediaItems={mediaItems}
        selectedTabId={selectedMediaTabId}
        selectedIndex={selectedMediaIndex}
        playbackState={mediaPlaybackState}
        busy={mediaBusy}
        onChangeTab={onMediaTabChange}
        onChangeMedia={onMediaItemChange}
        onAction={onMediaAction}
      />

      <section className={styles.section}>
        <Body1Strong>功能开关</Body1Strong>

        {ADVANCED_FEATURES.map((feature) => (
          <FeatureToggleCard
            key={feature.key}
            featureKey={feature.key}
            title={feature.title}
            description={feature.description}
            reloadRequired={feature.reloadRequired}
            enabled={featureStates[feature.key]}
            busy={isFeatureBusy(feature.key)}
            onToggle={() => onFeatureToggle(feature.key)}
          />
        ))}
      </section>
    </div>
  );
}

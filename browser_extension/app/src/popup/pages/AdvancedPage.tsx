import {Body1Strong, makeStyles, MessageBar, MessageBarBody, MessageBarTitle} from "@fluentui/react-components";

import {ADVANCED_FEATURES} from "../../shared/constants";
import type {AdvancedFeatureKey, FeatureStateMap, MediaAction, MediaItemOption, MediaPlaybackState,} from "../../shared/types";
import {FeatureToggleCard} from "../components/FeatureToggleCard";
import {MediaControlPanel} from "../components/MediaControlPanel";

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
  mediaItems,
  mediaPlaybackState,
  onMediaItemChange,
  onMediaAction,
}: {
  featureStates: FeatureStateMap;
  isFeatureBusy: (featureKey: AdvancedFeatureKey) => boolean;
  onFeatureToggle: (feature: AdvancedFeatureKey) => void;
  mediaItems: MediaItemOption[];
  mediaPlaybackState: MediaPlaybackState;
  onMediaItemChange: (index: number) => void;
  onMediaAction: (action: MediaAction, value?: number | boolean) => void;
}) {
  const styles = useStyles();
  return (
    <div className={styles.root}>
      <MessageBar intent="info">
        <div className={styles.messageLayout}>
          <MessageBarBody>
            <MessageBarTitle>{chrome.i18n.getMessage("advancedFeatures")}</MessageBarTitle>
            {chrome.i18n.getMessage("advancedFeaturesHint")}
          </MessageBarBody>
        </div>
      </MessageBar>

      <MediaControlPanel
        mediaItems={mediaItems}
        playbackState={mediaPlaybackState}
        onChangeMedia={onMediaItemChange}
        onAction={onMediaAction}
      />

      <section className={styles.section}>
        <Body1Strong>{chrome.i18n.getMessage("featureToggles")}</Body1Strong>

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

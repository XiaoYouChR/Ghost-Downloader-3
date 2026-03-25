import { Avatar, Badge, Body1Strong, Caption1, Card, Switch, makeStyles } from "@fluentui/react-components";
import type { SwitchOnChangeData } from "@fluentui/react-components";
import { ArrowClockwiseRegular } from "@fluentui/react-icons";

import type { AdvancedFeatureKey } from "../../shared/types";
import { featureIcon } from "../lib/presenters";

const useStyles = makeStyles({
  root: {
    padding: "16px",
  },
  layout: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
  },
  body: {
    minWidth: 0,
    flex: 1,
  },
  titleRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  actions: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
});

export function FeatureToggleCard({
  featureKey,
  title,
  description,
  enabled,
  busy,
  reloadRequired,
  onToggle,
}: {
  featureKey: AdvancedFeatureKey;
  title: string;
  description: string;
  enabled: boolean;
  busy?: boolean;
  reloadRequired?: boolean;
  onToggle: () => void;
}) {
  const styles = useStyles();
  const FeatureIcon = featureIcon(featureKey);

  return (
    <Card appearance="filled-alternative" className={styles.root}>
      <div className={styles.layout}>
        <Avatar color="brand" icon={<FeatureIcon />} />

        <div className={styles.body}>
          <div className={styles.titleRow}>
            <Body1Strong>{title}</Body1Strong>
          </div>
          <Caption1>{description}</Caption1>
        </div>

        <div className={styles.actions}>
          {reloadRequired ? (
            <Badge appearance="tint" color="warning" icon={<ArrowClockwiseRegular />}>
              需刷新
            </Badge>
          ) : null}
          <Switch
            checked={enabled}
            disabled={busy}
            onChange={(_event, _data: SwitchOnChangeData) => onToggle()}
          />
        </div>
      </div>
    </Card>
  );
}

import {Badge, Button, makeStyles, Spinner} from "@fluentui/react-components";
import {
    CheckmarkCircleRegular,
    OpenRegular,
    PlugDisconnectedRegular,
    WarningRegular,
} from "@fluentui/react-icons";

import type {DesktopConnectionState} from "../../shared/types";
import {connectionLabel, connectionTone} from "../../shared/utils";
import {toneToBadgeColor} from "../fluent";

const useStyles = makeStyles({
  root: {
    display: "flex",
    alignItems: "center",
    flexShrink: 0,
    gap: "6px",
    whiteSpace: "nowrap",
  },
});

export function ConnectionStatusBadge({
  state,
  message,
  pendingCount,
  onLaunchDesktop,
}: {
  state: DesktopConnectionState;
  message: string;
  pendingCount?: number;
  onLaunchDesktop?: () => void;
}) {
  const styles = useStyles();
  const tone = connectionTone(state);
  const hasPending = (pendingCount ?? 0) > 0;

  const label = state === "connected" ? "已连接" : connectionLabel(state, message);
  const icon =
    tone === "info" ? (
      <Spinner size="tiny" />
    ) : tone === "success" ? (
      <CheckmarkCircleRegular />
    ) : tone === "warning" || tone === "danger" ? (
      <WarningRegular />
    ) : (
      <PlugDisconnectedRegular />
    );

  const badgeText = hasPending ? `${label} · ${pendingCount} 排队` : label;

  return (
    <div className={styles.root}>
      <Badge
        appearance={tone === "neutral" ? "outline" : "tint"}
        color={toneToBadgeColor(tone)}
        icon={icon}
        size="large"
      >
        {badgeText}
      </Badge>
      {onLaunchDesktop && (
        <Button
          appearance="subtle"
          aria-label="启动桌面端"
          icon={<OpenRegular />}
          size="small"
          onClick={onLaunchDesktop}
        />
      )}
    </div>
  );
}

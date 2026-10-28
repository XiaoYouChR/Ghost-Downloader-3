import {Button, makeStyles, Spinner, tokens, Tooltip, typographyStyles} from "@fluentui/react-components";
import {
    CheckmarkCircleRegular,
    Open16Regular,
    PlugDisconnectedRegular,
    WarningRegular,
} from "@fluentui/react-icons";

import type {DesktopConnectionState} from "../../shared/types";
import type {AccentTone} from "../../shared/utils";
import {connectionLabel, connectionTone} from "../../shared/utils";

const TONE_COLORS: Record<AccentTone, string> = {
  neutral: tokens.colorNeutralForeground3,
  info: tokens.colorNeutralForeground3,
  success: tokens.colorStatusSuccessForeground1,
  warning: tokens.colorStatusWarningForeground1,
  danger: tokens.colorStatusDangerForeground1,
};

const useStyles = makeStyles({
  root: {
    display: "flex",
    alignItems: "center",
    gap: "4px",
    minWidth: 0,
  },
  icon: {
    display: "flex",
    flexShrink: 0,
    fontSize: "16px",
  },
  label: {
    ...typographyStyles.caption1,
    color: tokens.colorNeutralForeground2,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  launch: {
    flexShrink: 0,
  },
  launchIcon: {
    fontSize: "16px",
    width: "16px",
    height: "16px",
  },
});

export function ConnectionStatus({
  state,
  message,
  pendingCount,
  onLaunchDesktop,
}: {
  state: DesktopConnectionState;
  message: string;
  pendingCount: number;
  onLaunchDesktop: () => void;
}) {
  const styles = useStyles();
  const tone = connectionTone(state);

  const label = state === "connected" ? chrome.i18n.getMessage("connected") : connectionLabel(state, message);
  const text = pendingCount > 0 ? chrome.i18n.getMessage("pendingQueueBadge", [label, String(pendingCount)]) : label;
  const icon =
    tone === "info" ? (
      <Spinner size="extra-tiny" />
    ) : tone === "success" ? (
      <CheckmarkCircleRegular />
    ) : tone === "warning" || tone === "danger" ? (
      <WarningRegular />
    ) : (
      <PlugDisconnectedRegular />
    );

  return (
    <div className={styles.root}>
      <span className={styles.icon} style={{ color: TONE_COLORS[tone] }}>
        {icon}
      </span>
      <Tooltip content={text} relationship="description">
        <span className={styles.label}>{text}</span>
      </Tooltip>
      <Tooltip content={chrome.i18n.getMessage("launchDesktop")} relationship="label">
        <Button
          className={styles.launch}
          appearance="subtle"
          icon={{ className: styles.launchIcon, children: <Open16Regular /> }}
          size="small"
          onClick={onLaunchDesktop}
        />
      </Tooltip>
    </div>
  );
}

import { Badge, Spinner } from "@fluentui/react-components";
import {
  CheckmarkCircleRegular,
  PlugDisconnectedRegular,
  WarningRegular,
} from "@fluentui/react-icons";

import type { DesktopConnectionState } from "../../shared/types";
import { connectionLabel, connectionTone } from "../../shared/utils";
import { toneToBadgeColor } from "../lib/fluent";

export function ConnectionStatusBadge({
  state,
  message,
}: {
  state: DesktopConnectionState;
  message: string;
}) {
  const tone = connectionTone(state);
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

  return (
    <Badge
      appearance={tone === "neutral" ? "outline" : "tint"}
      color={toneToBadgeColor(tone)}
      icon={icon}
      size="large"
    >
      {label}
    </Badge>
  );
}

import type { ComponentType } from "react";
import type { BadgeProps, MessageBarProps } from "@fluentui/react-components";
import {
  ArrowClockwiseRegular,
  CheckmarkCircleRegular,
  ClockRegular,
  DismissCircleRegular,
  PauseCircleRegular,
  PlayCircleRegular,
} from "@fluentui/react-icons";

import type { AccentTone } from "../../shared/utils";

export function toneToBadgeColor(tone: AccentTone): NonNullable<BadgeProps["color"]> {
  switch (tone) {
    case "success":
      return "success";
    case "info":
      return "informative";
    case "warning":
      return "warning";
    case "danger":
      return "danger";
    default:
      return "subtle";
  }
}

export function taskStatusToBadgeColor(status: string): NonNullable<BadgeProps["color"]> {
  switch (status) {
    case "completed":
      return "success";
    case "running":
      return "informative";
    case "paused":
      return "warning";
    case "failed":
      return "danger";
    default:
      return "subtle";
  }
}

export function taskStatusToBadgeIcon(status: string): ComponentType {
  switch (status) {
    case "completed":
      return CheckmarkCircleRegular;
    case "running":
      return ArrowClockwiseRegular;
    case "waiting":
      return ClockRegular;
    case "paused":
      return PauseCircleRegular;
    case "failed":
      return DismissCircleRegular;
    default:
      return PlayCircleRegular;
  }
}

export function flashToneToIntent(
  tone: "neutral" | "success" | "error",
): NonNullable<MessageBarProps["intent"]> {
  switch (tone) {
    case "success":
      return "success";
    case "error":
      return "error";
    default:
      return "info";
  }
}

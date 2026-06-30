import type {ComponentType} from "react";
import type {BadgeProps} from "@fluentui/react-components";
import {
    ArrowClockwiseRegular,
    CheckmarkCircleRegular,
    ClockRegular,
    DataUsageRegular,
    DismissCircleRegular,
    DocumentArrowDownRegular,
    DocumentPdfRegular,
    DocumentTableRegular,
    DocumentTextRegular,
    FolderZipRegular,
    GlobeVideoRegular,
    ImageRegular,
    MusicNote2Regular,
    PauseCircleRegular,
    PhoneRegular,
    PlayCircleRegular,
    SearchRegular,
    StorageRegular,
    TabDesktopRegular,
    VideoClipRegular,
} from "@fluentui/react-icons";

import type {AdvancedFeatureKey} from "../shared/types";
import type {AccentTone, VisualKind} from "../shared/utils";

const VISUAL_ICON_MAP: Record<VisualKind, ComponentType> = {
  download: DocumentArrowDownRegular,
  video: VideoClipRegular,
  audio: MusicNote2Regular,
  archive: FolderZipRegular,
  document: DocumentTextRegular,
  pdf: DocumentPdfRegular,
  spreadsheet: DocumentTableRegular,
  image: ImageRegular,
  stream: GlobeVideoRegular,
};

const FEATURE_ICON_MAP: Record<AdvancedFeatureKey, ComponentType> = {
  recorder: VideoClipRegular,
  webrtc: DataUsageRegular,
  recorder2: TabDesktopRegular,
  mobileUserAgent: PhoneRegular,
  search: SearchRegular,
  catch: StorageRegular,
};

export function visualIcon(kind: VisualKind) {
  return VISUAL_ICON_MAP[kind];
}

export function featureIcon(key: AdvancedFeatureKey) {
  return FEATURE_ICON_MAP[key];
}

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

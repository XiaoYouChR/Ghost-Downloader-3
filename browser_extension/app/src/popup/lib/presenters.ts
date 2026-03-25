import type { ComponentType } from "react";
import {
  DataUsageRegular,
  DocumentArrowDownRegular,
  DocumentPdfRegular,
  DocumentTableRegular,
  DocumentTextRegular,
  FolderZipRegular,
  GlobeVideoRegular,
  ImageRegular,
  MusicNote2Regular,
  PhoneRegular,
  SearchRegular,
  StorageRegular,
  TabDesktopRegular,
  VideoClipRegular,
} from "@fluentui/react-icons";
import type { AdvancedFeatureKey } from "../../shared/types";
import type { VisualKind } from "../../shared/utils";

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

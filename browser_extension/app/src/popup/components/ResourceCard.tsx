import {
    Avatar,
    Button,
    Caption1,
    Card,
    Checkbox,
    makeStyles,
    mergeClasses,
} from "@fluentui/react-components";
import {ArrowDownloadRegular, CheckmarkRegular} from "@fluentui/react-icons";

import type {Resource} from "../../shared/types";
import {describeResource, formatBytes, isDashSegment,} from "../../shared/utils";
import {visualIcon} from "../fluent";

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = String(Math.floor(seconds % 60)).padStart(2, "0");
  return `${m}:${s}`;
}

const useStyles = makeStyles({
  root: {
    padding: "8px 10px",
  },
  sent: {
    opacity: 0.55,
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  select: {
    flexShrink: 0,
  },
  mediaBox: {
    position: "relative",
    flexShrink: 0,
    width: "40px",
    height: "23px",
  },
  poster: {
    width: "40px",
    height: "23px",
    objectFit: "cover",
    borderRadius: "3px",
    display: "block",
  },
  typeOverlay: {
    position: "absolute",
    bottom: "-4px",
    right: "-4px",
  },
  body: {
    minWidth: 0,
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: "2px",
  },
  title: {
    overflow: "hidden",
    whiteSpace: "nowrap",
    textOverflow: "ellipsis",
    fontWeight: 600,
    fontSize: "13px",
    lineHeight: "18px",
  },
  meta: {
    overflow: "hidden",
    whiteSpace: "nowrap",
    textOverflow: "ellipsis",
  },
  action: {
    flexShrink: 0,
  },
});

export function ResourceCard({
  resource,
  connected,
  busy,
  selected,
  onSend,
  onSelectedChange,
}: {
  resource: Resource;
  connected: boolean;
  busy?: boolean;
  selected?: boolean;
  onSend: () => void;
  onSelectedChange?: (checked: boolean) => void;
}) {
  const styles = useStyles();
  const presentation = describeResource(resource);
  const ResourceIcon = visualIcon(presentation.visual.kind);
  const isSent = Boolean(resource.sentToDesktopAt);
  const isDash = isDashSegment(resource);

  const metaParts: string[] = [presentation.primaryBadge];
  if (resource.videoWidth && resource.videoHeight) {
    metaParts.push(`${resource.videoHeight}p`);
  }
  if (resource.duration && resource.duration > 0) {
    metaParts.push(formatDuration(resource.duration));
  }
  if (resource.size > 0) {
    metaParts.push(formatBytes(resource.size));
  }
  for (const tag of presentation.tags) {
    if (tag !== presentation.primaryBadge) {
      metaParts.push(tag);
    }
  }

  const displayTitle = isDash && resource.pageTitle
    ? resource.pageTitle
    : resource.filename || resource.pageTitle || resource.url;

  return (
    <Card
      appearance="filled-alternative"
      className={mergeClasses(styles.root, isSent && styles.sent)}
    >
      <div className={styles.row}>
        <Checkbox
          aria-label={`选择 ${displayTitle}`}
          checked={selected}
          className={styles.select}
          onChange={(_event, data) => onSelectedChange?.(Boolean(data.checked))}
        />
        {resource.posterUrl ? (
          <div className={styles.mediaBox}>
            <img alt="" className={styles.poster} src={resource.posterUrl} />
            <Avatar
              className={styles.typeOverlay}
              color="colorful"
              icon={<ResourceIcon />}
              idForColor={resource.id}
              shape="square"
              size={16}
            />
          </div>
        ) : (
          <Avatar
            color="colorful"
            icon={<ResourceIcon />}
            idForColor={resource.id}
            shape="square"
            size={24}
          />
        )}

        <div className={styles.body}>
          <div className={styles.title}>{displayTitle}</div>
          <Caption1 className={styles.meta}>{metaParts.join(" · ")}</Caption1>
        </div>

        <Button
          appearance={isSent ? "subtle" : "primary"}
          className={styles.action}
          disabled={isSent || busy || (presentation.needsDesktop && !connected)}
          icon={isSent ? <CheckmarkRegular /> : <ArrowDownloadRegular />}
          size="small"
          onClick={isSent ? undefined : onSend}
        />
      </div>
    </Card>
  );
}

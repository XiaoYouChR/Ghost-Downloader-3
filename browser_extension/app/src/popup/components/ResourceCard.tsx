import {
  Avatar,
  Badge,
  Body1Strong,
  Button,
  Caption1,
  Card,
  Checkbox,
  Link,
  makeStyles,
} from "@fluentui/react-components";
import { ArrowDownloadRegular, CheckmarkCircleRegular } from "@fluentui/react-icons";

import type { CapturedResource } from "../../shared/types";
import {
  describeResource,
  domainFromUrl,
  formatBytes,
  formatCapturedAt,
  shorten,
} from "../../shared/utils";
import { visualIcon } from "../lib/presenters";

const useStyles = makeStyles({
  root: {
    gap: "8px",
    padding: "12px",
  },
  header: {
    display: "flex",
    alignItems: "flex-start",
    gap: "10px",
  },
  select: {
    paddingTop: "2px",
    flexShrink: 0,
  },
  body: {
    minWidth: 0,
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  title: {
    display: "-webkit-box",
    overflow: "hidden",
    wordBreak: "break-word",
    WebkitLineClamp: "2",
    WebkitBoxOrient: "vertical",
  },
  tags: {
    display: "flex",
    flexWrap: "wrap",
    gap: "6px",
  },
  meta: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    flexWrap: "wrap",
  },
  url: {
    overflow: "hidden",
    whiteSpace: "nowrap",
    textOverflow: "ellipsis",
  },
  action: {
    alignSelf: "flex-start",
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
  resource: CapturedResource;
  connected: boolean;
  busy?: boolean;
  selected?: boolean;
  onSend: () => void;
  onSelectedChange?: (checked: boolean) => void;
}) {
  const styles = useStyles();
  const presentation = describeResource(resource);
  const ResourceIcon = visualIcon(presentation.visual.kind);
  const sourceDomain = domainFromUrl(resource.pageUrl || resource.url) || "当前页面";

  return (
    <Card appearance="filled-alternative" className={styles.root}>
      <div className={styles.header}>
        <Checkbox
          aria-label={`选择 ${resource.filename || resource.url}`}
          checked={selected}
          className={styles.select}
          onChange={(_event, data) => onSelectedChange?.(Boolean(data.checked))}
        />
        <Avatar
          aria-label={resource.filename || resource.url}
          color="colorful"
          icon={<ResourceIcon />}
          idForColor={resource.id}
          shape="square"
          size={36}
        />

        <div className={styles.body}>
          <Body1Strong className={styles.title}>{resource.filename || resource.url}</Body1Strong>

          <div className={styles.tags}>
            {presentation.tags.map((tag) => (
              <Badge key={tag} appearance="tint" color="brand" size="small">
                {tag}
              </Badge>
            ))}
          </div>

          <div className={styles.meta}>
            {resource.size > 0 ? <Caption1>{formatBytes(resource.size)}</Caption1> : null}
            <Caption1>{sourceDomain}</Caption1>
            <Caption1>{formatCapturedAt(resource.capturedAt)}</Caption1>
          </div>

          <Link
            appearance="subtle"
            className={styles.url}
            href={resource.url}
            rel="noreferrer"
            target="_blank"
          >
            {shorten(resource.url, 68)}
          </Link>

          {resource.sentToDesktopAt ? (
            <Button
              appearance="secondary"
              className={styles.action}
              icon={<CheckmarkCircleRegular />}
              size="small"
            >
              {presentation.statusText}
            </Button>
          ) : (
            <Button
              appearance="primary"
              className={styles.action}
              disabled={busy || (presentation.needsDesktop && !connected)}
              icon={<ArrowDownloadRegular />}
              size="small"
              onClick={onSend}
            >
              {presentation.actionLabel}
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}

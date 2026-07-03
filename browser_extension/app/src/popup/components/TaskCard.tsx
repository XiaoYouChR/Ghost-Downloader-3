import {Avatar, Button, Caption1, Card, makeStyles, ProgressBar, tokens} from "@fluentui/react-components";
import {
    ArrowClockwiseRegular,
    DismissRegular,
    FolderOpenRegular,
    OpenRegular,
    PauseRegular,
    PlayRegular,
} from "@fluentui/react-icons";

import type {TaskAction, TaskSummary} from "../../shared/types";
import {formatBytes, formatTaskMetric, taskVisual} from "../../shared/utils";
import {visualIcon} from "../fluent";

const useStyles = makeStyles({
  root: {
    position: "relative",
    padding: "8px 10px",
    overflow: "hidden",
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
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
    cursor: "default",
  },
  metaClickable: {
    cursor: "pointer",
    "&:hover": {
      textDecoration: "underline",
    },
  },
  openWhenDone: {
    color: tokens.colorBrandForeground1,
  },
  actions: {
    display: "flex",
    alignItems: "center",
    flexShrink: 0,
    gap: "2px",
  },
  progress: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    borderRadius: 0,
  },
});

function metaText(task: TaskSummary): string {
  const sizePart = task.fileSize > 0
    ? `${formatBytes(task.receivedBytes)} / ${formatBytes(task.fileSize)}`
    : task.receivedBytes > 0
      ? formatBytes(task.receivedBytes)
      : "";

  if (task.shouldOpenWhenDone && task.status !== "completed") {
    return [chrome.i18n.getMessage("openWhenDone"), sizePart].filter(Boolean).join(" · ");
  }

  switch (task.status) {
    case "running":
      return [formatTaskMetric(task), sizePart].filter(Boolean).join(" · ");
    case "waiting":
      return [chrome.i18n.getMessage("waiting"), sizePart].filter(Boolean).join(" · ");
    case "paused":
      return [chrome.i18n.getMessage("paused"), sizePart].filter(Boolean).join(" · ");
    case "failed":
      return [chrome.i18n.getMessage("failed"), sizePart].filter(Boolean).join(" · ");
    case "completed":
      return [chrome.i18n.getMessage("completed"), task.fileSize > 0 ? formatBytes(task.fileSize) : ""].filter(Boolean).join(" · ");
    default:
      return task.status;
  }
}

function progressColor(status: string): "brand" | "warning" | "error" {
  switch (status) {
    case "paused":
      return "warning";
    case "failed":
      return "error";
    default:
      return "brand";
  }
}

export function TaskCard({
  task,
  busy,
  onAction,
}: {
  task: TaskSummary;
  busy?: boolean;
  onAction: (action: TaskAction) => void;
}) {
  const styles = useStyles();
  const visual = taskVisual(task);
  const TaskIcon = visualIcon(visual.kind);
  const isCompleted = task.status === "completed";
  const isRunning = task.status === "running";
  const isActive = isRunning || task.status === "waiting";
  const isPausedOrFailed = task.status === "paused" || task.status === "failed" || task.status === "waiting";
  const showProgress = !isCompleted;
  const progressValue = task.status === "waiting" ? undefined : Math.max(0, Math.min(100, task.progress)) / 100;

  const metaClassName = isActive
    ? `${styles.meta} ${styles.metaClickable}${task.shouldOpenWhenDone ? ` ${styles.openWhenDone}` : ""}`
    : styles.meta;

  return (
    <Card appearance="filled-alternative" className={styles.root}>
      <div className={styles.row}>
        <Avatar
          color="colorful"
          icon={<TaskIcon />}
          idForColor={task.taskId}
          shape="square"
          size={24}
        />

        <div className={styles.body}>
          <div className={styles.title}>{task.name}</div>
          <Caption1
            className={metaClassName}
            onClick={isActive ? () => onAction("open_when_done") : undefined}
          >
            {metaText(task)}
          </Caption1>
        </div>

        <div className={styles.actions}>
          {isCompleted && (
            <>
              <Button
                appearance="subtle"
                disabled={busy}
                icon={<ArrowClockwiseRegular />}
                aria-label={chrome.i18n.getMessage("redownload")}
                size="small"
                onClick={() => onAction("redownload")}
              />
              <Button
                appearance="subtle"
                disabled={busy || !task.canOpenFile}
                icon={<OpenRegular />}
                aria-label={chrome.i18n.getMessage("openFile")}
                size="small"
                onClick={() => onAction("open_file")}
              />
              <Button
                appearance="subtle"
                disabled={busy || !task.canOpenFolder}
                icon={<FolderOpenRegular />}
                aria-label={chrome.i18n.getMessage("openFolder")}
                size="small"
                onClick={() => onAction("open_folder")}
              />
            </>
          )}
          {isRunning && (
            <Button
              appearance="subtle"
              disabled={busy || !task.canPause}
              icon={<PauseRegular />}
              aria-label={chrome.i18n.getMessage("pause")}
              size="small"
              onClick={() => onAction("toggle_pause")}
            />
          )}
          {isPausedOrFailed && (
            <Button
              appearance="subtle"
              disabled={busy}
              icon={<PlayRegular />}
              aria-label={chrome.i18n.getMessage("resume")}
              size="small"
              onClick={() => onAction("toggle_pause")}
            />
          )}
          <Button
            appearance="subtle"
            disabled={busy}
            icon={<DismissRegular />}
            aria-label={chrome.i18n.getMessage("cancel")}
            size="small"
            onClick={() => onAction("cancel")}
          />
        </div>
      </div>

      {showProgress && (
        <ProgressBar
          className={styles.progress}
          color={progressColor(task.status)}
          thickness="medium"
          value={progressValue}
        />
      )}
    </Card>
  );
}

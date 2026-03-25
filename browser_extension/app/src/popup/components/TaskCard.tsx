import {
  Avatar,
  Badge,
  Body1Strong,
  Button,
  Caption1,
  Card,
  makeStyles,
  ProgressBar,
} from "@fluentui/react-components";
import {
  ArrowClockwiseRegular,
  DismissRegular,
  FolderOpenRegular,
  OpenRegular,
  PauseRegular,
  PlayRegular,
} from "@fluentui/react-icons";

import type { GenericTaskSummary, TaskAction } from "../../shared/types";
import {
  formatBytes,
  formatTaskMetric,
  formatTaskStatus,
  taskActionLabel,
  taskVisual,
} from "../../shared/utils";
import { taskStatusToBadgeColor, taskStatusToBadgeIcon } from "../lib/fluent";
import { visualIcon } from "../lib/presenters";

const useStyles = makeStyles({
  root: {
    gap: "6px",
    padding: "10px",
  },
  header: {
    display: "flex",
    alignItems: "flex-start",
    gap: "8px",
  },
  body: {
    minWidth: 0,
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  titleRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: "6px",
  },
  title: {
    flex: 1,
    display: "-webkit-box",
    overflow: "hidden",
    WebkitLineClamp: "2",
    WebkitBoxOrient: "vertical",
  },
  status: {
    flexShrink: 0,
  },
  progress: {
    marginTop: "2px",
  },
  footer: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "8px",
    flexWrap: "wrap",
  },
  metrics: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    flexWrap: "wrap",
    minWidth: 0,
  },
  actions: {
    display: "flex",
    alignItems: "center",
    flexWrap: "wrap",
    gap: "6px",
    marginLeft: "auto",
  },
  dismissButton: {
    minWidth: "auto",
  },
});

export function TaskCard({
  task,
  busy,
  onAction,
}: {
  task: GenericTaskSummary;
  busy?: boolean;
  onAction: (action: TaskAction) => void;
}) {
  const styles = useStyles();
  const visual = taskVisual(task);
  const TaskIcon = visualIcon(visual.kind);
  const StatusIcon = taskStatusToBadgeIcon(task.status);
  const primaryAction = taskActionLabel(task);
  const showProgress = task.status !== "completed";
  const showRedownload = task.status === "completed";
  const showOpenActions = task.status === "completed";
  const metric = task.status === "completed"
    ? (task.fileSize > 0 ? formatBytes(task.fileSize) : "--")
    : formatTaskMetric(task);

  return (
    <Card appearance="filled-alternative" className={styles.root}>
      <div className={styles.header}>
        <Avatar
          aria-label={task.title}
          color="colorful"
          icon={<TaskIcon />}
          idForColor={task.taskId}
          shape="square"
          size={32}
        />

        <div className={styles.body}>
          <div className={styles.titleRow}>
            <Body1Strong className={styles.title}>{task.title}</Body1Strong>
            <Badge
              appearance="tint"
              className={styles.status}
              color={taskStatusToBadgeColor(task.status)}
              icon={<StatusIcon />}
              size="medium"
            >
              {formatTaskStatus(task.status)}
            </Badge>
          </div>

          {showProgress ? (
            <ProgressBar
              className={styles.progress}
              thickness="medium"
              value={Math.max(0, Math.min(100, task.progress)) / 100}
            />
          ) : null}

          <div className={styles.footer}>
            <div className={styles.metrics}>
              <Caption1>{`${Math.max(0, Math.round(task.progress))}%`}</Caption1>
              <Caption1>{metric}</Caption1>
            </div>

            <div className={styles.actions}>
              {showRedownload ? (
                <Button
                  disabled={busy}
                  icon={<ArrowClockwiseRegular />}
                  size="small"
                  onClick={() => onAction("redownload")}
                >
                  重新下载
                </Button>
              ) : null}

              {showOpenActions ? (
                <>
                  <Button
                    disabled={busy || !task.canOpenFile}
                    icon={<OpenRegular />}
                    size="small"
                    onClick={() => onAction("open_file")}
                  >
                    打开文件
                  </Button>
                  <Button
                    disabled={busy || !task.canOpenFolder}
                    icon={<FolderOpenRegular />}
                    size="small"
                    onClick={() => onAction("open_folder")}
                  >
                    打开文件夹
                  </Button>
                </>
              ) : primaryAction ? (
                <Button
                  disabled={busy || (task.status === "running" && !task.canPause)}
                  icon={task.status === "running" ? <PauseRegular /> : <PlayRegular />}
                  size="small"
                  onClick={() => onAction("toggle_pause")}
                >
                  {primaryAction}
                </Button>
              ) : null}

              <Button
                appearance="subtle"
                className={styles.dismissButton}
                disabled={busy}
                icon={<DismissRegular />}
                aria-label="取消"
                size="small"
                onClick={() => onAction("cancel")}
              />
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}

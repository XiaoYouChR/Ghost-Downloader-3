import {ArrowDownloadRegular} from "@fluentui/react-icons";
import {makeStyles} from "@fluentui/react-components";

import type {TaskSummary, TaskAction} from "../../shared/types";
import {EmptyState} from "../components/EmptyState";
import {TaskCard} from "../components/TaskCard";

const useStyles = makeStyles({
  empty: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    padding: "14px",
  },
  root: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    gap: "10px",
    padding: "14px",
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  },
});

export function DownloadsPage({
  tasks,
  isTaskBusy,
  onTaskAction,
}: {
  tasks: TaskSummary[];
  isTaskBusy: (taskId: string) => boolean;
  onTaskAction: (taskId: string, action: TaskAction) => void;
}) {
  const styles = useStyles();

  if (tasks.length === 0) {
    return (
      <div className={styles.empty}>
        <EmptyState
          icon={<ArrowDownloadRegular />}
          title={chrome.i18n.getMessage("emptyTasksTitle")}
          description={chrome.i18n.getMessage("emptyTasksDescription")}
        />
      </div>
    );
  }

  return (
    <div className={styles.root}>
      <section className={styles.list}>
        {tasks.map((task) => (
          <TaskCard
            key={task.taskId}
            task={task}
            busy={isTaskBusy(task.taskId)}
            onAction={(action) => onTaskAction(task.taskId, action)}
          />
        ))}
      </section>
    </div>
  );
}

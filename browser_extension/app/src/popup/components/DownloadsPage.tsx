import { ArrowDownloadRegular } from "@fluentui/react-icons";
import { makeStyles } from "@fluentui/react-components";

import type { GenericTaskSummary, TaskAction } from "../../shared/types";
import { EmptyState } from "./EmptyState";
import { TaskCard } from "./TaskCard";

const useStyles = makeStyles({
  empty: {
    padding: "14px",
  },
  root: {
    display: "flex",
    flexDirection: "column",
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
  tasks: GenericTaskSummary[];
  isTaskBusy: (taskId: string) => boolean;
  onTaskAction: (taskId: string, action: TaskAction) => void;
}) {
  const styles = useStyles();

  if (tasks.length === 0) {
    return (
      <div className={styles.empty}>
        <EmptyState
          icon={<ArrowDownloadRegular />}
          title="当前还没有任务"
          description="浏览器接管下载或从资源嗅探页发送资源后，任务会出现在这里。"
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

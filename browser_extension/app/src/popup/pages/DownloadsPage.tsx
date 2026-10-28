import {useEffect, useMemo, useState} from "react";
import {
    Button,
    makeStyles,
    Menu,
    MenuButton,
    MenuDivider,
    MenuItem,
    MenuItemRadio,
    MenuList,
    MenuPopover,
    MenuTrigger,
    SearchBox,
    Tooltip,
} from "@fluentui/react-components";
import {
    ArrowDownloadRegular,
    ArrowSortDownRegular,
    ArrowSortUpRegular,
    DeleteRegular,
    MoreHorizontalRegular,
    SearchRegular,
} from "@fluentui/react-icons";

import type {SortDirection, TaskAction, TaskSort, TaskSortField, TaskSummary} from "../../shared/types";
import {EmptyState} from "../components/EmptyState";
import {TaskCard} from "../components/TaskCard";
import {buildTaskView} from "../task-view";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    gap: "8px",
    padding: "12px 16px",
  },
  toolbar: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  searchBox: {
    flex: 1,
    minWidth: 0,
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  },
});

const SORT_FIELD_LABELS: Record<TaskSortField, string> = {
  time: chrome.i18n.getMessage("sortByTime"),
  status: chrome.i18n.getMessage("sortByStatus"),
  name: chrome.i18n.getMessage("sortByName"),
  size: chrome.i18n.getMessage("sortBySize"),
};

const SORT_DIRECTION_LABELS: Record<SortDirection, string> = {
  asc: chrome.i18n.getMessage("sortAscending"),
  desc: chrome.i18n.getMessage("sortDescending"),
};

const DEFAULT_SORT: TaskSort = { field: "time", direction: "desc" };

const SORT_STORAGE_KEY = "gd4bTaskSort";

function isTaskSort(value: unknown): value is TaskSort {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const { field, direction } = value as Record<string, unknown>;
  return typeof field === "string" && Object.hasOwn(SORT_FIELD_LABELS, field)
    && typeof direction === "string" && Object.hasOwn(SORT_DIRECTION_LABELS, direction);
}

export function DownloadsPage({
  tasks,
  connected,
  isTaskBusy,
  onTaskAction,
  onRemoveTasks,
}: {
  tasks: TaskSummary[];
  connected: boolean;
  isTaskBusy: (taskId: string) => boolean;
  onTaskAction: (taskId: string, action: TaskAction) => void;
  onRemoveTasks: (taskIds: string[]) => void;
}) {
  const styles = useStyles();
  const [text, setText] = useState("");
  const [sort, setSort] = useState<TaskSort>(DEFAULT_SORT);

  const visibleTasks = useMemo(() => buildTaskView(tasks, { text, sort }), [tasks, text, sort]);
  const completedTaskIds = useMemo(
    () => tasks.filter((task) => task.status === "completed").map((task) => task.taskId),
    [tasks],
  );

  useEffect(() => {
    void chrome.storage.local
      .get(SORT_STORAGE_KEY)
      .then((stored) => {
        const value = stored[SORT_STORAGE_KEY];
        if (isTaskSort(value)) {
          setSort(value);
        }
      })
      .catch(() => {
        // Keep the default sort when storage is unavailable.
      });
  }, []);

  function saveSort(next: TaskSort) {
    setSort(next);
    void chrome.storage.local.set({ [SORT_STORAGE_KEY]: next });
  }

  if (tasks.length === 0) {
    return (
      <div className={styles.root}>
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
      <div className={styles.toolbar}>
        <SearchBox
          className={styles.searchBox}
          placeholder={chrome.i18n.getMessage("searchTasksPlaceholder")}
          size="small"
          value={text}
          onChange={(_e, data) => setText(data.value)}
        />
        <Menu
          checkedValues={{ field: [sort.field], direction: [sort.direction] }}
          onCheckedValueChange={(_e, data) => saveSort(data.name === "field"
            ? { ...sort, field: data.checkedItems[0] as TaskSortField }
            : { ...sort, direction: data.checkedItems[0] as SortDirection })}
        >
          <MenuTrigger disableButtonEnhancement>
            <MenuButton
              appearance="subtle"
              icon={sort.direction === "asc" ? <ArrowSortUpRegular /> : <ArrowSortDownRegular />}
              size="small"
            >
              {SORT_FIELD_LABELS[sort.field]}
            </MenuButton>
          </MenuTrigger>
          <MenuPopover>
            <MenuList>
              {(Object.keys(SORT_FIELD_LABELS) as TaskSortField[]).map((field) => (
                <MenuItemRadio key={field} name="field" value={field}>{SORT_FIELD_LABELS[field]}</MenuItemRadio>
              ))}
              <MenuDivider />
              {(Object.keys(SORT_DIRECTION_LABELS) as SortDirection[]).map((direction) => (
                <MenuItemRadio key={direction} name="direction" value={direction}>{SORT_DIRECTION_LABELS[direction]}</MenuItemRadio>
              ))}
            </MenuList>
          </MenuPopover>
        </Menu>
        <Menu>
          <MenuTrigger disableButtonEnhancement>
            <Tooltip content={chrome.i18n.getMessage("moreOptions")} relationship="label">
              <Button appearance="subtle" icon={<MoreHorizontalRegular />} size="small" />
            </Tooltip>
          </MenuTrigger>
          <MenuPopover>
            <MenuList>
              <MenuItem
                icon={<DeleteRegular />}
                secondaryContent={String(completedTaskIds.length)}
                disabled={!connected || completedTaskIds.length === 0}
                onClick={() => onRemoveTasks(completedTaskIds)}
              >
                {chrome.i18n.getMessage("removeCompletedTasks")}
              </MenuItem>
            </MenuList>
          </MenuPopover>
        </Menu>
      </div>

      {visibleTasks.length === 0 ? (
        <EmptyState
          icon={<SearchRegular />}
          title={chrome.i18n.getMessage("noMatchingTasksTitle")}
          description={chrome.i18n.getMessage("noMatchingTasksDescription")}
        />
      ) : (
        <section className={styles.list}>
          {visibleTasks.map((task) => (
            <TaskCard
              key={task.taskId}
              task={task}
              busy={isTaskBusy(task.taskId)}
              onAction={(action) => onTaskAction(task.taskId, action)}
            />
          ))}
        </section>
      )}
    </div>
  );
}

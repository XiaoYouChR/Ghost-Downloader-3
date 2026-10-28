import type {TaskSort, TaskSortField, TaskSummary} from "../shared/types";

export interface TaskQuery {
  text: string;
  sort: TaskSort;
}

const STATUS_ORDER = ["running", "waiting", "paused", "failed", "completed"];

function statusRank(task: TaskSummary): number {
  if (task.status === "completed" && !task.canOpenFile) {
    return STATUS_ORDER.length;
  }
  return STATUS_ORDER.indexOf(task.status);
}

function byNewest(left: TaskSummary, right: TaskSummary): number {
  return right.createdAt - left.createdAt;
}

const ASCENDING: Record<TaskSortField, (left: TaskSummary, right: TaskSummary) => number> = {
  time: (left, right) => left.createdAt - right.createdAt,
  status: (left, right) => statusRank(left) - statusRank(right),
  name: (left, right) => left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: "base" }),
  size: (left, right) => left.fileSize - right.fileSize,
};

function hasUnknownSize(task: TaskSummary): number {
  return task.fileSize > 0 ? 0 : 1;
}

/** Unknown sizes stay last and ties fall back to newest first, whichever the direction. */
export function buildTaskView(tasks: TaskSummary[], { text, sort }: TaskQuery): TaskSummary[] {
  const words = text.toLowerCase().split(/\s+/).filter(Boolean);
  const sign = sort.direction === "asc" ? 1 : -1;
  return tasks
    .filter((task) => words.every((word) => task.name.toLowerCase().includes(word)))
    .sort((left, right) =>
      (sort.field === "size" ? hasUnknownSize(left) - hasUnknownSize(right) : 0)
      || sign * ASCENDING[sort.field](left, right)
      || byNewest(left, right));
}

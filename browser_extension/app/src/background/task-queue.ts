const SESSION_KEY = "pendingTasks";

type TaskPayload = Record<string, unknown>;

async function readQueue(): Promise<TaskPayload[]> {
  const data = await chrome.storage.session.get(SESSION_KEY);
  const items = data[SESSION_KEY];
  return Array.isArray(items) ? items as TaskPayload[] : [];
}

async function writeQueue(items: TaskPayload[]): Promise<void> {
  await chrome.storage.session.set({ [SESSION_KEY]: items });
}

export async function enqueue(payload: TaskPayload): Promise<number> {
  const queue = await readQueue();
  queue.push(payload);
  await writeQueue(queue);
  return queue.length;
}

export async function flush<T>(
  sendFn: (payload: TaskPayload) => Promise<T>,
): Promise<T[]> {
  const queue = await readQueue();
  if (queue.length === 0) {
    return [];
  }

  const failed: TaskPayload[] = [];
  const results: T[] = [];
  for (const payload of queue) {
    try {
      results.push(await sendFn(payload));
    } catch {
      failed.push(payload);
    }
  }

  await writeQueue(failed);
  return results;
}

export async function pendingCount(): Promise<number> {
  const queue = await readQueue();
  return queue.length;
}

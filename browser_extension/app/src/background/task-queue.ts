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

export async function flush(
  sendFn: (payload: TaskPayload) => Promise<unknown>,
): Promise<number> {
  const queue = await readQueue();
  if (queue.length === 0) {
    return 0;
  }

  const failed: TaskPayload[] = [];
  let sent = 0;
  for (const payload of queue) {
    try {
      await sendFn(payload);
      sent += 1;
    } catch {
      failed.push(payload);
    }
  }

  await writeQueue(failed);
  return sent;
}

export async function pendingCount(): Promise<number> {
  const queue = await readQueue();
  return queue.length;
}

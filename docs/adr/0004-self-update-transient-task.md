# Self-update reuses the task pipeline as a transient task

The auto-update download reuses the existing HTTP download engine
(`HttpTask` / `HttpTaskStep` via `TaskService`) instead of a standalone
downloader. To keep it out of the user's task list and out of persistence, an
`UpdateTask(HttpTask)` subclass carries a class-level `transient = True` flag.
`TaskService.add`, the store's `flush`, `resumeSaved`, and the task page's
`_onTaskAdded` all skip transient tasks: not written to `tasks.jsonl`, not
resumed on next launch, not rendered as a card, and started immediately outside
the `maxTaskNum` concurrency limit. The `UpdateTask` is constructed directly
rather than via `featureService.parse`, because a pack decides which class
`parse` returns and cannot yield a custom subclass.

The full "download → ask → run installer → quit" flow is **Windows + `.exe`
only**. Any other asset (`.msi`, `.zip`, macOS, Linux, or `bestAsset` returning
None) falls back to the pre-existing behavior: an ordinary persisted Task in the
normal download folder, visible in the list. So only the exe path uses the
Update Folder and the StateToolTip; the fallback path is unchanged.

Progress shows in a `StateToolTip`; on success a persistent InfoBar offers
"install now", which launches the installer via `QProcess.startDetached` and
then quits the app. The Update Folder is wiped on both start and stop, so an
interrupted download never leaves a broken file lingering, and no downloaded
installer survives across runs.

## Considered Options

- **Standalone lightweight downloader** (bypass `TaskService`, stream bytes
  directly): rejected — the user wanted to reuse the battle-tested download
  engine (chunking, rate limit, progress snapshots) rather than reimplement it.

- **Instance-level hidden flag + a side set of update task IDs in TaskService**:
  rejected — an instance field would either hit serialization or need a
  parallel bookkeeping set. A `ClassVar` subclass keeps the flag out of
  `tasks.jsonl` entirely (only `f.repr=True` dataclass fields are serialized),
  which guarantees old `tasks.jsonl` files still load: `filterFields` drops
  unknown keys and fills missing ones with defaults. Backward compatibility was
  a hard requirement.

- **Keep a completed installer across runs so the user can install later**:
  rejected — it contradicts the unconditional start/stop cleanup and adds
  conditional-deletion complexity. Not installing is treated as abandoning.

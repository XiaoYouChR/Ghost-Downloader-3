# Deferred file deletion after cancel

File deletion is deferred until the Task Run has fully stopped — its `finally` 
block has closed all file handles and completed cleanup. This eliminates a race 
condition where `deleteFiles()` was called while the download thread still held 
the file open, causing `PermissionError: [WinError 32]` on Windows.

`CoroutineRunner.cancel()` now accepts an optional `stopped` callback that fires 
once the run's `finally` has executed. If the task already finished, the callback 
fires immediately. Task Service uses this to defer file deletion in 
`delete`/`redownload`/`edit` until the run releases all resources.

`deleteFiles()` now returns `bool` — `True` if all targets were deleted, `False` 
if any file was locked by another process. The bool aggregates across all steps 
and paths. `deletePath()` catches `OSError`, logs the failure, and returns `False` 
instead of raising. On `False`, Task Service emits `fileDeleteFailed(task)`, and 
TaskPage shows an InfoBar with the task name.

## The Bug

Before this change:

```python
def delete(self, task, shouldDeleteFiles):
    self._cancelRun(task)          # schedules cancel on download thread, returns immediately
    ...
    if shouldDeleteFiles:
        task.deleteFiles()         # runs NOW, while fd still open
```

`_cancelRun` → `coroutineRunner.cancel(workId)` only *requested* cancellation on 
the download thread's event loop. The GUI thread continued immediately and called 
`deleteFiles()` while the download's `finally` block (closing `self._fd` and 
`.ghd` handle) had not yet run. On Windows, `os.open` does not grant 
`FILE_SHARE_DELETE`, so `path.unlink()` raised `PermissionError`.

The same race existed in `redownload` and `edit` — both called `deleteFiles()` 
immediately after `_cancelRun()`.

## Decision

Three-layer fix:

1. **Time-order layer (core):** `CoroutineRunner.cancel(workId, stopped=None)` 
   registers a `stopped` callback. `execute()` fires it after the run's `finally` 
   completes, on all exit paths (success, error, cancel). If the task already 
   finished, `stopped` fires immediately via `post()`.

2. **Tolerance layer (platform):** `deletePath()` catches `OSError` on both file 
   and directory branches, logs a warning, and returns `False` instead of raising. 
   This prevents crashes from external locks (antivirus, indexers) that we cannot 
   control.

3. **Reporting layer (view):** `deleteFiles()` returns `bool` aggregated across 
   all steps and paths. Task Service emits `fileDeleteFailed(task)` on `False`. 
   TaskPage connects the signal and shows an InfoBar with the task name.

`delete`/`redownload`/`edit` each defer file-touching work into the `stopped` 
callback. `delete` defers only `deleteFiles()` (the rest runs immediately so the 
UI removes the card). `redownload` and `edit` defer the whole delete+restart 
chain — otherwise the new run would start before the old run released the file, 
re-creating the same race.

## Considered Options

- **Open with `FILE_SHARE_DELETE`**: Band-aid. The run is still writing after 
  deletion, can recreate the file or leave fresh partial data. Fixes the symptom, 
  not the ordering bug.

- **Block GUI thread until stopped**: Unacceptable for a GUI app. If a subworker 
  is stuck in network I/O, cancellation waits for the next `await` point. 
  Blocking the main thread freezes the UI.

- **Return `list[Path]` of failed paths**: More info, but costs 11 signature 
  changes and no current UI needs the path list. `bool` is sufficient — the user 
  sees "some files locked," logs show which ones.

- **Emit signal on every partial failure**: Too noisy. One InfoBar per task is 
  enough. `deletePath` logs each failed path for diagnosis.

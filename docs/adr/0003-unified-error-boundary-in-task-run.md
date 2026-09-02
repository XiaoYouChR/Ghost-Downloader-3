# Unified error boundary in Task.run()

All step error handling is unified through a single catch point in `Task.run()`.
Steps raise `TaskError` for known business errors or let unexpected exceptions
propagate. `Task.run()` catches both and stores a `StepError` on the step.
No protocol overrides `Task.run()` — BT and ED2k moved their logic into
`BTTaskStep.run()` / `ED2kTaskStep.run()` so the boundary is universal.

Error messages are English templates carrying format parameters. The View
translates at render time via `QCoreApplication.translate("TaskErrors", msg)`,
keeping Qt out of the logic layer. Pack-specific `error_catalog.py` files
provide `QT_TRANSLATE_NOOP` markers for `lupdate`; they are never imported.

Step errors are not serialized (`repr=False`). Failed tasks loaded from a
previous session show FAILED status without error detail — the user can retry
for a fresh error message.

## Considered Options

- **Step-level catch (status quo before this change)**: every step had
  `except Exception as e: self.setError(e); raise` — 10+ identical blocks,
  error messages were `repr(exception)`, no i18n, no structured parameters.

- **Task-level auto-retry on transient errors**: rejected because every
  protocol that benefits from retry already has it at the subworker or session
  level. Task-level failures are almost always permanent or require user
  intervention. A `retryable` flag can be added non-breakingly later if needed.

- **Translate at raise time (`QCoreApplication.translate` in step)**: rejected
  because it puts Qt in the logic layer. The View layer owns translation.

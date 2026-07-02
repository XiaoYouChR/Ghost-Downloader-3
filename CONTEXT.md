# Ghost Downloader Context

Ghost Downloader is a task-based downloader built with PySide6. It runs on
desktop (Windows, macOS, Linux) and Android from a shared business engine, with
a browser extension that captures resources and sends them to the desktop app.

## Language

### Domain nouns

**Task**:
A user-visible download item stored by the app.

**Task Run**:
The current execution of a Task inside the download loop.

**Task Queue**:
The internal waiting/running set that limits concurrent Task Runs.

**Task Service**:
The app actor that owns user-visible Task workflow: add, pause, delete,
redownload, edit, resumeSaved, stop. The single public door for all task
actions. Internally holds Task Store and Task Queue — neither is public.

**Task Store**:
The internal part of Task Service that holds live Task objects and persists
Task Records to `tasks.jsonl`. Not a public actor.

**Task Record**:
The durable stored form of a Task, one JSON line in `tasks.jsonl`.

**Saved Tasks**:
Task Records loaded from a previous app run that may need to start again.

**Coroutine Runner**:
The app actor that owns the background asyncio loop and Qt callback delivery.
Knows nothing about Task.

**Speed Meter**:
Aggregate download speed monitor. Download engines feed bytes via
`addSpeed(byteCount)`; HTTP/FTP also `await waitForSpeedLimit()` to honor
the global limit. Emits `speedChanged(bytesPerSecond)` once per second only
while bytes are flowing — its timer starts on the first `addSpeed` and stops
itself on the first idle tick.
_Avoid_: globalSpeed mutable, View-owned timer

**Task Step**:
One executable step inside a Task. A Task may have one or many steps. Step
owns `run()` directly — there is no separate Worker class.

**Subworker**:
A split transfer unit for one byte-range chunk inside an HTTP or FTP step.

**Task Files**:
The files and temporary progress state produced by a Task.

**Task Error**:
A business exception raised by Step.run() with a user-facing English message
template and format parameters. `TaskError("Server returned error ({status})",
status=403)`. Task.run() is the single catch point.

**Step Error**:
A frozen value object stored on `step.error` (runtime only, not serialized).
Carries `message` (English template, also the i18n key) and `params` (format
values). `str(stepError)` returns the formatted English fallback.

**Name**:
The basename of a Task's finished file, for example `video.mp4`.
_Avoid_: title, filename (keep `filename` only at the raw browser/protocol seam)

**Output Folder**:
The folder a Task downloads into.

**Output Path**:
The full path of a Task's finished file; equals `outputFolder / name`.

**Task Options**:
The app-owned options used to parse, create, or edit a Task. Frozen dataclass
with subtypes: ResourceTaskOptions, PageTaskOptions, MergeTaskOptions,
BinaryInstallOptions.
_Avoid_: payload (keep only at raw transport seams)

**Task Parser**:
A FeaturePack-provided capability that turns Task Options into a Task.
Declares a `priority` and a `match(options)` predicate.

**Task Draft**:
Unconfirmed task state before the user confirms it. Owns in-flight parses and
late completion. Task Service does not understand draft state.

**Draft Item**:
One URL entry inside a Task Draft, tracking its parse state and result.

**Feature Service**:
The app actor that owns pack discovery, parser priority routing, and pack
lifecycle. `parse(options)` iterates all parsers sorted by priority and calls
the first match.

**FeaturePack**:
A plugin bundle under `features/*_pack`; it may provide task parsers, cards,
file types, binary runtimes, pages, or settings. Declares capabilities; the
app integrates them.

**Pack Page**:
A navigation page contributed by a FeaturePack.

**Binary Runtime**:
An external executable family that a pack can probe or provide an install task
for. Concrete implementations: M3U8Runtime, FFmpegRuntime, YtDlpRuntime.

**Resource**:
A downloadable thing captured by the browser extension.

**App Entry**:
The top-level script that composes process startup for one platform.

**App Stop Flow**:
The function connected to Qt quit that stops app-owned actors in order.

**Settings**:
App-wide user configuration: the Settings page and `cfg`.
_Avoid_: options (options are per-Task input, not app config)

**Category**:
Download classification and target folder rule. CategoryService matches
file extensions to categories and resolves download folders.

**Client**:
A wreq HTTP client with optional TLS fingerprint emulation. `buildClient()`
is the factory; `toEmulation()` resolves a profile string to a wreq Emulation.

**Signal Bus**:
Process-level event bus with exactly four signals: `activationRequested`,
`openFileRequested`, `exceptionCaught`, `updateAvailable`. No task or
business signals — those live on Task Service and Speed Meter.

**Plan**:
A "do X after all tasks complete" intent: shutdown, restart, or open file.

### Verb vocabulary

These verbs have specific meanings in this project.

**load**: read app-local persisted data or local resources.
_Not_: fetch (network), read (raw I/O)

**save**: persist durable app state or progress/cache data.

**fetch**: one network request to retrieve data.
_Not_: load (local), probe (metadata only)

**probe**: ask for capability or metadata without creating a task.

**parse**: convert seam text, payload, or protocol output to app objects.

**match**: decide whether a candidate fits a rule.

**find**: search local disk or a real search space.

**build**: pure construction from known data, no side effects.
_Not_: create (has side effects)

**create**: create a real resource with side effects (spawn, allocate, connect).

**to\***: convert representation. `toSafeFilename`, `toPosixPath`.

**set**: assign local object or widget state directly.

**update**: recompute state from caller-provided inputs.
_Not_: refresh (self-initiated)

**refresh**: self-initiated re-query; no caller input needed.
_Not_: update (caller-provided)

**add**: add a business object. `taskService.add(task)`.

**start / pause / stop**: start execution, user-visible pause, stop current
execution only.

**resume**: startup recovery. `taskService.resumeSaved()`.

**remove**: detach from memory, model, config, or UI. No disk deletion.
_Not_: delete (destructive)

**delete**: destructive deletion from disk or durable records.
_Not_: remove (non-destructive), cleanup (vague)

**clear**: empty a collection, input, selection, or cache.

**flush**: write buffered store state to disk. `flushSoon`, `flushNow`.

**cancel**: abandon async work without deleting records.

**open / close**: open or close file, folder, URL, socket, session, dialog.

**reveal**: reveal or select a file or folder in the OS file manager.

**on\***: Qt slot, signal reaction, event reaction.

**run**: execute a workflow step owned by the current actor.

**supervise**: worker-internal supervisor that samples progress, saves resume
data, and coordinates subworkers.

**install**: place a runtime or binary on disk.

**send**: push data or notification to another system. One-way, no response
expected. `sendNotification`, `sendResult`.

**request**: ask another actor or system to perform an action.
`requestPairing`, `requestIgnoreBatteryOptimizations`.

### File-system words

**folder**: the value is definitely a folder. `outputFolder`, `installFolder`.
**file**: the value is definitely a file. `outputFile`, `decryptionKeyFile`.
**path**: the value may be a file or folder. `outputPath`, `binaryPath`.
_Avoid_: `directory` in project-owned names (only when mirroring an external API).

### Boolean names

Booleans use `is*`, `has*`, `can*`, or `should*`.
_Avoid_: bare adjectives (`available`), action-looking booleans (`enableX`),
third-person verbs (`supportsX`).

### Signal names

Signal names follow `{noun}{PastParticiple}`: `taskAdded`, `speedChanged`,
`pairRequested`, `parseSucceeded`. A signal is a fact that already happened,
not a command to do something. Slots mirror the signal:
`_on{Noun}{PastParticiple}` — `_onTaskAdded`, `_onSpeedChanged`.

### Noun-returning lookups

For simple key or list lookup, use noun form: `taskById(taskId)`,
`resourceByUrl(url)`, `categoryById(categoryId)`.
_Avoid_: `find*` for in-memory lookup (keep `find*` for disk/PATH search).

## Relationships

- A **Task Draft** contains one or more **Draft Items** before the user
  confirms them. Each Draft Item tracks a URL, its parse state, and
  optionally a parsed Task.
- **Task Options** are parsed by a **Task Parser** into a **Task**.
  `featureService.parse(options)` iterates parsers by priority; the first
  `match(options)` wins.
- A **FeaturePack** is the plugin bundle that may provide one or more
  **Task Parsers**, cards, file types, runtimes, or pages.
- A **Task** has one durable **Task Record** in `tasks.jsonl`.
- **Task Service** internally holds **Task Store** and **Task Queue**; neither
  is public. Task Service resumes **Saved Tasks**; a View does not.
- A **Coroutine Runner** runs generic async work and delivers callbacks back to
  Qt.
- A **Task** may have zero or one active **Task Run**.
- A **Task Run** iterates **Task Steps** sequentially via `pendingSteps()`.
  Each Step owns its own `run()`.
- A browser **Resource** can become **Resource Task Options** via
  `toResourceTaskOptions()` in the extension. A page-media handoff becomes
  **Page Task Options** or **Merge Task Options**.
- **Category Service** matches file extensions to categories and resolves
  download folders. Task Service auto-categorizes on add.

### Parser routing

`featureService.parse(options)` iterates parsers by priority (higher checked
first) and calls the first match:

| Parser | Priority | Match condition |
|---|---|---|
| HttpParser | 100 | any `http`/`https` URL (fallback) |
| FtpParser | 95 | `ftp`/`ftps` scheme |
| GitHubParser | 90 | GitHub file URL + proxy configured |
| HuggingFaceParser | 85 | HuggingFace domain |
| TorrentParser | 85 | `magnet:` scheme or `.torrent` |
| M3U8Parser | 80 | `.m3u8`/`.mpd` in URL or local manifest |
| YouTubeParser | 70 | YouTube domain |
| MergeParser | 60 | `isinstance(options, MergeTaskOptions)` |
| InstallParser | 55 | `isinstance(options, BinaryInstallOptions)` |
| BilibiliParser | 50 | Bilibili domain |
| ED2kParser | 45 | `ed2k://` scheme |

Delegation patterns:
- **GitHubParser** rewrites URL through proxy, then calls
  `featureService.parse(replace(options, url=proxiedUrl))`. No recursion:
  proxied URL is not a GitHub host.
- **MergeParser** calls `featureService.parse(options.video)` and
  `featureService.parse(options.audio)` to parse sub-resources. Both route
  through the priority chain.
- **InstallParser** delegates the download through
  `featureService.parse(TaskOptions(url=...))` so GitHubParser mirrors it.

## Ownership rules

**`task.status` has a single writer.** Task Service writes it for queue
transitions (WAITING/RUNNING/PAUSED); the Step writes it for terminal outcomes
(COMPLETED/FAILED). Views only read it to render.

**Task Service** is the single public door. It internally holds Task Store
and Task Queue. No caller reaches either directly.

| State | Internal owner |
|---|---|
| Live Task objects | Task Store (inside Task Service) |
| Durable Task Records (`tasks.jsonl`) | Task Store (inside Task Service) |
| Category default folder, duplicate-name policy | Task Store (in `add`) |
| Waiting order | Task Queue (inside Task Service) |
| Running runs + cancel handles | Task Queue (inside Task Service) |
| Slot limit | Task Queue (inside Task Service) |
| File disappearance watch | Task Service (QFileSystemWatcher) |

**Task lifecycle signals are emitted by Task Service:**
`taskAdded(Task)`, `taskRemoved(taskId)`, `taskStarted(Task)`,
`taskPaused(Task)`, `taskCompleted(Task)`, `taskFailed(Task)`,
`tasksAllCompleted()`.

**Speed Meter** owns aggregate download speed — separate from task
orchestration. Download engines feed it bytes; it emits `speedChanged` per
second only while bytes are flowing.

**Views collect user intent and render state.** They call Task Service
directly (`taskService.pause(task)`, `taskService.delete(task, ...)`). They
do not own task lifecycle decisions, persist records, or manage the download
loop. Services hold no View references; Views connect to service signals.

**Browser Service** is a protocol adapter: receive WebSocket messages, translate
to Task Service verbs, send results back. It holds no MainWindow reference.
View connection is purely via signals wired in the entry script.

**Dependency direction** (leaf → top):

```
coroutineRunner    knows nothing about Task
speedMeter         knows nothing about Task; fed bytes by download engines
taskService        uses coroutineRunner; internally holds TaskStore + TaskQueue
featureService     holds packs + parsers; parse() returns Task
taskDraft          uses coroutineRunner + featureService
browserService     uses taskService + featureService; emits signals for View
categoryService    standalone; taskService calls matchByName on add
View / Entry       wires everything; connects signals
```

## Module topology

### Service layer

All business services are platform-agnostic module singletons:

| Service | Owns | Signals |
|---|---|---|
| `coroutineRunner` | asyncio event loop on QThread, callback delivery | — |
| `speedMeter` | byte accumulator, 1s timer, speed limit gate | `speedChanged(int)` |
| `taskService` | TaskStore + TaskQueue, file watcher, flush timer | `taskAdded`, `taskRemoved`, `taskStarted`, `taskPaused`, `taskCompleted`, `taskFailed`, `tasksAllCompleted`, `fileDisappeared`, `diskSpaceInsufficient` |
| `featureService` | pack list, sorted parser list, packByPackId map | — |
| `browserService` | WebSocket server, client sessions, snapshot timer | `pairRequested`, `taskDraftRequested`, `extensionUpdated`, `connectionChanged` |
| `categoryService` | category rules (persisted in cfg) | `categoriesChanged` |
| `clipboardListener` | clipboard monitoring, URL filtering | `urlsDetected(list)` |
| `runtimeStatusService` | async version probing for BinaryRuntime | `statusChanged(RuntimeStatus)` |
| `plan` | post-completion intent (shutdown/restart/open) | — |

### FeaturePack system

Each pack under `features/*_pack/` declares capabilities via methods on its
`FeaturePack` subclass. `featureService.load()` discovers packs from
`manifest.toml` files, topologically sorts by dependencies, then imports them.

Pack capabilities: `parsers()`, `taskCard()`, `draftCard()`, `optionCards()`,
`editCards()`, `fileTypes()`, `pages()`, `settingGroups()`, `start()`, `stop()`.

Module singletons created at import time (configs, runtimes, services, actors)
must not read `cfg` values at construction — use lazy properties. `qconfig.load`
happens before `featureService.load`.

Notable pack-level actors:
- `bilibiliAccount` — module singleton for Bilibili login/cookie state;
  the sole gateway to the current cookie.
- `btSession` — module singleton wrapping the libtorrent session; lazy open
  on first BTTask.run(); emits `alertReceived` for broadcast+filter routing.
- `trackerService` — tracker source fetch + cache + merge.
- `ffmpegRuntime`, `m3u8Runtime`, `ytDlpRuntime` — BinaryRuntime singletons.

### View layer

**MainWindow** owns a `TaskDraft` service instance and a lazy
`TaskDraftDialog`. It does not own task lifecycle — it wires
`draft.taskConfirmed → taskService.add`, which is the only task-creation path.

**TaskPage** subscribes to `taskService.*` signals for card lifecycle. Virtual
scroll: `_cards` dict, `_displayOrder` list, `_mounted` set. Three-layer
refresh: `_rebuildList` (filter+sort) → `_refreshViewport` (mount/unmount
visible range) → `_refreshVisibleCards` (1s timer repaint for progress text).

**TaskDraftDialog** receives a `TaskDraft` in its constructor. It debounces URL
changes, delegates parsing to `TaskDraft`, and renders draft cards from
`featureService.draftCard()`.

**SettingPage** adds pack settings via `featureService.settingGroups(parent)`.

### Browser Extension

Service worker with four bridge singletons:

**desktopBridge**: WebSocket connection to desktop BrowserService. Protocol v3:
`hello` → `hello_ack` → `subscribe_tasks` → `task_snapshot` push. Request/
response via `requestId` correlation. Reconnects on close (2.5s timer + 1-min
alarm fallback). Offline tasks queue in `taskQueue` (storage.session) and flush
on reconnect.

**resourceBridge**: captures from three sources: `webRequest.onResponseStarted`
(network), `webRequest.onSendHeaders` (header snapshots), `runtime.onMessage`
cat-catch `addMedia` (page). Owns `ResourceCache` (pure in-memory, no chrome
deps, unit-testable). Uses `download-spec.ts` for `toResourceTaskOptions()`.

**mediaBridge**: media playback control. `buildPanelState()` polls cat-catch
content script for video state. `runAction()` sends commands. Owns
`mediaSnapshot` as single source of truth.

**featureBridge**: per-tab feature toggles (recorder, webrtc, mobileUserAgent,
etc.). Persists to `storage.local`; reconciles against live tabs on load.

**Page Media** (content script side, four lifecycle layers):
- L1 — MSE Probe (MAIN world, `document_start`): intercepts
  `SourceBuffer.appendBuffer` to correlate fetch URLs → MSE buffer appends.
- L2 — Attribution Engine (ISOLATED world, `document_start`): attributes
  network URLs to playing `<video>` elements via timing correlation.
- L3 — Download Button (ISOLATED world, `document_idle`): standalone IIFE,
  finds active media, on click asks L2 to resolve → sends to background →
  resourceBridge dispatches to desktop.
- L4 — Resolution Strategies (no lifecycle, pure functions): per-site dispatch
  (YouTube, X, Douyin, generic). Strategies cannot reach back into the
  attribution engine.

**Popup Protocol**: typed union `PopupCommand = StateCommand | ActionCommand`.
Exhaustive switch in `runPopupCommand()` — compile-time complete.

## App lifecycle

### Desktop startup (`Ghost-Downloader-3.py`)

```
setupEnvironment():
  setupHiddenSubprocess (win32)
  import resources
  patchFluentLabelThemeChanged
  qconfig.load(configPath, cfg)

startApp(application, isSilent):
  sys.excepthook → signalBus.exceptionCaught
  load translator
  coroutineRunner.start()
  MainWindow()
  featureService.load() → discover + import packs
  PackConfig.load() → register pack ConfigItems
  window.setupPacks() → add pack pages/settings
  taskService.taskStarted → speedMeter.start
  tasksAllCompleted → speedMeter.stop
  taskService.resumeSaved()
  featureService.start() → pack.start() on each
  wire signalBus, browserService, clipboardListener, tray/dock
  taskService.taskCompleted → notifyTaskCompleted
  tasksAllCompleted → plan.trigger
  application.aboutToQuit.connect(stopApp)
```

### Desktop shutdown

```
stopApp():
  taskService.stop()       # pause all running/waiting
  taskService.flush()      # write store to disk
  browserService.stop()    # close WebSocket server
  aria2RpcServer.stop()
  featureService.stop()    # pack.stop() on each
  coroutineRunner.stop()   # cancel all, stop asyncio loop
```

### Android differences

Same engine, different cockpit. `MobileMainWindow` is an independent QWidget
(not a subclass of desktop MainWindow). `MobileTaskPage` subclasses desktop
`TaskPage` for filter/sort/virtual-scroll reuse — overrides only interaction
(touch, layout). Cards use an MRO mixin swap for overflow menu and long-press.

Mobile-specific: `KeepAlive` (foreground service + wake lock), Android
notifications, auto-approve browser pairing (no dialog), silent task add
(no draft dialog), share intent handling.

`patches.py` is a contained workaround layer for PySide6-on-Android quirks:
EGL single-surface (popups must be child widgets), broken QSvgPlugin,
content:// URIs, narrow-screen reflow.

Shutdown is identical to desktop.

## Code shape

Functions and methods use `camelCase`. Classes use `PascalCase`. Constants use
`UPPER_SNAKE_CASE`. Object-private attributes and class-internal helpers start
with `_`. Module-level classes and constants do not add `_`.

QWidget and QDialog subclasses follow a four-phase `__init__`:
`_initWidget()` → `_initLayout()` → `_bind()`. Signals are connected in
`_bind`, after all widgets exist — so `_initWidget` can set initial state
without triggering slots.

Services are signal-driven actors with private state. They do not hold View
references. Views connect to service signals and call service methods directly.

## Task execution

### Step iteration, error boundary, and cancellation

`Task.run()` iterates `pendingSteps()` sequentially — sorts steps by index,
skips COMPLETED, yields remaining while `self.status == RUNNING`. No protocol
overrides `Task.run()` — it is the universal error boundary:

- `TaskError` → `step.setError(StepError(str(e), e.params))` — user-facing
- `Exception` → `step.setError(StepError(repr(e)))` — unexpected, debuggable
- `CancelledError` → passes through (BaseException in Python 3.11+), no error set

Steps raise `TaskError` for known business errors. Steps that use `TaskGroup`
catch `ExceptionGroup` internally and convert protocol exceptions to `TaskError`
before they reach `Task.run()`. Steps never call `setError` directly.

Error messages are English templates (also serving as i18n keys). The View
translates at render time via `QCoreApplication.translate("TaskErrors", msg)`.
Pack-specific `error_catalog.py` files hold `QT_TRANSLATE_NOOP` markers for
`lupdate` extraction; they are never imported at runtime.

**Cancellation**: `taskService.pause(task)` → `coroutineRunner.cancel(workId)` →
`asyncio.Task.cancel()` → `CancelledError` into running step. Each protocol
handles cleanup: HTTP/FTP preserve `.ghd` progress for resume; M3U8/yt-dlp
terminate subprocess; BT saves resume data and removes torrent from session.

### Split transfer (HTTP/FTP)

HTTP and FTP use the same subworker pattern: divide file into byte ranges,
launch concurrent subworkers (each sends range requests and `pwrite`s at
position), run a 1s `_supervise()` loop that saves `.ghd` progress and
calculates speed. `_autoSpeedUp()` adds subworkers after stable-speed sampling.
`_reassignSubworker()` splits the slowest remaining range when a subworker
finishes. On resume, `_loadRecord()` restores subworker positions from `.ghd`.

FTP differs: each subworker opens its own FTP connection; uses manual
`asyncio.wait(FIRST_EXCEPTION)` instead of TaskGroup for dynamic subworker
addition.

### CLI subprocess steps

M3U8, yt-dlp, and FFmpeg launch external processes and parse stdout for
progress. M3U8 uses N_m3u8DL-RE with regex progress parsing (VOD segments,
live elapsed). yt-dlp uses `--progress-template` for machine-readable output
and `--print after_move:__GD3_FINAL__%(filepath)s` for final file detection.
FFmpeg merge is a 3-step task: download video + download audio + stream-copy
merge with `out_time_us` progress parsing.

### Serialization

`Task.toDict()` walks dataclass fields where `f.repr == True`; fields with
`repr=False` (like subworkers, runtime state) are excluded. `Task.fromDict()`
uses `Task._registry` (populated by `__init_subclass__`) to reconstruct the
correct Task/Step subclass. Unknown fields are silently dropped for forward
compatibility.

Runtime state lives as plain instance attributes (not dataclass fields),
initialized in `run()`, never serialized.

## Example dialogue

> **Dev:** "When the user presses pause, are we deleting the Task?"
> **Domain expert:** "No. Pause stops the Task Run. The Task Record and Task
> Files stay."

> **Dev:** "When the user presses redownload, do we create a new Task?"
> **Domain expert:** "No. Redownload stops the Task Run, deletes Task Files,
> resets the same Task, and starts a new Task Run."

## Flagged ambiguities

- `payload` was used for raw protocol data, dialog options, and FeaturePack
  input. Resolved: keep `payload` at raw seams; use **Task Options** inside
  the app.
- `title` was used as the final product name of a Task. Resolved: a Task owns
  a **name**, not a UI title.
- `createTask` was used for starting or enqueuing a Task Run. Resolved:
  creation of a durable Task and starting a Task Run are separate concepts.
- `removeTask` was used for both View removal and durable deletion. Resolved:
  removing a Task Record and deleting Task Files are separate steps.
- `resumeMemorizedTasks` lived on TaskPage. Resolved: startup recovery is Task
  Service work; the View only refreshes through signals.
- `aboutToQuit` connected several services directly. Resolved: each App Entry
  connects one App Stop Flow so shutdown order is explicit.
- `resolve*` was widely used for functions that fetched, parsed, searched, and
  built in unclear combination. Resolved: use the specific verb that names the
  actual operation (load, fetch, probe, parse, build, select, or a
  noun-returning method).

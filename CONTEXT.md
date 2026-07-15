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

**Pausable**:
A Task is pausable while its running Step can resume from a breakpoint (for
transfers, whether the server honours byte-range requests). Pausability is
derived from resumability at the moment it is read — never stored as separate
state, because a Step may only learn its resumability after it was created.

**Task Files**:
The files and temporary progress state produced by a Task.
_Avoid_: confusing with **Selectable File** (the checkable unit below)

**Selectable File**:
One checkable download unit inside a multi-file Task — a repository file, a
playlist video, a multi-part page, or a torrent file. Identified by a stable
index that never changes with selection.

**File Selection**:
Which Selectable Files a Task should download, expressed as flags on the
files. Changing selection never creates or destroys Steps and is allowed in
every Task status; deselected files keep their partial progress.

**Revive**:
A completed Task returning to downloading because newly selected files have
pending work. Reviving clears the completion timestamp and starts the Task
automatically.

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
for. Concrete implementations: M3U8Runtime, FFmpegRuntime, YouTubeRuntime.

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
A "do X after all tasks complete" intent: shutdown, restart, sleep, or open file.

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

**mount / unmount**: create or retire a lazily-managed widget as it enters or
leaves the viewport. Unmounting may defer actual destruction until safe.
_Not_: remove (model detach), delete (destructive)

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

Booleans are named with `is*`, `has*`, `can*`, or `should*` prefixes.
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

`featureService.parse(options)` iterates parsers in ascending priority order;
the first `match(options)` wins. Specific parsers have low priority numbers
and are checked first; HttpParser (100) is the fallback, checked last.

| Parser | Priority | Match condition |
|---|---|---|
| ED2kParser | 45 | `ed2k://` scheme |
| BilibiliParser | 50 | Bilibili domain |
| InstallParser | 55 | `isinstance(options, BinaryInstallOptions)` |
| MergeParser | 60 | `isinstance(options, MergeTaskOptions)` |
| YouTubeParser | 70 | YouTube domain |
| M3U8Parser | 80 | `.m3u8`/`.mpd` in URL or local manifest |
| TorrentParser | 85 | `magnet:` scheme or `.torrent` local file |
| HuggingFaceParser | 85 | HuggingFace domain |
| GitHubParser | 90 | GitHub file URL + proxy configured |
| FtpParser | 95 | `ftp`/`ftps` scheme |
| HttpParser | 100 | any `http`/`https` URL (fallback) |

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
View connection is purely via signals bound in the entry script.

**Dependency direction** (leaf → top):

```
coroutineRunner    knows nothing about Task
speedMeter         knows nothing about Task; fed bytes by download engines
taskService        uses coroutineRunner; internally holds TaskStore + TaskQueue
featureService     holds packs + parsers; parse() returns Task
taskDraft          uses coroutineRunner + featureService
browserService     uses taskService + featureService; emits signals for View
categoryService    standalone; taskService calls matchByName on add
View / Entry       binds everything; connects signals
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
do not read `cfg` values at construction — they use lazy properties. `qconfig.load`
happens before `featureService.load`.

Notable pack-level actors:
- `bilibiliAccount` — module singleton for Bilibili login/cookie state;
  the sole gateway to the current cookie.
- `btSession` — module singleton wrapping the libtorrent session; lazy open
  on first BTTask.run(); emits `alertReceived` for broadcast+filter routing.
- `trackerService` — tracker source fetch + cache + merge.
- `ffmpegRuntime`, `m3u8Runtime`, `youTubeRuntime` — BinaryRuntime singletons.

### View layer

**MainWindow** owns a `TaskDraft` service instance and a lazy
`TaskDraftDialog`. It does not own task lifecycle — it binds
`draft.taskConfirmed → taskService.add`, which is the only task-creation path.

**TaskPage** subscribes to `taskService.*` signals for card lifecycle. Lazy
virtual scroll: `_liveCards` dict (viewport-only cards, created on enter,
destroyed on leave), `_displayOrder` list, `_selectedIds` set (selection state
lifted from cards). Three-layer refresh: `_refreshList` (filter+sort) →
`_refreshViewport` (mount/unmount/position visible cards) →
`_refreshVisibleCards` (periodic repaint for progress text). Band selection
via `BandSelector` event filter on scrollWidget; Delete key shortcut in
selection mode.

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
  loadEngine(application)          → translator + coroutineRunner.start
  MainWindow()
  splash (if not silent)
  loadPacks()                      → featureService.load + PackConfig.load
  window.setupPacks()
  startEngine()                    → speedMeter bind + resumeSaved + featureService.start
  bind signalBus, browserService, clipboardListener, tray/dock
  bindNotifications(completed, diskSpace)
  checkUpdateAtStartup()
  application.aboutToQuit.connect(stopEngine)
```

Shared startup functions live in `app/startup.py`: `loadEngine`, `loadPacks`,
`startEngine`, `bindNotifications`, `checkUpdateAtStartup`, `stopEngine`.

### Desktop shutdown

```
stopEngine():
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

### Naming conventions

Functions and methods use `camelCase`. Classes use `PascalCase`. Constants use
`UPPER_SNAKE_CASE`. Object-private attributes and class-internal helpers start
with `_`. Module-level classes and constants do not add `_`.

Function names combine one verb from the verb vocabulary above with one
concrete business noun: `taskService.add(task)`,
`featureService.parse(options)`, `browserService.stop()`. No verbs outside the
vocabulary appear in app-owned code — if none of the existing verbs fit, the
function's responsibility is unclear and the seam is wrong, not the vocabulary.

### Word choice

Names use short, common English words that a first-time reader understands
without a dictionary: `task`, `step`, `name`, `folder`, `speed`, `draft`.
Rare or academic words are replaced with plain equivalents: `sanitize` →
`toSafeFilename`, `normalize` → `toProxySite`, `orchestrate` → `run`.
When a shorter word means the same thing, the shorter word wins: `add` over
`insert`, `stop` over `terminate`.

Names describe what the actor owns in the domain, not its structural role.
Actors are named `taskService`, `speedMeter`, `categoryService` — generic
structural nouns like `manager`, `controller`, `coordinator`, `provider`,
`repository`, `facade`, `pipeline`, and `context` are absent because each
actor is named for the business concept it owns. A new noun represents a real
domain concept; introducing a noun just to make an awkward helper sound nicer
is a sign the helper belongs on an existing actor.

A forced long name (`removeTaskRecordAndDeleteFiles`) is a sign the function
owns two responsibilities. Better seams make names short:
`taskService.delete(task, shouldDeleteFiles)`.

### Comments

Code carries no comments and no docstrings by default. A well-named function
with typed parameters explains what it does; comments that restate the code
compete for the reader's attention without adding information. Comments earn
their place only when they explain **why** — a hidden constraint, a workaround
for a specific bug, or behavior that would surprise a reader. If removing a
comment would not confuse a future reader, the comment is not written.

### Inlining

This codebase prefers inlined code over shallow extractions. A function earns
extraction when it is called from two or more sites, or when it exceeds ~15
lines with a single clear duty and a return type that is a single named type
(not a tuple or dict). One-line wrappers, single-caller helpers under 5 lines,
and trivial delegations are inlined at their call site. Three similar lines of
obvious code are kept inline rather than extracted into a function whose
interface is as complex as its body — the extraction adds a jump without
reducing knowledge for the caller.

### Deepening

"Deeper module" in this project means less call-site knowledge, not more
architecture nouns. Refactors in this codebase have been subtractive:
workflows moved behind existing actors before new actors were created;
reach-through plumbing deleted; new modules introduced only when the same
business rule was already spreading across multiple callers. New seams were
earned by deleting knowledge from call sites, not by drawing boxes.

### Four-phase `__init__`

QWidget and QDialog subclasses follow a four-phase `__init__`:

```python
def __init__(self, parent=None):
    super().__init__(parent)
    self._initWidget()
    self._initLayout()
    self._bind()
```

Each phase has a single responsibility:

`_initWidget()` — create and configure child widgets. Set initial property
values, default text, icons, size policies. No signal connections — the widgets
are inert at this point, so setting state does not trigger any reactions.

`_initLayout()` — assemble layouts and add widgets. Only layout code: margins,
spacing, stretch factors, addWidget/addLayout calls.

`_bind()` — connect signals to slots. All widgets exist and are laid out, so
it is safe to connect. Slots triggered here can safely reference any sibling
widget.

This separation exists because Qt signals fire immediately on connect if the
current widget state already matches the signal condition. Connecting in
`_initWidget` before sibling widgets exist leads to slot calls that reference
widgets not yet created.

### Responsibility layers

```
View (app/view/)
  Renders state and collects user intent.
  Calls service methods: taskService.pause(task), taskService.delete(task, ...).
  Connects to service signals for refresh: taskService.taskAdded → _onTaskAdded.
  Does not own task lifecycle, persist records, run downloads, or manage the
  event loop.

Service (app/services/)
  Signal-driven actors with private state. The single source of truth for the
  state they own. Emit signals when state changes.
  Do not import from app/view/. Do not hold QWidget references. Do not show
  dialogs or InfoBars.

FeaturePack (features/*_pack/)
  Declare capabilities (parsers, cards, runtimes). Provide pack-specific
  business logic (download step implementation, protocol handling).
  Do not import from app/view/ except for card classes returned by taskCard /
  draftCard / optionCards. Do not reach into Task Service internals.

Platform (app/platform/)
  OS-specific adapters: file association, run at login, hidden subprocess,
  notifications, Android keepalive. Thin wrappers with no business logic.

Entry (Ghost-Downloader-3.py, android/main.py)
  Composition root. Creates services and views, binds signals, defines
  shutdown order. Platform-specific wiring lives here, not in services or views.
```

When a View method grows long because it orchestrates multiple service calls,
the orchestration belongs behind a service method — the View calls one verb,
the service owns the ordering. This is how `taskService.redownload(task)`
replaced multi-step card code that called stop + delete files + reset + start.

## Task execution

### Step iteration, error boundary, and cancellation

`Task.run()` iterates `pendingSteps()` sequentially — sorts steps by index,
skips COMPLETED, yields remaining while `self.status == RUNNING`. No protocol
overrides `Task.run()` — it is the universal error boundary:

- `TaskError` → `step.setError(StepError(str(e), e.params))` — user-facing
- `Exception` → `step.setError(StepError("Unexpected error: {detail}"))` — generic wrapper, detail from `str(e)`
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
- `fileSize == 0` means both "size unknown" (`SpecialFileSize.UNKNOWN`) and a
  legitimately empty file — the model cannot tell them apart. Unresolved;
  existing code works around it (`updateStatus` backfills only when
  `receivedBytes > 0`; the HTTP probe treats sizes 0 and 1 as pseudo-unknown).

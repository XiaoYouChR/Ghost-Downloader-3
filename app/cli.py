from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from collections.abc import Callable
from pathlib import Path

from app.config.cfg import cfg, currentHeaders
from app.config.constants import VERSION
from app.models.task import Task, TaskOptions, TaskStatus, toTaskError
from app.platform.instance import Invocation, Reply
from app.platform.url_scheme import isLaunchUri, isWakeUri
from app.services.task_service import NameConflictChoice

OUTPUT_CONTRACT = """\
stdout is one JSON object: {"result": ...} on success, {"error": {"code", "message"}} on failure.
Exit codes: 0 success, 1 operation failed (see JSON), 2 usage error.

examples:
  # show name, size and files before adding
  ghd probe "https://example.com/a.torrent"
  # download only files 0 and 3; the output has the taskId
  ghd add "https://example.com/a.torrent" --select 0,3 --folder ./downloads
  # block until it finishes; exit 0 only if completed
  ghd wait tsk_0123
"""


HEADER_HELP = "request header, e.g. 'Referer: https://example.com/'; repeatable"
TASK_ID_HELP = "task ID from `ghd add` or `ghd tasks`"


class UsageError(Exception):
    pass


class TextRequested(Exception):
    pass


class CommandParser(ArgumentParser):
    """argparse 的 sys.exit 会结束 Primary Instance，所以改为抛出异常。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, allow_abbrev=False, **kwargs)

    def _print_message(self, message: str, file=None) -> None:
        raise TextRequested(message)

    def error(self, message: str):
        raise UsageError(f"{message}. Run `{self.prog} --help` for details.")


def buildParser() -> CommandParser:
    parser = CommandParser(prog="ghd", description="Control Ghost Downloader from the terminal. "
                                                   "Starts it in the background if it is not running.",
                           epilog=OUTPUT_CONTRACT, formatter_class=RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"ghd {VERSION}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    add = commands.add_parser("add", help="add tasks and start them; prints task IDs")
    add.add_argument("urls", nargs="+", metavar="url", help="URL, magnet/ed2k link, or local file such as a .torrent")
    add.add_argument("-o", "--folder", help="output folder (default: the folder set in Ghost Downloader)")
    add.add_argument("--name", help="file name; only with a single URL")
    add.add_argument("--select", metavar="INDEXES",
                     help="comma-separated file indexes from probe, e.g. 0,3,5; only with a single URL "
                          "(default: the files probe marks isSelected)")
    add.add_argument("-H", "--header", action="append", default=[], metavar="'NAME: VALUE'", help=HEADER_HELP)
    add.add_argument("--conflict", choices=("keep", "overwrite"), default="keep",
                     help="when the name is taken: keep both or overwrite (default: keep)")

    wait = commands.add_parser("wait", help="block until tasks stop downloading; exit 0 only if all completed")
    wait.add_argument("taskIds", nargs="+", metavar="taskId", help=TASK_ID_HELP)

    tasks = commands.add_parser("tasks", help="list tasks")
    tasks.add_argument("-s", "--status", choices=[status.name.lower() for status in TaskStatus],
                       help="only list tasks in this status (default: all)")

    commands.add_parser("task", help="show one task with its files").add_argument("taskId", help=TASK_ID_HELP)

    pause = commands.add_parser("pause", help="pause tasks")
    pause.add_argument("taskIds", nargs="+", metavar="taskId", help=TASK_ID_HELP)

    start = commands.add_parser("start", help="start paused or failed tasks")
    start.add_argument("taskIds", nargs="+", metavar="taskId", help=TASK_ID_HELP)

    remove = commands.add_parser("remove", help="remove tasks; unfinished files are always deleted")
    remove.add_argument("taskIds", nargs="+", metavar="taskId", help=TASK_ID_HELP)
    remove.add_argument("--delete-files", action="store_true", help="also delete completed files")

    probe = commands.add_parser("probe", help="show name, size and files of a URL without adding a task")
    probe.add_argument("url")
    probe.add_argument("-H", "--header", action="append", default=[], metavar="'NAME: VALUE'", help=HEADER_HELP)
    return parser


def isSilent(argv: list[str]) -> bool:
    return "--silence" in argv or any(isWakeUri(arg) for arg in argv)


def toResult(result, exitCode: int = 0) -> Reply:
    return Reply(json.dumps({"result": result}), exitCode)


def toError(code: str, message: str, exitCode: int = 1) -> Reply:
    return Reply(json.dumps({"error": {"code": code, "message": message}}), exitCode)


def toSummary(task: Task) -> dict:
    error = task.lastError if task.status == TaskStatus.FAILED else None
    return {
        "taskId": task.taskId,
        "name": task.name,
        "status": task.status.name.lower(),
        "progress": round(task.currentSnapshot()[0], 1),
        "fileSize": task.fileSize,
        "outputFolder": str(task.outputFolder),
        "error": str(error) if error else None,
    }


def toFiles(task: Task) -> list[dict]:
    return [{"index": file.index, "path": file.relativePath, "fileSize": file.size, "isSelected": file.selected}
            for file in task.files or []]


def toUrl(arg: str, cwd: str) -> str:
    if arg.find(":") > 1:
        return arg
    path = Path(cwd, arg)
    return path.resolve().as_uri() if path.is_file() else arg


def toHeaders(lines: list[str]) -> dict[str, str]:
    headers = currentHeaders()
    for line in lines:
        name, _, value = line.partition(":")
        headers[name.strip()] = value.strip()
    return headers


class Cli:
    def __init__(self, taskService, parse, submit, open: Callable[[list[str]], None],
                 activate: Callable[[], None]) -> None:
        self._taskService = taskService
        self._parse = parse
        self._submit = submit
        self._openUris = open
        self._activate = activate
        self._parser = buildParser()
        self._handlers = {"probe": self._probe, "add": self._add, "tasks": self._tasks, "task": self._task,
                          "pause": self._pause, "start": self._start, "remove": self._remove, "wait": self._wait}

    def run(self, invocation: Invocation) -> None:
        argv, cwd, reply = invocation.argv, invocation.cwd, invocation.reply
        if argv[:1] != ["ghd"]:
            self._open(argv, cwd)
            reply(Reply("", 0))
            return
        try:
            args = self._parser.parse_args(argv[1:])
        except TextRequested as text:
            reply(Reply(str(text).rstrip("\n"), 0))
            return
        except UsageError as error:
            reply(toError("usage", str(error), 2))
            return
        self._handlers[args.command](args, cwd, reply)

    def _open(self, argv: list[str], cwd: str) -> None:
        if any(isWakeUri(arg) for arg in argv):
            return
        uris = [toUrl(arg, cwd) for arg in argv if not arg.startswith("-") and not isLaunchUri(arg)]
        uris = [uri for uri in uris if uri.find(":") > 1]
        if uris:
            self._openUris(uris)
        elif not isSilent(argv):
            self._activate()

    def _tasksOf(self, taskIds: list[str], reply: Callable[[Reply], None]) -> list[Task] | None:
        tasks = [self._taskService.taskById(taskId) for taskId in taskIds]
        if None in tasks:
            missing = taskIds[tasks.index(None)]
            reply(toError("taskNotFound", f"No task with ID {missing}. Run `ghd tasks` to list task IDs."))
            return None
        return tasks

    def _probe(self, args: Namespace, cwd: str, reply: Callable[[Reply], None]) -> None:
        def onParsed(task: Task) -> None:
            reply(toResult({"name": task.name, "fileSize": task.fileSize, "files": toFiles(task)}))

        def onParseFailed(error: Exception) -> None:
            reply(toError("parseFailed", str(toTaskError(error))))

        options = TaskOptions(url=toUrl(args.url, cwd), headers=toHeaders(args.header))
        self._submit(self._parse(options), onParsed, onParseFailed)

    def _add(self, args: Namespace, cwd: str, reply: Callable[[Reply], None]) -> None:
        if len(args.urls) > 1 and (args.name or args.select):
            reply(toError("usage", "--name and --select take a single URL.", 2))
            return
        try:
            selection = [int(index) for index in args.select.split(",")] if args.select else None
        except ValueError:
            reply(toError("usage", "--select takes comma-separated file indexes, e.g. 0,3,5.", 2))
            return
        folder = Path(cwd, args.folder).resolve() if args.folder else Path(cfg.downloadFolder.value)
        choice = NameConflictChoice.OVERWRITE if args.conflict == "overwrite" else NameConflictChoice.KEEP_BOTH
        items: list[dict | None] = [None] * len(args.urls)

        def collect(index: int, item: dict) -> None:
            items[index] = {"url": args.urls[index], **item}
            if None in items:
                return
            isAllAdded = all("error" not in item for item in items)
            reply(toResult(items, 0 if isAllAdded else 1))

        def onParsed(task: Task, index: int) -> None:
            if args.name:
                task.setName(args.name)
            if selection is not None:
                task.setSelection(selection)
            self._taskService.add(task, choice=choice)
            collect(index, {"taskId": task.taskId, "name": task.name})

        def onParseFailed(error: Exception, index: int) -> None:
            collect(index, {"error": {"code": "parseFailed", "message": str(toTaskError(error))}})

        for index, url in enumerate(args.urls):
            options = TaskOptions(url=toUrl(url, cwd), headers=toHeaders(args.header), outputFolder=folder)
            self._submit(self._parse(options), onParsed, onParseFailed, index)

    def _tasks(self, args: Namespace, cwd: str, reply: Callable[[Reply], None]) -> None:
        tasks = self._taskService.tasks
        if args.status:
            tasks = [task for task in tasks if task.status.name.lower() == args.status]
        reply(toResult([toSummary(task) for task in tasks]))

    def _task(self, args: Namespace, cwd: str, reply: Callable[[Reply], None]) -> None:
        if tasks := self._tasksOf([args.taskId], reply):
            reply(toResult({**toSummary(tasks[0]), "files": toFiles(tasks[0])}))

    def _pause(self, args: Namespace, cwd: str, reply: Callable[[Reply], None]) -> None:
        tasks = self._tasksOf(args.taskIds, reply)
        if tasks is None:
            return
        downloading = [task for task in tasks if task.status in (TaskStatus.WAITING, TaskStatus.RUNNING)]
        if unpausable := [task for task in downloading if not task.canPause]:
            reply(toError("cannotPause", f"Task {unpausable[0].taskId} is in a step that cannot be paused."))
            return
        for task in downloading:
            self._taskService.pause(task)
        reply(toResult([toSummary(task) for task in tasks]))

    def _start(self, args: Namespace, cwd: str, reply: Callable[[Reply], None]) -> None:
        tasks = self._tasksOf(args.taskIds, reply)
        if tasks is None:
            return
        for task in tasks:
            if task.status in (TaskStatus.PAUSED, TaskStatus.FAILED):
                self._taskService.start(task)
        reply(toResult([toSummary(task) for task in tasks]))

    def _remove(self, args: Namespace, cwd: str, reply: Callable[[Reply], None]) -> None:
        tasks = self._tasksOf(args.taskIds, reply)
        if tasks is None:
            return
        for task in tasks:
            self._taskService.delete(task, shouldDeleteFiles=args.delete_files)
        reply(toResult(args.taskIds))

    def _wait(self, args: Namespace, cwd: str, reply: Callable[[Reply], None]) -> None:
        tasks = self._tasksOf(args.taskIds, reply)
        if tasks is None:
            return
        signals = (self._taskService.taskCompleted, self._taskService.taskFailed,
                   self._taskService.taskPaused, self._taskService.taskRemoved)

        def onChanged(_=None) -> None:
            remaining = [task for task in tasks if self._taskService.taskById(task.taskId)]
            if any(task.status in (TaskStatus.WAITING, TaskStatus.RUNNING) for task in remaining):
                return
            for signal in signals:
                signal.disconnect(onChanged)
            items = [toSummary(task) if task in remaining
                     else {"taskId": task.taskId, "error": {"code": "taskRemoved", "message": "The task was removed."}}
                     for task in tasks]
            isAllCompleted = all(item.get("status") == "completed" for item in items)
            reply(toResult(items, 0 if isAllCompleted else 1))

        for signal in signals:
            signal.connect(onChanged)
        onChanged()

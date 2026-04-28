from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict, cast


ROOT = Path(__file__).resolve().parents[1]
AGENTS_FILE = ROOT / "AGENTS.md"
RUNNER_FILE = ROOT / "run_automation.ps1"
TASK_FILE = ROOT / "task.json"
PROGRESS_FILE = ROOT / "progress.txt"


class TaskRecord(TypedDict):
    id: int
    title: str
    description: str
    steps: list[str]
    passes: bool


class TaskDocument(TypedDict):
    project: str
    description: str
    tasks: list[TaskRecord]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_json_object(path: Path) -> dict[str, object]:
    raw_data = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw_data, dict):
        raise AssertionError(f"{path.name} must contain a JSON object")

    normalized: dict[str, object] = {}
    raw_mapping = cast(dict[object, object], raw_data)
    for key, value in raw_mapping.items():
        if not isinstance(key, str):
            raise AssertionError(f"{path.name} keys must be strings")
        normalized[key] = value

    return normalized


def read_non_empty_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise AssertionError(f"{label} must be a string")
    if not value.strip():
        raise AssertionError(f"{label} must be a non-empty string")
    return value


def read_task_record(raw_task: object, previous_id: int, seen_ids: set[int]) -> TaskRecord:
    if not isinstance(raw_task, dict):
        raise AssertionError("each task must be a JSON object")

    task_mapping = cast(dict[object, object], raw_task)

    required_fields = {"id", "title", "description", "steps", "passes"}
    if not required_fields.issubset(task_mapping.keys()):
        raise AssertionError("task is missing required fields")

    raw_id = task_mapping["id"]
    if isinstance(raw_id, bool) or not isinstance(raw_id, int):
        raise AssertionError("task id must be an integer")
    if raw_id in seen_ids:
        raise AssertionError("task ids must be unique")
    if raw_id <= previous_id:
        raise AssertionError("task ids must be strictly increasing")

    title = read_non_empty_string(task_mapping["title"], "task title")
    description = read_non_empty_string(task_mapping["description"], "task description")

    raw_steps = task_mapping["steps"]
    if not isinstance(raw_steps, list):
        raise AssertionError("task steps must be a list")
    steps_source = cast(list[object], raw_steps)
    if len(steps_source) == 0:
        raise AssertionError("task steps must be a non-empty list")

    steps: list[str] = []
    for step in steps_source:
        if not isinstance(step, str):
            raise AssertionError("task steps must be strings")
        if not step.strip():
            raise AssertionError("task steps must be non-empty")
        steps.append(step)

    raw_passes = task_mapping["passes"]
    if not isinstance(raw_passes, bool):
        raise AssertionError("task passes must be a boolean")

    return {
        "id": raw_id,
        "title": title,
        "description": description,
        "steps": steps,
        "passes": raw_passes,
    }


def load_task_document() -> TaskDocument:
    data = load_json_object(TASK_FILE)
    project = read_non_empty_string(data.get("project"), "project")
    description = read_non_empty_string(data.get("description"), "description")
    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list):
        raise AssertionError("tasks must be a list")

    previous_id = -1
    seen_ids: set[int] = set()
    tasks: list[TaskRecord] = []

    for raw_task in cast(list[object], raw_tasks):
        task = read_task_record(raw_task, previous_id, seen_ids)
        previous_id = task["id"]
        seen_ids.add(task["id"])
        tasks.append(task)

    return {
        "project": project,
        "description": description,
        "tasks": tasks,
    }


def validate_progress_log(task_document: TaskDocument) -> None:
    progress_text = PROGRESS_FILE.read_text(encoding="utf-8")
    require(progress_text.startswith("# 进度日志"), "progress.txt must start with '# 进度日志'")
    require("### 已完成内容:" in progress_text, "progress.txt must use the Chinese completed section heading")
    require("### 测试验证:" in progress_text, "progress.txt must use the Chinese testing section heading")
    require("### 备注:" in progress_text, "progress.txt must use the Chinese notes section heading")

    for task in task_document["tasks"]:
        if task["passes"]:
            pattern = rf"^## \d{{4}}-\d{{2}}-\d{{2}} - 任务: {re.escape(task['title'])}$"
            require(
                re.search(pattern, progress_text, flags=re.MULTILINE) is not None,
                f"completed task '{task['title']}' must exist in progress.txt",
            )


def validate_agent_contract() -> None:
    agents_text = AGENTS_FILE.read_text(encoding="utf-8")
    required_tokens = [
        "task.json",
        "progress.txt",
        "docs/standards/feature-pack-interface-standard.md",
        "docs/contracts/feature-pack-v1-python-contracts.md",
        "uv run basedpyright",
        "one task per round",
        "must be written in Chinese",
        "The Zen of Python",
        "camelCase",
        "search the internet for current best practices",
        "git commit",
    ]

    for token in required_tokens:
        require(token in agents_text, f"AGENTS.md must mention '{token}'")


def validate_runner_contract() -> None:
    runner_text = RUNNER_FILE.read_text(encoding="utf-8")
    required_tokens = [
        "codex",
        "task.json",
        "progress.txt",
        "--output-last-message",
        "gpt-5.5",
        "model_reasoning_effort",
        "xhigh",
        "--search",
        "--dangerously-bypass-approvals-and-sandbox",
        "git commit",
    ]

    for token in required_tokens:
        require(token in runner_text, f"run_automation.ps1 must mention '{token}'")


def main() -> None:
    require(AGENTS_FILE.exists(), "AGENTS.md is missing")
    require(RUNNER_FILE.exists(), "run_automation.ps1 is missing")
    require(TASK_FILE.exists(), "task.json is missing")
    require(PROGRESS_FILE.exists(), "progress.txt is missing")

    task_document = load_task_document()
    validate_progress_log(task_document)
    validate_agent_contract()
    validate_runner_contract()

    print("automation contract validation passed")


if __name__ == "__main__":
    main()

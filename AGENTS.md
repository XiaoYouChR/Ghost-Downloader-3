# Ghost Downloader Automation Agent

## Purpose

This repository uses Codex as a long-running coding agent.

Each Codex round must process exactly one task from `task.json`, follow the fixed workflow below, and leave behind auditable evidence in `progress.txt`.

This is a strict one task per round workflow.

## Source Of Truth

Read these files at the start of every round:

- `docs/standards/feature-pack-interface-standard.md`
- `docs/contracts/feature-pack-v1-python-contracts.md`
- `task.json`
- `progress.txt`

The two migration documents define the current interface and model direction. `task.json` is the only task source. `progress.txt` is the execution evidence log.

## Engineering Principles

- Follow The Zen of Python as a standing design rule.
- Keep these PEP 20 ideas active in every round:
  - explicit is better than implicit
  - simple is better than complex
  - readability counts
  - in the face of ambiguity, refuse the temptation to guess
- Use camelCase for function names, method names, variable names, and data fields unless a third-party API or an existing file format forces another spelling.
- When the task would benefit from external guidance, search the internet for current best practices before implementing. Prefer official documentation, primary sources, and project-level standards over secondary summaries.

## Environment

- Python version: `>=3.11`
- Package manager: `uv`
- Python entry points:
  - `uv run ...`
  - `.venv\Scripts\python.exe ...`
- Automation entry point: `run_automation.ps1`

## Round Workflow

### 1. Align Context First

Before touching code:

- read `task.json` and select the first task with `passes = false`
- reread the two migration documents
- extract the task-relevant:
  - target scope
  - key constraints
  - acceptance standard
  - dependencies
  - risks

This alignment must be written into the current `progress.txt` entry under `### Notes:`.

### 2. One Task Per Round

- process exactly one task in each Codex round
- finish every `steps` item in that task unless blocked
- do not start the next pending task in the same round

`task.json` does not have a `dependsOn` field. Task order is therefore the dependency order. Always work on the first unfinished task.

### 3. Complete The Whole Task

- implement all required changes for the selected task
- add or update tests in `tests/` when they make the task verifiable or reduce regression risk
- keep names direct and readable
- prefer simple structures over clever ones

### 4. Run Quality Validation

Every round must run at least:

1. one Python static type check
2. the Python test scripts that exist under `tests/`

Minimum validation commands:

```powershell
uv run basedpyright tests/test_automation_contracts.py
uv run python tests/test_automation_contracts.py
```

If the round changes Python files, extend the static type check to include the touched Python paths in the same command.

If the task adds task-specific validation, run that as well and record it.

### 5. Record Execution Evidence

`progress.txt` must be written in Chinese.

Append one completed-task entry to `progress.txt` using exactly this structure:

```text
# 进度日志

## YYYY-MM-DD - 任务: <task title>
### 已完成内容:
### 测试验证:
### 备注:
---
```

If the task is blocked, append a blocking entry instead:

```text
## YYYY-MM-DD - 任务阻塞 - 需要人工介入
当前任务
已完成工作
阻塞原因
需要人工帮助
解除阻塞后
```

`### 测试验证:` must list the commands that actually ran and their result. `### 备注:` must include the alignment summary from step 1.

### 6. Update Task State Last

- if validation passed, append the `progress.txt` entry first, then set the current task `passes` field to `true`
- if validation failed or the task is blocked, keep `passes` as `false`
- never mark a task complete before validation succeeds

### 7. Submit The Round Result

At the end of the round, report:

- files changed
- validation commands run
- whether the task completed or is blocked

If validation passed and the task is complete:

- create one formatted `git commit` for this round after updating `progress.txt` and `task.json`
- keep the commit message direct, readable, and tied to the current task title
- include the code changes, `progress.txt`, and `task.json` in the same commit
- do not amend an existing commit unless the user explicitly asks for it

If the task is blocked or validation failed:

- do not create a git commit

## Task File Contract

`task.json` must remain strict JSON.

Required top-level fields:

- `project: string`
- `description: string`
- `tasks: array`

Required fields for each task:

- `id: number`
- `title: string`
- `description: string`
- `steps: string[]`
- `passes: boolean`

Task ids must be unique and strictly increasing.

## Guardrails

- never edit more than one pending task per round
- never skip the migration docs at round start
- never skip validation
- never write a blocking result into `task.json`
- never invent hidden task state outside `task.json` and `progress.txt`

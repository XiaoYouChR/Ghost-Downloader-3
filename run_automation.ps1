param(
    [string]$TaskFile = "task.json",
    [string]$AgentFile = "AGENTS.md",
    [string]$ProgressFile = "progress.txt",
    [string]$Model = "gpt-5.4",
    [string]$ReasoningEffort = "xhigh",
    [int]$MaxRounds = 0,
    [bool]$Search = $true,
    [bool]$FullAccess = $true,
    [string]$OutputDir = ".automation"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

function Read-TaskFile {
    param(
        [string]$Path
    )

    $raw = Get-Content -Path $Path -Raw -Encoding UTF8
    $data = $raw | ConvertFrom-Json
    Validate-TaskFile -Data $data -Path $Path
    return $data
}

function Validate-TaskFile {
    param(
        [object]$Data,
        [string]$Path
    )

    foreach ($key in @("project", "description", "tasks")) {
        if ($key -notin $Data.PSObject.Properties.Name) {
            throw "Missing '$key' in $Path."
        }
    }

    if ([string]::IsNullOrWhiteSpace([string]$Data.project)) {
        throw "Field 'project' must be a non-empty string."
    }

    if ([string]::IsNullOrWhiteSpace([string]$Data.description)) {
        throw "Field 'description' must be a non-empty string."
    }

    $tasks = @($Data.tasks)
    $previousId = -1
    $seenIds = [System.Collections.Generic.HashSet[int]]::new()

    for ($index = 0; $index -lt $tasks.Count; $index++) {
        $task = $tasks[$index]

        foreach ($key in @("id", "title", "description", "steps", "passes")) {
            if ($key -notin $task.PSObject.Properties.Name) {
                throw "Task index $index is missing '$key'."
            }
        }

        $id = [int]$task.id
        if (-not $seenIds.Add($id)) {
            throw "Task id '$id' is duplicated."
        }

        if ($id -le $previousId) {
            throw "Task ids must be strictly increasing."
        }

        $previousId = $id

        if ([string]::IsNullOrWhiteSpace([string]$task.title)) {
            throw "Task id '$id' has an empty title."
        }

        if ([string]::IsNullOrWhiteSpace([string]$task.description)) {
            throw "Task id '$id' has an empty description."
        }

        $steps = @($task.steps)
        if ($steps.Count -eq 0) {
            throw "Task id '$id' must contain at least one step."
        }

        foreach ($step in $steps) {
            if ([string]::IsNullOrWhiteSpace([string]$step)) {
                throw "Task id '$id' contains an empty step."
            }
        }
    }
}

function Get-NextTask {
    param(
        [object]$Data
    )

    foreach ($task in @($Data.tasks)) {
        if (-not [bool]$task.passes) {
            return $task
        }
    }

    return $null
}

function New-CodexPrompt {
    param(
        [object]$Data,
        [object]$Task,
        [int]$PendingCount
    )

    $stepsText = (@($Task.steps) | ForEach-Object { "- $_" }) -join [Environment]::NewLine

    return @"
You are running one Ghost Downloader automation round.

Follow AGENTS.md exactly.

Read these files before editing:
- docs/standards/feature-pack-interface-standard.md
- docs/contracts/feature-pack-v1-python-contracts.md
- task.json
- progress.txt

Goal:
- Complete task #$($Task.id): $($Task.title)

Context:
- Project: $($Data.project)
- Project description: $($Data.description)
- Pending task count before this round: $PendingCount
- task.json is the only task source
- progress.txt is the execution evidence log

Task description:
$($Task.description)

Task steps:
$stepsText

Constraints:
- Work on this task only.
- Complete every listed step in this task during this round unless blocked.
- Run the required validation before deciding the task is complete.
- Append progress evidence to progress.txt in Chinese.
- Only after validation passes, set this task's passes field to true in task.json.
- If blocked, leave passes as false and write the blocking record to progress.txt.

Done when:
- The task implementation is complete.
- Validation has run.
- progress.txt contains the current round evidence.
- task.json matches the validation outcome.
"@
}

if (-not (Test-Path -Path $AgentFile -PathType Leaf)) {
    throw "Missing AGENTS file: $AgentFile"
}

if (-not (Test-Path -Path $TaskFile -PathType Leaf)) {
    throw "Missing task file: $TaskFile"
}

if (-not (Test-Path -Path $ProgressFile -PathType Leaf)) {
    throw "Missing progress file: $ProgressFile"
}

$outputRoot = Join-Path $repoRoot $OutputDir
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

$roundLimit = if ($MaxRounds -le 0) { [int]::MaxValue } else { $MaxRounds }

for ($round = 1; $round -le $roundLimit; $round++) {
    $taskData = Read-TaskFile -Path $TaskFile
    $tasks = @($taskData.tasks)
    $pendingTasks = @($tasks | Where-Object { -not [bool]$_.passes })
    $nextTask = Get-NextTask -Data $taskData

    if ($null -eq $nextTask) {
        Write-Host "No pending tasks remain in $TaskFile."
        break
    }

    $taskId = [int]$nextTask.id
    $taskTitle = [string]$nextTask.title
    Write-Host "Round ${round}: task #$taskId - $taskTitle"

    $prompt = New-CodexPrompt -Data $taskData -Task $nextTask -PendingCount $pendingTasks.Count
    $promptPath = Join-Path $outputRoot "last_prompt.txt"
    $outputPath = Join-Path $outputRoot "last_message.txt"

    Set-Content -Path $promptPath -Value $prompt -Encoding UTF8

    $codexArgs = @()
    if ($Search) {
        $codexArgs += "--search"
    }

    $codexArgs += "exec"

    $codexArgs += @(
        "-c", "model_reasoning_effort=`"$ReasoningEffort`"",
        "--skip-git-repo-check",
        "--cd", $repoRoot,
        "--model", $Model,
        "--output-last-message", $outputPath,
        "-"
    )

    if ($FullAccess) {
        $codexArgs += "--dangerously-bypass-approvals-and-sandbox"
    }
    else {
        $codexArgs += "--full-auto"
    }

    $prompt | & codex @codexArgs
    if ($LASTEXITCODE -ne 0) {
        throw "codex exec failed with exit code $LASTEXITCODE."
    }

    $updatedData = Read-TaskFile -Path $TaskFile
    $updatedTask = @($updatedData.tasks | Where-Object { [int]$_.id -eq $taskId }) | Select-Object -First 1

    if ($null -eq $updatedTask) {
        throw "Task #$taskId disappeared from $TaskFile."
    }

    if ([bool]$updatedTask.passes) {
        Write-Host "Task #$taskId completed."
        continue
    }

    Write-Warning "Task #$taskId is still pending. Stop automation and inspect progress.txt."
    break
}

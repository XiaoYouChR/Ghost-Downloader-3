package com.xychr.ghostdownloader.ui.components.task

import com.xychr.ghostdownloader.model.*

enum class TaskReadState { LOADING, READY, UNAVAILABLE }

data class TaskListState(
    val tasks: List<TaskUiState> = emptyList(),
    val readState: TaskReadState = TaskReadState.LOADING,
)

data class TaskSummary(val speed: Long = 0, val running: Int = 0, val waiting: Int = 0)

fun buildTaskSummary(tasks: List<TaskUiState>): TaskSummary = TaskSummary(
    speed = tasks.filter { it.status == TaskStatus.RUNNING }.sumOf { it.speed },
    running = tasks.count { it.status == TaskStatus.RUNNING },
    waiting = tasks.count { it.status == TaskStatus.WAITING },
)

enum class TaskBatchAction { START, PAUSE }

data class TaskBatchTargets(
    val startIds: List<String> = emptyList(),
    val pauseIds: List<String> = emptyList(),
    val retryCount: Int = 0,
    val skippedPauseCount: Int = 0,
)

fun buildTaskBatchTargets(tasks: List<TaskUiState>): TaskBatchTargets {
    val pauseIds = tasks.filter { it.status == TaskStatus.RUNNING && it.canPause }.map { it.id }
    return TaskBatchTargets(
        startIds = tasks.filter { it.status in setOf(TaskStatus.PAUSED, TaskStatus.WAITING, TaskStatus.FAILED) }.map { it.id },
        pauseIds = pauseIds,
        retryCount = tasks.count { it.status == TaskStatus.FAILED },
        // The Android pause entry point cannot pause WAITING tasks. Do not promise a stopped queue.
        skippedPauseCount = tasks.count { it.status == TaskStatus.RUNNING || it.status == TaskStatus.WAITING } - pauseIds.size,
    )
}

data class TaskBatchResult(val submitted: Int, val failed: Int, val skipped: Int)

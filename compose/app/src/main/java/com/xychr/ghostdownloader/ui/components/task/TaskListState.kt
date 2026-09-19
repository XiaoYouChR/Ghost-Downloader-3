package com.xychr.ghostdownloader.ui.components.task

import com.xychr.ghostdownloader.model.*

enum class SortField { CREATED, COMPLETED, NAME, SIZE, QUEUE }

data class TaskListState(
    val tasks: List<TaskUiState> = emptyList(),
    val hasLoaded: Boolean = false,
)

fun buildTaskOrder(
    tasks: List<TaskUiState>,
    query: String,
    categoryFilter: String?,
    sortField: SortField,
    isDescending: Boolean,
): List<TaskUiState> {
    val matched = tasks.filter { task ->
        (categoryFilter == null || task.categoryId == categoryFilter) &&
            (query.isBlank() ||
                task.name.contains(query, ignoreCase = true) ||
                task.url.contains(query, ignoreCase = true))
    }
    val ascending = when (sortField) {
        SortField.QUEUE -> return buildQueueOrder(matched, isDescending)
        SortField.CREATED -> matched.sortedBy { it.createdAt }
        SortField.COMPLETED -> matched.sortedBy { it.completedAt }
        SortField.NAME -> matched.sortedBy { it.name.lowercase() }
        SortField.SIZE -> matched.sortedBy { it.fileSize }
    }
    return if (isDescending) ascending.reversed() else ascending
}

private fun buildQueueOrder(tasks: List<TaskUiState>, descending: Boolean): List<TaskUiState> {
    val (running, nonRunning) = tasks.partition { it.status == TaskStatus.RUNNING }
    val (waiting, rest) = nonRunning.partition { it.queueOrder != null }
    val buckets = listOf(
        running,
        waiting.sortedWith(compareBy { it.queueOrder }),
        rest.sortedByDescending { it.createdAt },
    )
    return (if (descending) buckets else buckets.reversed()).flatten()
}

data class TaskSections(val active: List<TaskUiState>, val completed: List<TaskUiState>)

fun buildTaskSections(tasks: List<TaskUiState>, heldSections: Map<String, Boolean>): TaskSections {
    val (completed, active) = tasks.partition { heldSections[it.id] ?: it.isFinished }
    return TaskSections(active, completed)
}

fun buildTotalSpeed(tasks: List<TaskUiState>): Long =
    tasks.filter { it.status == TaskStatus.RUNNING }.sumOf { it.speed }

data class TaskBatchTargets(
    val startIds: List<String> = emptyList(),
    val pauseIds: List<String> = emptyList(),
    val skippedPauseCount: Int = 0,
)

private val TaskUiState.canBePaused: Boolean
    get() = status == TaskStatus.WAITING || (status == TaskStatus.RUNNING && canPause)

fun buildTaskBatchTargets(tasks: List<TaskUiState>): TaskBatchTargets = TaskBatchTargets(
    startIds = tasks.filter { it.status in setOf(TaskStatus.PAUSED, TaskStatus.WAITING, TaskStatus.FAILED) }.map { it.id },
    pauseIds = tasks.filter { it.canBePaused }.map { it.id },
    skippedPauseCount = tasks.count { it.status == TaskStatus.RUNNING && !it.canBePaused },
)

data class TaskBatchResult(val submitted: Int, val failed: Int)

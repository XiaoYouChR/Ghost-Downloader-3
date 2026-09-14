package com.xychr.ghostdownloader

import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.components.task.*
import com.xychr.ghostdownloader.ui.pages.*
import org.junit.Assert.*
import org.junit.Test

class TaskSummaryTest {
    @Test fun buildSummaryIncludesAllRunningCategoriesAndNotOldPausedSpeeds() {
        val tasks = listOf(
            TaskUiState(id = "video", categoryId = "video", status = "RUNNING", speed = 100),
            TaskUiState(id = "other", categoryId = "other", status = "RUNNING", speed = 200),
            TaskUiState(id = "paused", status = "PAUSED", speed = 500),
            TaskUiState(id = "waiting", status = "WAITING"),
            TaskUiState(id = "done", status = "COMPLETED", speed = 400),
        )
        assertEquals(TaskSummary(300, 2, 1), buildTaskSummary(tasks))
    }

    @Test fun buildSummaryDistinguishesRunningAtZeroFromIdle() {
        assertEquals(TaskSummary(0, 1, 0), buildTaskSummary(listOf(TaskUiState(status = "RUNNING"))))
        assertEquals(TaskSummary(), buildTaskSummary(emptyList()))
    }

    @Test fun buildStartTargetsIncludesRetriesButNeverCompletedOrRunning() {
        val tasks = listOf("PAUSED", "WAITING", "FAILED", "COMPLETED", "RUNNING")
            .map { TaskUiState(id = it, status = it) }
        val targets = buildTaskBatchTargets(tasks)
        assertEquals(listOf("PAUSED", "WAITING", "FAILED"), targets.startIds)
        assertEquals(1, targets.retryCount)
    }

    @Test fun buildPauseTargetsMatchesAndroidEngineAndSkipsUnpausableAndWaiting() {
        val tasks = listOf(
            TaskUiState(id = "safe", status = "RUNNING", canPause = true),
            TaskUiState(id = "seeding", status = "RUNNING", canPause = false),
            TaskUiState(id = "unsafe", status = "RUNNING", canPause = false),
            TaskUiState(id = "waiting", status = "WAITING", canPause = true),
            TaskUiState(id = "paused", status = "PAUSED"),
            TaskUiState(id = "failed", status = "FAILED"),
        )
        val targets = buildTaskBatchTargets(tasks)
        assertEquals(listOf("safe"), targets.pauseIds)
        assertEquals(3, targets.skippedPauseCount)
    }

    @Test fun buildSelectedTargetsDoesNotIncludeUnselectedTasks() {
        val tasks = listOf(TaskUiState(id = "selected", status = "PAUSED"), TaskUiState(id = "other", status = "FAILED"))
        assertEquals(listOf("selected"), buildTaskBatchTargets(tasks.filter { it.id == "selected" }).startIds)
        assertEquals(0, buildTaskBatchTargets(tasks.filter { it.id == "selected" }).retryCount)
    }

    @Test fun initialListIsLoadingNotAnIdleSnapshot() {
        assertEquals(TaskReadState.LOADING, TaskListState().readState)
    }
}

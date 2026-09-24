package com.xychr.ghostdownloader

import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.components.task.*
import org.junit.Assert.*
import org.junit.Test

class TaskListStateTest {
    @Test fun totalSpeedSumsRunningTasksAndIgnoresPausedOrCompletedOnes() {
        val tasks = listOf(
            TaskUiState(id = "video", categoryId = "video", status = "RUNNING", speed = 100),
            TaskUiState(id = "other", categoryId = "other", status = "RUNNING", speed = 200),
            TaskUiState(id = "paused", status = "PAUSED", speed = 500),
            TaskUiState(id = "waiting", status = "WAITING"),
            TaskUiState(id = "done", status = "COMPLETED", speed = 400),
        )
        assertEquals(300L, buildTotalSpeed(tasks))
    }

    @Test fun buildStartTargetsIncludesRetriesButNeverCompletedOrRunning() {
        val tasks = listOf("PAUSED", "WAITING", "FAILED", "COMPLETED", "RUNNING")
            .map { TaskUiState(id = it, status = it) }
        assertEquals(listOf("PAUSED", "WAITING", "FAILED"), buildTaskBatchTargets(tasks).startIds)
    }

    @Test fun buildPauseTargetsIncludesQueuedTasksButSkipsUnpausableOnes() {
        val tasks = listOf(
            TaskUiState(id = "safe", status = "RUNNING", canPause = true),
            TaskUiState(id = "live", status = "RUNNING", canPause = false),
            TaskUiState(id = "waiting", status = "WAITING", canPause = true),
            TaskUiState(id = "paused", status = "PAUSED"),
            TaskUiState(id = "failed", status = "FAILED"),
        )
        val targets = buildTaskBatchTargets(tasks)
        assertEquals(listOf("safe", "waiting"), targets.pauseIds)
    }

    @Test fun initialListIsNotLoadedYet() {
        assertFalse(TaskListState().hasLoaded)
    }
}

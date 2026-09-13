package com.xychr.ghostdownloader

import com.xychr.ghostdownloader.ui.task.TaskUiState
import com.xychr.ghostdownloader.ui.task.buildTaskSections
import com.xychr.ghostdownloader.ui.task.isFinished
import org.junit.Assert.*
import org.junit.Test

class TaskSectionsTest {
    @Test fun failedTasksRemainUnfinished() {
        val failed = TaskUiState(id = "failed", status = "FAILED")
        val completed = TaskUiState(id = "done", status = "COMPLETED")
        val sections = buildTaskSections(listOf(failed, completed), emptyMap())
        assertEquals(listOf(failed), sections.active)
        assertEquals(listOf(completed), sections.completed)
    }

    @Test fun completionUpdatesStateWithoutMovingAnInteractingCard() {
        val completed = TaskUiState(id = "task", status = "COMPLETED", progress = 100.0)
        val held = buildTaskSections(listOf(completed), mapOf("task" to false))
        assertTrue(held.active.single().isFinished)
        assertEquals(100.0, held.active.single().progress, 0.0)
        assertTrue(held.completed.isEmpty())
        assertEquals(listOf(completed), buildTaskSections(listOf(completed), emptyMap()).completed)
    }

    @Test fun seedingIsStillAnExecutingTask() {
        val task = TaskUiState(id = "seed", status = "RUNNING", isSeeding = true, progress = 100.0)
        assertEquals(listOf(task), buildTaskSections(listOf(task), emptyMap()).active)
    }

    @Test fun removedTasksAreNotResurrectedByHeldPositions() {
        val sections = buildTaskSections(emptyList(), mapOf("gone" to false))
        assertTrue(sections.active.isEmpty())
        assertTrue(sections.completed.isEmpty())
    }

    @Test fun partitionKeepsTheRequestedSortOrder() {
        val tasks = listOf(
            TaskUiState(id = "a", status = "RUNNING"),
            TaskUiState(id = "b", status = "COMPLETED"),
            TaskUiState(id = "c", status = "PAUSED"),
        )
        assertEquals(listOf("a", "c"), buildTaskSections(tasks, emptyMap()).active.map { it.id })
    }
}

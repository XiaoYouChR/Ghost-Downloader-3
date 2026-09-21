package com.xychr.ghostdownloader

import com.xychr.ghostdownloader.model.TaskUiState
import com.xychr.ghostdownloader.ui.components.task.SortField
import com.xychr.ghostdownloader.ui.components.task.buildTaskOrder
import org.junit.Assert.*
import org.junit.Test

class TaskOrderTest {
    private val running = TaskUiState(id = "running", status = "RUNNING", createdAt = 10)
    private val waitingLate = TaskUiState(id = "waitingLate", status = "WAITING", createdAt = 20, queueOrder = 1)
    private val waitingEarly = TaskUiState(id = "waitingEarly", status = "WAITING", createdAt = 30, queueOrder = 0)
    private val paused = TaskUiState(id = "paused", status = "PAUSED", createdAt = 40)
    private val completed = TaskUiState(id = "completed", status = "COMPLETED", createdAt = 50)

    @Test fun queueOrderPutsRunningThenTheQueueThenTheRestByNewestFirst() {
        val tasks = listOf(paused, waitingLate, completed, waitingEarly, running)
        val ids = buildTaskOrder(tasks, "", null, SortField.QUEUE, isDescending = true).map { it.id }
        assertEquals(listOf("running", "waitingEarly", "waitingLate", "completed", "paused"), ids)
    }

    @Test fun queueOrderAscendingFlipsOnlyTheBucketOrderNotTheBuckets() {
        val tasks = listOf(paused, waitingLate, completed, waitingEarly, running)
        val ids = buildTaskOrder(tasks, "", null, SortField.QUEUE, isDescending = false).map { it.id }
        assertEquals(listOf("completed", "paused", "waitingEarly", "waitingLate", "running"), ids)
    }

    @Test fun searchMatchesNameOrUrlAndCombinesWithTheCategoryFilter() {
        val tasks = listOf(
            TaskUiState(id = "1", name = "Solo Leveling", url = "https://example.com/a", categoryId = "video", createdAt = 10),
            TaskUiState(id = "2", name = "podcast", url = "https://example.com/solo", categoryId = "music", createdAt = 20),
            TaskUiState(id = "3", name = "Solo trailer", url = "https://example.com/b", categoryId = "music", createdAt = 30),
        )
        assertEquals(listOf("1", "2", "3"),
            buildTaskOrder(tasks, "solo", null, SortField.CREATED, isDescending = false).map { it.id })
        assertEquals(listOf("2", "3"),
            buildTaskOrder(tasks, "solo", "music", SortField.CREATED, isDescending = false).map { it.id })
        assertEquals(listOf("1"),
            buildTaskOrder(tasks, "", "video", SortField.CREATED, isDescending = false).map { it.id })
    }

    @Test fun nameSortIgnoresCaseAndDescendingReversesIt() {
        val tasks = listOf(
            TaskUiState(id = "lower", name = "beta", createdAt = 10),
            TaskUiState(id = "upper", name = "Alpha", createdAt = 20),
        )
        assertEquals(listOf("upper", "lower"),
            buildTaskOrder(tasks, "", null, SortField.NAME, isDescending = false).map { it.id })
        assertEquals(listOf("lower", "upper"),
            buildTaskOrder(tasks, "", null, SortField.NAME, isDescending = true).map { it.id })
    }
}

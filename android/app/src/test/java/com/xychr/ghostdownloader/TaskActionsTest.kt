package com.xychr.ghostdownloader

import com.xychr.ghostdownloader.model.TaskDetail
import com.xychr.ghostdownloader.model.TaskUiState
import com.xychr.ghostdownloader.ui.components.task.TaskAction
import com.xychr.ghostdownloader.ui.components.task.buildTaskActions
import com.xychr.ghostdownloader.ui.components.task.buildTaskMainAction
import com.xychr.ghostdownloader.ui.components.task.buildVerifyHashAction
import org.junit.Assert.*
import org.junit.Test

class TaskActionsTest {

    private fun TaskUiState.actionIds(isCategoryEnabled: Boolean = false) =
        buildTaskActions(this, isCategoryEnabled)

    @Test fun runningTaskPausesUnlessItCannotResume() {
        val pausable = TaskUiState(status = "RUNNING", canPause = true)
        assertEquals(TaskAction.PAUSE, pausable.actionIds().main.action)
        assertTrue(pausable.actionIds().main.isEnabled)

        val singleStream = TaskUiState(status = "RUNNING", canPause = false)
        assertEquals(TaskAction.PAUSE, singleStream.actionIds().main.action)
        assertFalse(singleStream.actionIds().main.isEnabled)
    }

    @Test fun stoppableTaskOffersStopInsteadOfPause() {
        val live = TaskUiState(status = "RUNNING", canStop = true)
        assertEquals(TaskAction.STOP, live.actionIds().main.action)
        assertTrue(live.actionIds().main.isEnabled)
    }

    @Test fun completedFileTaskOpensTheFileAndOffersFolderShareRedownload() {
        val task = TaskUiState(status = "COMPLETED", hasOutputFile = true)
        val built = task.actionIds()
        assertEquals(TaskAction.OPEN_FILE, built.main.action)
        assertEquals(
            listOf(TaskAction.OPEN_FOLDER, TaskAction.SHARE_FILE, TaskAction.REDOWNLOAD),
            built.inline.map { it.action },
        )
    }

    @Test fun completedFolderTaskOpensTheFolderAndOffersNothingElseToOpen() {
        val task = TaskUiState(status = "COMPLETED", hasOutputFile = true, isOutputFolder = true)
        val built = task.actionIds()
        assertEquals(TaskAction.OPEN_FOLDER, built.main.action)
        assertEquals(listOf(TaskAction.REDOWNLOAD), built.inline.map { it.action })
    }

    @Test fun completedTaskWithoutOutputFallsBackToItsFolder() {
        val installed = TaskUiState(status = "COMPLETED", hasOutputFile = false)
        assertFalse(installed.actionIds().inline.any { it.action == TaskAction.SHARE_FILE })
        assertFalse(installed.actionIds().inline.any { it.action == TaskAction.OPEN_FILE })
    }

    @Test fun seedingTaskStopsSeedingAndKeepsOpening() {
        val task = TaskUiState(status = "COMPLETED", hasOutputFile = true, canSeed = true, isSeeding = true)
        val built = task.actionIds()
        assertEquals(TaskAction.STOP_SEEDING, built.main.action)
        assertEquals(
            listOf(TaskAction.OPEN_FILE, TaskAction.OPEN_FOLDER, TaskAction.REDOWNLOAD),
            built.inline.map { it.action },
        )
    }

    @Test fun seedableCompletedTaskStartsSeeding() {
        val task = TaskUiState(status = "COMPLETED", hasOutputFile = true, isOutputFolder = true, canSeed = true)
        val built = task.actionIds()
        assertEquals(TaskAction.START_SEEDING, built.main.action)
        assertEquals(listOf(TaskAction.OPEN_FOLDER, TaskAction.REDOWNLOAD), built.inline.map { it.action })
    }

    @Test fun seedableTaskWithMissingFileCannotSeed() {
        val task = TaskUiState(status = "COMPLETED", hasOutputFile = true, isFileMissing = true, canSeed = true)
        assertEquals(TaskAction.REDOWNLOAD, task.actionIds().main.action)
    }

    @Test fun failedTaskRetriesAndKeepsRedownload() {
        val task = TaskUiState(status = "FAILED")
        val built = task.actionIds()
        assertEquals(TaskAction.RESUME, built.main.action)
        assertEquals(listOf(TaskAction.REDOWNLOAD), built.inline.map { it.action })
    }

    @Test fun cardAndDetailAgreeOnTheMainAction() {
        for (status in listOf("RUNNING", "PAUSED", "WAITING", "COMPLETED", "FAILED")) {
            for (hasOutputFile in listOf(false, true)) {
                for (isOutputFolder in listOf(false, true)) {
                    val card = TaskUiState(
                        status = status, hasOutputFile = hasOutputFile, isOutputFolder = isOutputFolder,
                    )
                    val detail = TaskDetail(
                        status = status, hasOutputFile = hasOutputFile, isOutputFolder = isOutputFolder,
                    )
                    assertEquals(buildTaskMainAction(card), buildTaskMainAction(detail))
                }
            }
        }
    }

    @Test fun queuedTaskMovesToFrontInPlaceOfTheMenu() {
        for (status in listOf("PAUSED", "WAITING")) {
            val built = TaskUiState(status = status).actionIds()
            assertEquals(listOf(TaskAction.MOVE_TO_FRONT), built.inline.map { it.action })
            assertFalse(built.menu.any { it.action == TaskAction.MOVE_TO_FRONT })
        }
    }

    @Test fun noActionAppearsInTwoSlots() {
        for (status in listOf("RUNNING", "PAUSED", "WAITING", "COMPLETED", "FAILED")) {
            for (isFolder in listOf(false, true)) {
                val built = buildTaskActions(
                    TaskUiState(status = status, hasOutputFile = true, isOutputFolder = isFolder,
                        canEdit = true, fileCount = 3),
                    isCategoryEnabled = true,
                )
                val slots = listOf(built.main.action) + built.inline.map { it.action }
                assertEquals(slots.distinct(), slots)
                assertTrue(built.menu.none { it.action in slots })
            }
        }
    }

    @Test fun menuDropsWhatDoesNotApply() {
        val running = TaskUiState(status = "RUNNING", hasOutputFile = true, canEdit = true, fileCount = 1)
        val menu = running.actionIds().menu.map { it.action }
        assertFalse("单文件任务不该有选文件", TaskAction.FILES in menu)
        assertTrue(TaskAction.EDIT in menu)
        assertFalse("编辑只对未完成的任务有意义", TaskAction.EDIT in
            running.copy(status = "COMPLETED").actionIds().menu.map { it.action })
        assertFalse("关闭分类时不该出现改分类", TaskAction.CATEGORY in menu)
        assertTrue(TaskAction.CATEGORY in running.actionIds(isCategoryEnabled = true).menu.map { it.action })
        assertEquals(TaskAction.DELETE, menu.last())
    }

    @Test fun hashOnlyOfferedForCompletedSingleFiles() {
        fun menuOf(task: TaskUiState) = task.actionIds().menu.map { it.action }
        assertFalse(TaskAction.VERIFY_HASH in menuOf(TaskUiState(status = "RUNNING", hasOutputFile = true)))
        assertTrue(TaskAction.VERIFY_HASH in menuOf(TaskUiState(status = "COMPLETED", hasOutputFile = true)))
        assertFalse("文件夹读不出单个摘要",
            TaskAction.VERIFY_HASH in menuOf(
                TaskUiState(status = "COMPLETED", hasOutputFile = true, isOutputFolder = true)))
        assertFalse(TaskAction.VERIFY_HASH in menuOf(TaskUiState(status = "COMPLETED", hasOutputFile = false)))
    }

    @Test fun missingFileMakesRedownloadTheMainAction() {
        val built = TaskUiState(status = "COMPLETED", hasOutputFile = true, isFileMissing = true).actionIds()

        assertEquals(TaskAction.REDOWNLOAD, built.main.action)
        assertFalse("重新下载只出现一次",
            built.inline.any { it.action == TaskAction.REDOWNLOAD } ||
                built.menu.any { it.action == TaskAction.REDOWNLOAD })
        assertFalse("文件不在就没得分享", built.inline.any { it.action == TaskAction.SHARE_FILE })
        assertTrue("文件夹还在", built.inline.any { it.action == TaskAction.OPEN_FOLDER })
        assertFalse(built.menu.first { it.action == TaskAction.VERIFY_HASH }.isEnabled)

        val present = TaskUiState(status = "COMPLETED", hasOutputFile = true).actionIds()
        assertEquals(TaskAction.OPEN_FILE, present.main.action)
        assertTrue(present.menu.first { it.action == TaskAction.VERIFY_HASH }.isEnabled)
    }

    @Test fun detailOffersHashUnderTheSameConditions() {
        fun gatingOf(detail: TaskDetail): Boolean? = buildVerifyHashAction(detail)?.isEnabled

        assertNull(gatingOf(TaskDetail(status = "RUNNING", hasOutputFile = true)))
        assertNull(gatingOf(TaskDetail(status = "COMPLETED", hasOutputFile = true, isOutputFolder = true)))
        assertEquals(false, gatingOf(TaskDetail(status = "COMPLETED", hasOutputFile = true, isFileMissing = true)))
        assertEquals(true, gatingOf(TaskDetail(status = "COMPLETED", hasOutputFile = true)))
    }

    @Test fun completedTaskKeepsRedownloadOutOfTheMenu() {
        val task = TaskUiState(status = "COMPLETED", hasOutputFile = true)
        assertFalse(TaskAction.REDOWNLOAD in task.actionIds().menu.map { it.action })
        assertTrue(TaskAction.REDOWNLOAD in
            TaskUiState(status = "RUNNING").actionIds().menu.map { it.action })
    }
}

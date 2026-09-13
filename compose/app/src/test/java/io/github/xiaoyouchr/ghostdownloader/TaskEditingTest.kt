package com.xychr.ghostdownloader

import com.xychr.ghostdownloader.ui.task.*
import com.xychr.ghostdownloader.ui.settings.Category
import org.junit.Assert.*
import org.junit.Test

class TaskEditingTest {
    @Test fun optionsRoundTripPreservesSupportedCapabilities() {
        val options = TaskOptions("/downloads", headers = mapOf("Referer" to "https://example.test"), subworkerCount = 8)
        assertEquals(options, options.toDraft().toOptions())
        assertNull(options.toDraft().toOptions().recordLimit)
    }

    @Test fun invalidConnectionsStayInDraftAndCannotBeSubmitted() {
        val draft = TaskOptionDraft("/downloads", connections = "not a number")
        assertThrows(IllegalArgumentException::class.java) { draft.toOptions() }
        assertEquals("not a number", draft.connections)
    }

    @Test fun headerValueCanContainColons() {
        val options = TaskOptionDraft("/downloads", headers = "Referer: https://example.test:8443/video").toOptions()
        assertEquals("https://example.test:8443/video", options.headers?.get("Referer"))
    }

    @Test fun invalidHeaderDoesNotSilentlyDisappear() {
        assertThrows(IllegalArgumentException::class.java) {
            TaskOptionDraft("/downloads", headers = "broken header").toOptions()
        }
    }

    @Test fun fileSelectionIsIndependentFromEngineSnapshot() {
        val detail = TaskDetail(id = "one", files = listOf(TaskFile(index = 1, isSelected = true)))
        val initial = TaskFilesState(detail, setOf(1), setOf(1))
        val edited = initial.copy(selected = emptySet())
        assertTrue(edited.hasChanges)
        assertTrue(detail.files.single().isSelected)
        assertFalse(initial.hasChanges)
    }

    @Test fun deletedCategoryFallsBackWithoutChangingTheTaskRecord() {
        val task = TaskUiState(categoryId = "deleted")
        assertEquals("", toCategoryId(task.categoryId, listOf(Category(categoryId = "video"))))
        assertEquals("deleted", task.categoryId)
    }

    @Test fun otherCategoryIsNotUncategorized() {
        assertEquals("cat_other", toCategoryId("cat_other", listOf(Category(categoryId = "cat_other"))))
        assertEquals("", toCategoryId("", listOf(Category(categoryId = "cat_other"))))
    }
}

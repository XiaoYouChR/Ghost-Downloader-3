package com.xychr.ghostdownloader.draft

import androidx.lifecycle.ViewModelStore
import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.components.draft.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.test.resetMain
import org.junit.Before
import org.junit.After
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class DraftWorkflowTest {
    @Before fun setMain() { Dispatchers.setMain(Dispatchers.Unconfined) }
    @After fun clearMain() { Dispatchers.resetMain() }

    @Test fun confirmFlushesLatestInputAndOptionsBeforeSubmitting() = runBlocking {
        val calls = mutableListOf<String>()
        val store = ViewModelStore()
        val draft = DraftViewModel(
            send = { name, _ -> calls += name },
            draftFlow = emptyFlow(),
            categoriesFlow = emptyFlow(),
        )
        store.put("draft", draft)
        try {
            draft.setUrls("https://example.test/latest")
            assertTrue(draft.confirm())
            assertTrue(calls.contains("parse"))
            assertTrue(calls.contains("setDraftSubworkerCount"))
            assertEquals("confirmDraft", calls.last())
            assertEquals("", draft.state.value.urls)
        } finally { store.clear() }
    }

    @Test fun clearingFolderIsNotOverwrittenByLaterProjections() = runBlocking {
        val flow = MutableStateFlow(
            DraftProjection(items = listOf(DraftItem(url = "one", isParsing = false, outputFolder = "/default")))
        )
        val store = ViewModelStore()
        val draft = DraftViewModel(
            send = { _, _ -> },
            draftFlow = flow,
            categoriesFlow = emptyFlow(),
        )
        store.put("draft", draft)
        try {
            assertEquals("/default", draft.state.value.globalFolder)
            draft.setGlobalFolder("")
            flow.value = DraftProjection(
                items = listOf(
                    DraftItem(url = "one", isParsing = false, outputFolder = "/default"),
                    DraftItem(url = "two"),
                )
            )
            assertEquals("", draft.state.value.globalFolder)
        } finally { store.clear() }
    }

    @Test fun categoryApplyReadsDestinationFromPushedProjection() = runBlocking {
        var item = DraftItem(url = "one", isParsing = false)
        val calls = mutableListOf<Pair<String, List<Any?>>>()
        val flow = MutableStateFlow(DraftProjection(listOf(item)))
        val store = ViewModelStore()
        val draft = DraftViewModel(
            send = { name, args ->
                calls.add(name to args)
                item = item.copy(categoryChoice = "video", categoryId = "video")
                flow.value = DraftProjection(listOf(item))
            },
            draftFlow = flow,
            categoriesFlow = emptyFlow(),
        )
        store.put("draft", draft)
        try {
            assertTrue(draft.setCategory("one", "video"))
            assertEquals(listOf("setDraft" to listOf<Any?>("one", "setCategory", "video")), calls)
            assertEquals("video", draft.state.value.items.single().categoryId)
            assertFalse(draft.state.value.isWorking)
        } finally { store.clear() }
    }

    @Test fun failedCategoryApplyDoesNotPublishAnOptimisticDestination() = runBlocking {
        val item = DraftItem(url = "one", isParsing = false)
        val store = ViewModelStore()
        val draft = DraftViewModel(
            send = { _, _ -> error("Save failed") },
            draftFlow = MutableStateFlow(DraftProjection(listOf(item))),
            categoriesFlow = emptyFlow(),
        )
        store.put("draft", draft)
        try {
            assertFalse(draft.setCategory("one", "video"))
            assertEquals(item, draft.state.value.items.single())
            assertFalse(draft.state.value.error == null)
            assertFalse(draft.state.value.isWorking)
        } finally { store.clear() }
    }

    @Test fun sendPackRoutesProbeToSeparateEngineMethod() = runBlocking {
        val calls = mutableListOf<Pair<String, List<Any?>>>()
        val store = ViewModelStore()
        val draft = DraftViewModel(
            send = { name, args -> calls.add(name to args) },
            draftFlow = emptyFlow(),
            categoriesFlow = emptyFlow(),
        )
        store.put("draft", draft)
        try {
            draft.sendPack("one", "probe", listOf("media"))
            draft.sendPack("one", "setTrack", listOf("video", true))
            assertEquals("probeDraft", calls[0].first)
            assertEquals(listOf<Any?>("one", "media"), calls[0].second)
            assertEquals("setDraft", calls[1].first)
            assertEquals(listOf<Any?>("one", "setTrack", "video", true), calls[1].second)
        } finally { store.clear() }
    }

    @Test fun nullCategoryChoiceCrossesAsNullNotEmptyString() = runBlocking {
        val calls = mutableListOf<Pair<String, List<Any?>>>()
        val store = ViewModelStore()
        val draft = DraftViewModel(
            send = { name, args -> calls.add(name to args) },
            draftFlow = emptyFlow(),
            categoriesFlow = emptyFlow(),
        )
        store.put("draft", draft)
        try {
            draft.setCategory("one", null)
            assertEquals(listOf<Any?>("one", "setCategory", null), calls.single().second)
        } finally { store.clear() }
    }

    @Test fun fileChangesReportsOnlyEditedFields() {
        val initial = listOf(DraftFile(0, "a/b.mp4", 10, true), DraftFile(1, "a/c.mp4", 20, true))
        assertTrue(fileChanges(initial, initial).isEmpty())

        val deselected = initial.map { if (it.index == 1) it.copy(isSelected = false) else it }
        assertEquals(listOf(DraftChange("setSelection", listOf<Any?>("0"))), fileChanges(initial, deselected))

        val renamed = initial.map { if (it.index == 0) it.copy(path = "a/z.mp4") else it }
        assertEquals(listOf(DraftChange("setFileName", listOf<Any?>(0, "a/z.mp4"))), fileChanges(initial, renamed))

        val both = listOf(initial[0].copy(path = "a/z.mp4"), initial[1].copy(isSelected = false))
        assertEquals(
            listOf(
                DraftChange("setSelection", listOf<Any?>("0")),
                DraftChange("setFileName", listOf<Any?>(0, "a/z.mp4")),
            ),
            fileChanges(initial, both),
        )
    }
}

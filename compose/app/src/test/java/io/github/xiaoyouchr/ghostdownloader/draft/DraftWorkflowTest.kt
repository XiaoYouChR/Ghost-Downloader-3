package com.xychr.ghostdownloader.ui.draft

import androidx.lifecycle.ViewModelStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
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
    @Test fun completedProbeClearsLoadingEvenWhenDependencyReturnsImmediately() = runBlocking {
        val item = DraftItem(url = "one", isParsing = false)
        val store = ViewModelStore()
        val draft = DraftViewModel(fetchItems = { listOf(item) }, send = { _, _ -> }, categoriesFlow = emptyFlow())
        store.put("draft", draft)
        try {
            draft.probe("one", "media")
            assertFalse("Completed probe left a loading indicator", "one" in draft.state.value.probing)
            assertTrue(draft.state.value.probeErrors.isEmpty())
        } finally { store.clear() }
    }

    @Test fun failedProbeCanBeRetriedAndClearsPreviousError() = runBlocking {
        val item = DraftItem(url = "one", isParsing = false)
        val store = ViewModelStore()
        var shouldFail = true
        var attempts = 0
        val draft = DraftViewModel(fetchItems = { listOf(item) }, send = { name, _ ->
            if (name == "probeDraft") {
                attempts++
                if (shouldFail) error("Probe failed")
            }
        }, categoriesFlow = emptyFlow())
        store.put("draft", draft)
        try {
            draft.probe("one", "media")
            assertEquals("Probe failed", draft.state.value.probeErrors["one"]?.message)
            assertFalse("one" in draft.state.value.probing)
            shouldFail = false
            draft.probe("one", "media")
            assertEquals(2, attempts)
            assertTrue(draft.state.value.probeErrors.isEmpty())
        } finally { store.clear() }
    }

    @Test fun confirmFlushesLatestInputBeforeSubmittingAndDoesNotWaitForParsing() = runBlocking {
        var items = emptyList<DraftItem>()
        val calls = mutableListOf<String>()
        val store = ViewModelStore()
        val draft = DraftViewModel(fetchItems = { items }, send = { name, args ->
            calls += name
            if (name == "parse") items = listOf(DraftItem(url = args.single().toString()))
        }, categoriesFlow = emptyFlow())
        store.put("draft", draft)
        try {
            draft.setUrls("https://example.test/latest")
            assertTrue(draft.confirm())
            assertEquals(listOf("parse", "confirmDraft"), calls)
            assertTrue(draft.state.value.items.isEmpty())
            assertEquals("", draft.state.value.urls)
        } finally { store.clear() }
    }

    @Test fun removingUrlClearsItsPendingProbeIndicator() = runTest {
        Dispatchers.setMain(UnconfinedTestDispatcher(testScheduler))
        var items = listOf(DraftItem(url = "one", isParsing = false, canProbeMedia = true))
        val store = ViewModelStore()
        val draft = DraftViewModel(fetchItems = { items }, send = { name, _ ->
            if (name == "probeDraft") awaitCancellation()
            if (name == "parse") items = emptyList()
        }, categoriesFlow = emptyFlow())
        store.put("draft", draft)
        try {
            assertTrue("one" in draft.state.value.probing)
            draft.setUrls("")
            advanceTimeBy(1001)
            runCurrent()
            assertTrue(draft.state.value.items.isEmpty())
            assertTrue(draft.state.value.probing.isEmpty())
        } finally { store.clear() }
    }

    @Test fun categoryApplyReadsDestinationWithoutConfirmingOrStartingDraft() = runBlocking {
        var item = DraftItem(url = "one", isParsing = false, targetFolder = "/default")
        val calls = mutableListOf<Pair<String, List<Any>>>()
        val store = ViewModelStore()
        val draft = DraftViewModel(fetchItems = { listOf(item) }, send = { name, args ->
            calls.add(name to args)
            item = item.copy(categoryChoice = "video", categoryId = "video", targetFolder = "/default/Video")
        }, categoriesFlow = emptyFlow())
        store.put("draft", draft)
        try {
            assertTrue(draft.update("one", listOf(DraftChange("setCategory", listOf("video", false)))))
            assertEquals(listOf("setDraft" to listOf("one", "setCategory", "video", false)), calls)
            assertEquals("video", draft.state.value.items.single().categoryId)
            assertEquals("/default/Video", draft.state.value.items.single().targetFolder)
            assertFalse(draft.state.value.isWorking)
        } finally { store.clear() }
    }

    @Test fun failedCategoryApplyDoesNotPublishAnOptimisticDestination() = runBlocking {
        val item = DraftItem(url = "one", isParsing = false, targetFolder = "/default")
        val store = ViewModelStore()
        val draft = DraftViewModel(fetchItems = { listOf(item) }, send = { _, _ -> error("Save failed") }, categoriesFlow = emptyFlow())
        store.put("draft", draft)
        try {
            assertFalse(draft.update("one", listOf(DraftChange("setCategory", listOf("video", false)))))
            assertEquals(item, draft.state.value.items.single())
            assertEquals("Save failed", draft.state.value.error)
            assertFalse(draft.state.value.isWorking)
        } finally { store.clear() }
    }
}

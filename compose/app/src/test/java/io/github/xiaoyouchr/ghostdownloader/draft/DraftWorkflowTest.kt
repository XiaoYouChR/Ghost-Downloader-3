package com.xychr.ghostdownloader.draft

import androidx.lifecycle.ViewModelStore
import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.components.draft.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
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

    @Test fun sendPackRoutesProbeToSeparateEngineMethod() = runBlocking {
        val item = DraftItem(url = "one", isParsing = false)
        val calls = mutableListOf<Pair<String, List<Any>>>()
        val store = ViewModelStore()
        val draft = DraftViewModel(fetchItems = { listOf(item) }, send = { name, args ->
            calls.add(name to args)
        }, categoriesFlow = emptyFlow())
        store.put("draft", draft)
        try {
            draft.sendPack("one", "probe", listOf("media"))
            draft.sendPack("one", "setTrack", listOf("video", true))
            assertEquals("probeDraft", calls[0].first)
            assertEquals(listOf("one", "media"), calls[0].second)
            assertEquals("setDraft", calls[1].first)
            assertEquals(listOf("one", "setTrack", "video", true), calls[1].second)
        } finally { store.clear() }
    }
}

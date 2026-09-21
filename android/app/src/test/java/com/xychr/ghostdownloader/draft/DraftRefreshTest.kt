package com.xychr.ghostdownloader.draft

import androidx.lifecycle.ViewModelStore
import com.xychr.ghostdownloader.model.*
import com.xychr.ghostdownloader.ui.components.draft.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class DraftRefreshTest {
    @Before fun setMain() { Dispatchers.setMain(Dispatchers.Unconfined) }
    @After fun clearMain() { Dispatchers.resetMain() }

    @Test fun failedRefreshKeepsItemAndReportsOnPage() = runBlocking {
        val item = DraftItem(url = "one", isParsing = false)
        val store = ViewModelStore()
        val draft = DraftViewModel(
            send = { _, _ -> error("Refresh failed") },
            draftFlow = MutableStateFlow(DraftProjection(listOf(item))),
            categoriesFlow = emptyFlow(),
        )
        store.put("draft", draft)
        try {
            draft.refresh("one")
            assertEquals(item, draft.state.value.items.single())
            assertFalse(draft.state.value.error == null)
        } finally { store.clear() }
    }
}

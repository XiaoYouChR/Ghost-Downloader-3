package com.xychr.ghostdownloader.ui.settings

import androidx.lifecycle.ViewModelStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class SettingsEditTest {
    private val store = ViewModelStore()

    @After fun clear() { store.clear(); Dispatchers.resetMain() }

    @Test fun saveWaitsAndRejectsDuplicateSubmission() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val editor = SettingsEdit()
        store.put("edit", editor)
        val result = CompletableDeferred<Unit>()
        var writes = 0
        editor.save { writes++; result.await() }
        editor.save { writes++ }
        assertTrue(editor.state.value.isSaving)
        runCurrent()
        assertEquals(1, writes)
        assertFalse(editor.state.value.isSaved)
        result.complete(Unit)
        runCurrent()
        assertEquals(SettingsEditState(isSaved = true), editor.state.value)
        editor.save { writes++ }
        runCurrent()
        assertEquals(1, writes)
    }

    @Test fun failedSaveCanBeRetriedExplicitly() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val editor = SettingsEdit()
        store.put("edit", editor)
        editor.save { error("disk full") }
        runCurrent()
        assertEquals(SettingsEditState(hasError = true), editor.state.value)
        editor.save { }
        runCurrent()
        assertEquals(SettingsEditState(isSaved = true), editor.state.value)
    }

    @Test fun cancellationDoesNotBecomeSuccessOrTrapEditor() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val editor = SettingsEdit()
        store.put("edit", editor)
        editor.save { throw CancellationException() }
        runCurrent()
        assertEquals(SettingsEditState(), editor.state.value)
    }
}

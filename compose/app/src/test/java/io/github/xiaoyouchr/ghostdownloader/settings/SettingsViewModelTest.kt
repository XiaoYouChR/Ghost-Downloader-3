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
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.After
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class SettingsViewModelTest {
    private val store = ViewModelStore()

    @After fun clear() {
        store.clear()
        Dispatchers.resetMain()
    }

    @Test fun loadFailureCanBeRetried() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        var shouldFail = true
        val model = SettingsViewModel(loadConfig = {
            if (shouldFail) error("offline")
            buildJsonObject { put("maxTaskNum", 3) }
        }, saveSetting = { _, _ -> })
        store.put("settings", model)
        runCurrent()
        assertEquals(SettingsUiState.Error(SettingsFailure.LOAD), model.uiState.value)
        shouldFail = false
        model.load()
        runCurrent()
        assertEquals(3, (model.uiState.value as SettingsUiState.Success).settings.maxTaskNum)
    }

    @Test fun saveFailureReloadsWithoutRepeatingWrite() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        var writes = 0
        val model = SettingsViewModel(loadConfig = { buildJsonObject { put("maxTaskNum", 3) } },
            saveSetting = { _, _ -> writes++; error("disk full") })
        store.put("settings", model)
        runCurrent()
        model.set("maxTaskNum", 4)
        runCurrent()
        assertEquals(SettingsUiState.Error(SettingsFailure.SAVE), model.uiState.value)
        model.load()
        runCurrent()
        assertEquals(1, writes)
        assertEquals(3, (model.uiState.value as SettingsUiState.Success).settings.maxTaskNum)
    }

    @Test fun savedButUnreadableIsNotReportedAsFailedWrite() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        var isSaved = false
        val model = SettingsViewModel(loadConfig = {
            if (isSaved) error("read failed")
            buildJsonObject { put("maxTaskNum", 3) }
        }, saveSetting = { _, _ -> isSaved = true })
        store.put("settings", model)
        runCurrent()
        model.set("maxTaskNum", 4)
        runCurrent()
        assertEquals(SettingsUiState.Error(SettingsFailure.RELOAD), model.uiState.value)
    }

    @Test fun savingIsSingleFlightAndReturnsAuthoritativeValue() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val gate = CompletableDeferred<Unit>()
        var value = 3
        var writes = 0
        val model = SettingsViewModel(loadConfig = { buildJsonObject { put("maxTaskNum", value) } },
            saveSetting = { _, input -> writes++; gate.await(); value = input as Int })
        store.put("settings", model)
        runCurrent()
        model.set("maxTaskNum", 4)
        assertTrue((model.uiState.value as SettingsUiState.Success).isSaving)
        model.set("maxTaskNum", 5)
        model.load()
        runCurrent()
        assertEquals(1, writes)
        gate.complete(Unit)
        runCurrent()
        val result = model.uiState.value as SettingsUiState.Success
        assertFalse(result.isSaving)
        assertEquals(4, result.settings.maxTaskNum)
    }

    @Test fun cancellationDoesNotBecomeSaveFailure() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val model = SettingsViewModel(loadConfig = { buildJsonObject {} },
            saveSetting = { _, _ -> throw CancellationException("cancelled") })
        store.put("settings", model)
        runCurrent()
        model.set("maxTaskNum", 4)
        runCurrent()
        assertFalse((model.uiState.value as SettingsUiState.Success).isSaving)
    }
}

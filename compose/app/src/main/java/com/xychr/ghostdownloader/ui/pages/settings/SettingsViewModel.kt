package com.xychr.ghostdownloader.ui.pages.settings

import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.model.Settings
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.decodeFromJsonElement

private val settingsJson = Json { ignoreUnknownKeys = true }

class SettingsViewModel : ViewModel() {

    val config: StateFlow<JsonObject?> =
        EngineRepository.observe<JsonObject>("settings")
            .stateIn(viewModelScope, SharingStarted.Eagerly, null)

    val settings: StateFlow<Settings?> = config
        .map { it?.let { settingsJson.decodeFromJsonElement<Settings>(it) } }
        .stateIn(viewModelScope, SharingStarted.Eagerly, null)

    fun set(name: String, value: Any) {
        viewModelScope.launch {
            EngineRepository.invoke("setSetting", name, value)
        }
    }
}

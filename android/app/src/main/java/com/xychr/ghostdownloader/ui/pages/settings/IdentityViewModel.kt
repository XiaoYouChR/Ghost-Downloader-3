package com.xychr.ghostdownloader.ui.pages.settings

import com.xychr.ghostdownloader.bridge.bridge
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

@Serializable
data class IdentityPreset(
    val name: String = "",
    val clientProfile: String = "",
    val userAgent: String = "",
    val hosts: List<String> = emptyList(),
    val isEnabled: Boolean = true,
)

@Serializable
data class HeadersPreset(
    val name: String = "",
    val headers: Map<String, String> = emptyMap(),
)

@Serializable
data class ClientProfiles(val family: String, val versions: List<String>)

@Serializable
data class IdentityState(
    val clientProfile: String = "auto",
    val identityPresets: List<IdentityPreset> = emptyList(),
    val headersPresets: List<HeadersPreset> = emptyList(),
    val currentHeadersPreset: Int = 0,
)

data class IdentityUiState(
    val identity: IdentityState,
    val profiles: List<ClientProfiles>,
    val defaultHeaders: Map<String, String>,
)

class IdentityViewModel : ViewModel() {

    private val _profiles = MutableStateFlow<List<ClientProfiles>?>(null)
    private val _defaults = MutableStateFlow<Map<String, String>?>(null)

    val state: StateFlow<IdentityUiState?> = combine(
        bridge.observe<IdentityState>("settings"),
        _profiles,
        _defaults,
    ) { identity, profiles, defaults ->
        if (profiles != null && defaults != null) IdentityUiState(identity, profiles, defaults)
        else null
    }.stateIn(viewModelScope, SharingStarted.Eagerly, null)

    private val _isBusy = MutableStateFlow(false)
    val isBusy = _isBusy.asStateFlow()

    init {
        viewModelScope.launch {
            _profiles.value = bridge.query("clientProfiles")
            _defaults.value = bridge.query("defaultHeaders")
        }
    }

    suspend fun setClientProfile(profile: String) {
        bridge.invoke("setSetting", "clientProfile", profile)
    }

    fun setActiveHeadersPreset(index: Int) = write {
        bridge.invoke("setSetting", "currentHeadersPreset", index)
    }

    suspend fun addIdentityPreset(preset: IdentityPreset) {
        bridge.invoke("addIdentityPreset", bridge.encode(preset))
    }

    suspend fun updateIdentityPreset(index: Int, preset: IdentityPreset) {
        bridge.invoke("updateIdentityPreset", index, bridge.encode(preset))
    }

    fun setIdentityEnabled(index: Int, isEnabled: Boolean) = write {
        val presets = state.value?.identity?.identityPresets ?: return@write
        updateIdentityPreset(index, presets[index].copy(isEnabled = isEnabled))
    }

    fun setIdentityOrder(index: Int, target: Int) = write {
        bridge.invoke("setIdentityOrder", index, target)
    }

    fun removeIdentityPreset(index: Int) = write {
        bridge.invoke("removeIdentityPreset", index)
    }

    suspend fun addHeadersPreset(preset: HeadersPreset) {
        bridge.invoke("addHeadersPreset", bridge.encode(preset))
    }

    suspend fun updateHeadersPreset(index: Int, preset: HeadersPreset) {
        bridge.invoke("updateHeadersPreset", index, bridge.encode(preset))
    }

    fun removeHeadersPreset(index: Int) = write {
        val identity = state.value?.identity ?: return@write
        val current = identity.currentHeadersPreset
        if (identity.headersPresets.size <= 1) return@write
        bridge.invoke("removeHeadersPreset", index)
        bridge.invoke("setSetting", "currentHeadersPreset", when {
            index < current -> current - 1
            index == current -> 0
            else -> current
        })
    }

    private fun write(block: suspend () -> Unit) {
        if (_isBusy.value) return
        _isBusy.value = true
        viewModelScope.launch {
            try {
                block()
            } catch (e: CancellationException) { throw e }
            catch (_: Exception) { }
            finally { _isBusy.value = false }
        }
    }
}

package com.xychr.ghostdownloader.ui.pages.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.xychr.ghostdownloader.engine.engineRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.takeWhile
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

@Serializable
data class UpdateAvailable(val version: String = "", val releaseUrl: String = "")

@Serializable
data class UpdateCheck(val status: String = "latest")

@Serializable
data class UpdateDownloadState(
    val state: String = "idle",
    val progress: Double = 0.0,
    val filePath: String = "",
    val error: String = "",
)

enum class CheckState { CHECKING, LATEST, NO_ASSET, FAILED }

class UpdateViewModel(
    private val loadIgnoredVersion: () -> String?,
    private val saveIgnoredVersion: (String) -> Unit,
) : ViewModel() {

    private val _checkState = MutableStateFlow<CheckState?>(null)
    val checkState: StateFlow<CheckState?> = _checkState.asStateFlow()

    private val _downloadState = MutableStateFlow(UpdateDownloadState())
    val downloadState: StateFlow<UpdateDownloadState> = _downloadState.asStateFlow()

    private val _ignoredVersion = MutableStateFlow(loadIgnoredVersion())

    val available: StateFlow<UpdateAvailable?> =
        engineRepository.observe<UpdateAvailable?>("updateAvailable")
            .stateIn(viewModelScope, SharingStarted.Eagerly, null)

    val updateNotice: StateFlow<UpdateAvailable?> =
        combine(available, _ignoredVersion) { update, ignored ->
            update?.takeIf { it.version != ignored }
        }.stateIn(viewModelScope, SharingStarted.Eagerly, null)

    init {
        viewModelScope.launch {
            val s = runCatching { engineRepository.query<UpdateDownloadState>("updateState") }
                .getOrNull() ?: return@launch
            if (s.state != "idle") {
                _downloadState.value = s
                if (s.state == "downloading") collectDownloadState()
            }
        }
    }

    fun check() {
        if (_checkState.value == CheckState.CHECKING) return
        _checkState.value = CheckState.CHECKING
        viewModelScope.launch {
            _checkState.value = try {
                when (engineRepository.query<UpdateCheck>("checkUpdate").status) {
                    "available" -> null
                    "no_asset" -> CheckState.NO_ASSET
                    else -> CheckState.LATEST
                }
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                CheckState.FAILED
            }
        }
    }

    fun download() {
        _downloadState.value = UpdateDownloadState(state = "downloading")
        viewModelScope.launch {
            engineRepository.invoke("downloadUpdate", "app")
            collectDownloadState()
        }
    }

    fun ignore() {
        val version = available.value?.version ?: return
        _ignoredVersion.value = version
        saveIgnoredVersion(version)
    }

    private suspend fun collectDownloadState() {
        engineRepository.observe<UpdateDownloadState>("updateState")
            .filter { it.state != "idle" }
            .takeWhile { it.state == "downloading" }
            .collect { _downloadState.value = it }
        _downloadState.value = runCatching { engineRepository.query<UpdateDownloadState>("updateState") }
            .getOrDefault(_downloadState.value)
    }
}

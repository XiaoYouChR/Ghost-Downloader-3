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
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

@Serializable
data class UpdateAvailable(
    val version: String = "",
    val releaseUrl: String = "",
    val publishedAt: String = "",
    val prerelease: Boolean = false,
)

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

    val downloadState: StateFlow<UpdateDownloadState> =
        engineRepository.observe<UpdateDownloadState>("updateState")
            .stateIn(viewModelScope, SharingStarted.Eagerly, UpdateDownloadState())

    private val _ignoredVersion = MutableStateFlow(loadIgnoredVersion())

    val available: StateFlow<UpdateAvailable?> =
        engineRepository.observe<UpdateAvailable?>("updateAvailable")
            .stateIn(viewModelScope, SharingStarted.Eagerly, null)

    val updateNotice: StateFlow<UpdateAvailable?> =
        combine(available, _ignoredVersion) { update, ignored ->
            update?.takeIf { it.version != ignored }
        }.stateIn(viewModelScope, SharingStarted.Eagerly, null)

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
        viewModelScope.launch {
            engineRepository.invoke("downloadUpdate", "app")
        }
    }

    fun ignore() {
        val version = available.value?.version ?: return
        _ignoredVersion.value = version
        saveIgnoredVersion(version)
    }
}

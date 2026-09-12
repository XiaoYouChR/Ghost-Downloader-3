package com.xychr.ghostdownloader.ui.pages.settings

import com.xychr.ghostdownloader.engine.EngineRepository
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.InfoSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage
import com.xychr.ghostdownloader.model.TaskError
import com.xychr.ghostdownloader.i18n.engineText
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

@Serializable
data class RuntimeUiState(
    val id: String = "",
    val title: String = "",
    val description: String = "",
    val canInstall: Boolean = false,
    val isInstalled: Boolean = false,
    val isBusy: Boolean = false,
    val isInstalling: Boolean = false,
    val progress: Double = 0.0,
    val version: String = "",
    val detail: String = "",
    val latestVersion: String = "",
    val error: TaskError? = null,
)

class RuntimesViewModel : ViewModel() {

    private val _runtimes = MutableStateFlow<List<RuntimeUiState>>(emptyList())
    val runtimes: StateFlow<List<RuntimeUiState>> = _runtimes.asStateFlow()

    private var pollJob: Job? = null

    init {
        viewModelScope.launch { EngineRepository.invoke("refreshRuntimes") }
        poll()
    }

    fun install(id: String) {
        viewModelScope.launch {
            EngineRepository.invoke("installRuntime", id)
            poll()
        }
    }

    fun cancelInstall(id: String) {
        viewModelScope.launch { EngineRepository.invoke("cancelRuntimeInstall", id) }
    }

    /** 安装和检查都是引擎自己推进的，所以只在有活儿时轮询，全部空闲就停 */
    private fun poll() {
        pollJob?.cancel()
        pollJob = viewModelScope.launch {
            while (isActive) {
                val list = runCatching { EngineRepository.query<List<RuntimeUiState>>("runtimes") }
                    .getOrNull()
                if (list != null) _runtimes.value = list
                delay(1000)
                if (list != null && list.none { it.isBusy || it.isInstalling }) break
            }
        }
    }
}

@Composable
fun RuntimesPage(onBack: () -> Unit, viewModel: RuntimesViewModel = viewModel()) {
    val runtimes by viewModel.runtimes.collectAsStateWithLifecycle()

    SettingsPage(stringResource(R.string.settings_section_runtimes), onBack) {
        SettingSection {
            runtimes.forEach { runtime ->
                RuntimeRow(
                    runtime = runtime,
                    onInstall = { viewModel.install(runtime.id) },
                    onCancel = { viewModel.cancelInstall(runtime.id) },
                )
            }
        }
    }
}

@Composable
private fun RuntimeRow(runtime: RuntimeUiState, onInstall: () -> Unit, onCancel: () -> Unit) {
    val hasUpdate = runtime.latestVersion.isNotEmpty() && runtime.latestVersion != runtime.version

    InfoSettingRow(
        title = engineText(runtime.title, emptyMap()),
        subtitle = runtimeStatusText(runtime),
        trailing = when {
            runtime.isInstalling -> {
                { TextButton(onCancel) { Text(stringResource(R.string.action_cancel)) } }
            }

            !runtime.canInstall -> null

            !runtime.isInstalled -> {
                { TextButton(onInstall) { Text(stringResource(R.string.runtime_install)) } }
            }

            hasUpdate -> {
                { TextButton(onInstall) { Text(stringResource(R.string.runtime_update)) } }
            }

            else -> null
        },
    )
}

@Composable
private fun runtimeStatusText(runtime: RuntimeUiState): String = when {
    runtime.isInstalling ->
        stringResource(R.string.runtime_installing, runtime.progress.toInt())

    runtime.error != null -> engineText(runtime.error.message, runtime.error.params)

    runtime.isBusy -> stringResource(R.string.runtime_checking)

    !runtime.isInstalled ->
        if (runtime.canInstall) stringResource(R.string.runtime_not_installed)
        else engineText(runtime.description, emptyMap())

    else -> listOf(
        runtime.version.ifEmpty {
            if (runtime.canInstall) "" else stringResource(R.string.runtime_bundled)
        },
        runtime.detail,
        runtime.latestVersion.takeIf { it.isNotEmpty() && it != runtime.version }
            ?.let { "→ $it" }.orEmpty(),
    ).filter(String::isNotEmpty).joinToString("  ")
}

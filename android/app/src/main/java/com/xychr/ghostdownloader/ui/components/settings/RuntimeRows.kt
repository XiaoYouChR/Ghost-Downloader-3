package com.xychr.ghostdownloader.ui.components.settings

import androidx.compose.foundation.layout.size
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.model.TaskError
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
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

    val runtimes: StateFlow<List<RuntimeUiState>> =
        engineRepository.observe<List<RuntimeUiState>>("runtimes")
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    init { refresh() }

    fun install(id: String) {
        viewModelScope.launch { engineRepository.invoke("installRuntime", id) }
    }

    fun cancelInstall(id: String) {
        viewModelScope.launch { engineRepository.invoke("cancelRuntimeInstall", id) }
    }

    fun refresh() {
        viewModelScope.launch { engineRepository.invoke("refreshRuntimes") }
    }
}

@Composable
fun RuntimeRows(viewModel: RuntimesViewModel = viewModel()) {
    val runtimes by viewModel.runtimes.collectAsStateWithLifecycle()

    runtimes.forEach { runtime ->
        RuntimeRow(
            runtime = runtime,
            onInstall = { viewModel.install(runtime.id) },
            onCancel = { viewModel.cancelInstall(runtime.id) },
            onRetry = { viewModel.refresh() },
        )
    }
}

@Composable
private fun RuntimeRow(
    runtime: RuntimeUiState,
    onInstall: () -> Unit,
    onCancel: () -> Unit,
    onRetry: () -> Unit,
) {
    val hasUpdate = runtime.latestVersion.isNotEmpty() && runtime.latestVersion != runtime.version

    InfoSettingRow(
        title = engineText(runtime.title, emptyMap()),
        subtitle = runtimeStatusText(runtime),
        trailing = when {
            runtime.isInstalling -> {
                { TextButton(onCancel) { Text(stringResource(R.string.action_cancel)) } }
            }

            runtime.isBusy -> {
                { CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp) }
            }

            runtime.error != null -> {
                { TextButton(onRetry) { Text(stringResource(R.string.runtime_retry)) } }
            }

            !runtime.canInstall -> null

            !runtime.isInstalled || hasUpdate -> {
                val label = if (runtime.isInstalled) R.string.runtime_update else R.string.runtime_install
                { FilledTonalButton(onInstall) { Text(stringResource(label)) } }
            }

            else -> null
        },
        footer = if (runtime.isInstalling) {
            { LinearProgressIndicator(progress = { (runtime.progress / 100.0).toFloat() }) }
        } else null,
    )
}

@Composable
private fun runtimeStatusText(runtime: RuntimeUiState): String = when {
    runtime.isInstalling -> stringResource(R.string.runtime_installing)

    runtime.error != null -> engineText(runtime.error)

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

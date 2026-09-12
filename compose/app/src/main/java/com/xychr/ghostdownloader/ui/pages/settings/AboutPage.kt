package com.xychr.ghostdownloader.ui.pages.settings

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.core.net.toUri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.InfoSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage
import com.xychr.ghostdownloader.engine.EngineRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.takeWhile
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import java.io.File

private const val REPOSITORY_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3"

@Serializable
data class UpdateCheckResult(
    val available: Boolean = false,
    val currentVersion: String = "",
    val latestVersion: String = "",
    val assetName: String = "",
    val assetSize: Long = 0,
    val releaseNotes: String = "",
    val releaseUrl: String = "",
)

@Serializable
data class UpdateDownloadState(
    val state: String = "idle",
    val progress: Double = 0.0,
    val filePath: String = "",
    val error: String = "",
)

enum class CheckState { IDLE, CHECKING, AVAILABLE, LATEST, FAILED }

class UpdateViewModel : ViewModel() {
    private val _checkState = MutableStateFlow(CheckState.IDLE)
    val checkState: StateFlow<CheckState> = _checkState.asStateFlow()

    private val _result = MutableStateFlow(UpdateCheckResult())
    val result: StateFlow<UpdateCheckResult> = _result.asStateFlow()

    private val _downloadState = MutableStateFlow(UpdateDownloadState())
    val downloadState: StateFlow<UpdateDownloadState> = _downloadState.asStateFlow()

    init {
        viewModelScope.launch {
            val s = runCatching { EngineRepository.query<UpdateDownloadState>("updateState") }
                .getOrNull() ?: return@launch
            if (s.state != "idle") {
                _downloadState.value = s
                if (s.state == "downloading") collectDownloadState()
            }
        }
    }

    fun check() {
        _checkState.value = CheckState.CHECKING
        viewModelScope.launch {
            try {
                val r = EngineRepository.query<UpdateCheckResult>("checkUpdate")
                _result.value = r
                _checkState.value = if (r.available) CheckState.AVAILABLE else CheckState.LATEST
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                _checkState.value = CheckState.FAILED
            }
        }
    }

    fun download() {
        _downloadState.value = UpdateDownloadState(state = "downloading")
        viewModelScope.launch {
            EngineRepository.invoke("downloadUpdate", "app")
            collectDownloadState()
        }
    }

    private suspend fun collectDownloadState() {
        EngineRepository.observe<UpdateDownloadState>("updateState")
            .filter { it.state != "idle" }
            .takeWhile { it.state == "downloading" }
            .collect { _downloadState.value = it }
        _downloadState.value = runCatching { EngineRepository.query<UpdateDownloadState>("updateState") }
            .getOrDefault(_downloadState.value)
    }
}

@Composable
fun AboutPage(onBack: () -> Unit, viewModel: UpdateViewModel = viewModel()) {
    val context = LocalContext.current
    val version = remember {
        context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: ""
    }
    val checkState by viewModel.checkState.collectAsStateWithLifecycle()
    val result by viewModel.result.collectAsStateWithLifecycle()
    val dlState by viewModel.downloadState.collectAsStateWithLifecycle()

    SettingsPage(stringResource(R.string.settings_section_about), onBack) {
        SettingSection {
            InfoSettingRow(
                title = stringResource(R.string.settings_version),
                subtitle = version,
            )
            ActionSettingRow(
                title = stringResource(R.string.settings_source_code),
                subtitle = REPOSITORY_URL,
                onClick = {
                    context.startActivity(
                        Intent(Intent.ACTION_VIEW, REPOSITORY_URL.toUri())
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    )
                },
            )
        }

        Spacer(Modifier.height(8.dp))
        UpdateSection(context, checkState, result, dlState, viewModel)
    }
}

@Composable
private fun UpdateSection(
    context: Context,
    checkState: CheckState,
    result: UpdateCheckResult,
    dlState: UpdateDownloadState,
    viewModel: UpdateViewModel,
) {
    SettingSection {
        when {
            dlState.state == "downloading" -> {
                InfoSettingRow(
                    title = stringResource(R.string.settings_update_downloading, dlState.progress.toInt()),
                )
            }

            dlState.state == "ready" -> {
                ActionSettingRow(
                    title = stringResource(R.string.settings_update_install),
                    subtitle = result.latestVersion,
                    onClick = { context.installApk(File(dlState.filePath)) },
                )
            }

            dlState.state == "failed" -> {
                ActionSettingRow(
                    title = stringResource(R.string.settings_update_download_failed),
                    subtitle = dlState.error,
                    onClick = { viewModel.download() },
                )
            }

            checkState == CheckState.CHECKING -> {
                InfoSettingRow(
                    title = stringResource(R.string.settings_checking_update),
                )
            }

            checkState == CheckState.AVAILABLE -> {
                ActionSettingRow(
                    title = stringResource(R.string.settings_update_available, result.latestVersion),
                    subtitle = result.assetName,
                    onClick = { viewModel.download() },
                )
            }

            checkState == CheckState.LATEST -> {
                InfoSettingRow(
                    title = stringResource(R.string.settings_update_latest),
                )
            }

            checkState == CheckState.FAILED -> {
                ActionSettingRow(
                    title = stringResource(R.string.settings_update_failed),
                    onClick = { viewModel.check() },
                )
            }

            else -> {
                ActionSettingRow(
                    title = stringResource(R.string.settings_check_update),
                    onClick = { viewModel.check() },
                )
            }
        }
    }
}

private fun Context.installApk(file: File) {
    val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
    val intent = Intent(Intent.ACTION_VIEW).apply {
        setDataAndType(uri, "application/vnd.android.package-archive")
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }
    startActivity(intent)
}

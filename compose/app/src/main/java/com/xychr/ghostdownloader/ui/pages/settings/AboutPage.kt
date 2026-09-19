package com.xychr.ghostdownloader.ui.pages.settings

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.InfoSettingRow
import com.xychr.ghostdownloader.ui.components.settings.ReleaseInfoSheet
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsScaffold
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.navigation.PackInfoRoute
import com.xychr.ghostdownloader.ui.navigation.PermissionsSettingsRoute
import com.xychr.ghostdownloader.ui.navigation.Route
import com.xychr.ghostdownloader.ui.platform.openUrl
import com.xychr.ghostdownloader.ui.platform.start
import java.io.File

private const val REPOSITORY_URL = "https://github.com/XiaoYouChR/Ghost-Downloader-3"

@Composable
fun AboutPage(
    onNavigate: (Route) -> Unit,
    onBack: () -> Unit,
    viewModel: SettingsViewModel,
    updateViewModel: UpdateViewModel,
) {
    val context = LocalContext.current
    val version = remember {
        context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: ""
    }
    val settings by viewModel.settings.collectAsStateWithLifecycle()
    val checkState by updateViewModel.checkState.collectAsStateWithLifecycle()
    val available by updateViewModel.available.collectAsStateWithLifecycle()
    val dlState by updateViewModel.downloadState.collectAsStateWithLifecycle()

    SettingsScaffold(stringResource(R.string.settings_section_about), onBack) {
        SettingSection {
            InfoSettingRow(
                title = stringResource(R.string.settings_version),
                subtitle = version,
            )
            ActionSettingRow(
                title = stringResource(R.string.settings_source_code),
                subtitle = REPOSITORY_URL,
                onClick = { context.openUrl(REPOSITORY_URL) },
            )
            ActionSettingRow(
                title = stringResource(R.string.settings_pack_info),
                onClick = { onNavigate(PackInfoRoute) },
            )
        }

        SettingSection {
            settings?.let {
                SwitchSettingRow(
                    title = stringResource(R.string.settings_check_update_at_startup),
                    subtitle = stringResource(R.string.settings_check_update_at_startup_desc),
                    checked = it.shouldCheckUpdateAtStartup,
                    onCheckedChange = { checked -> viewModel.set("shouldCheckUpdateAtStartup", checked) },
                )
            }
        }

        Spacer(Modifier.height(8.dp))
        UpdateSection(context, checkState, available, dlState, updateViewModel, onNavigate)
    }
}

@Composable
private fun UpdateSection(
    context: Context,
    checkState: CheckState?,
    available: UpdateAvailable?,
    dlState: UpdateDownloadState,
    viewModel: UpdateViewModel,
    onNavigate: (Route) -> Unit,
) {
    var installFailed by remember { mutableStateOf(false) }
    var showReleaseInfo by remember { mutableStateOf(false) }

    SettingSection {
        when {
            dlState.state == "downloading" -> {
                InfoSettingRow(title = stringResource(R.string.settings_update_downloading, dlState.progress.toInt()))
                LinearProgressIndicator(
                    progress = { (dlState.progress / 100).toFloat() },
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                )
            }

            dlState.state == "ready" -> {
                ActionSettingRow(
                    title = stringResource(R.string.settings_update_install),
                    subtitle = available?.version ?: dlState.filePath.substringAfterLast('/'),
                    onClick = {
                        installFailed = !context.installApk(File(dlState.filePath))
                    },
                )
                if (installFailed) {
                    ActionSettingRow(
                        title = stringResource(R.string.settings_update_install_failed),
                        colors = ListItemDefaults.segmentedColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer,
                        ),
                        onClick = { onNavigate(PermissionsSettingsRoute) },
                    )
                }
            }

            dlState.state == "failed" -> {
                ActionSettingRow(
                    title = stringResource(R.string.settings_update_download_failed),
                    subtitle = dlState.error,
                    onClick = { viewModel.download() },
                )
            }

            available != null -> {
                ActionSettingRow(
                    title = stringResource(R.string.settings_update_available, available.version),
                    subtitle = stringResource(R.string.settings_update_notes),
                    onClick = { showReleaseInfo = true },
                )
                ActionSettingRow(
                    title = stringResource(R.string.settings_update_install),
                    onClick = { viewModel.download() },
                )
                ActionSettingRow(
                    title = stringResource(R.string.settings_update_ignore),
                    onClick = { viewModel.ignore() },
                )
            }

            checkState == CheckState.CHECKING -> InfoSettingRow(title = stringResource(R.string.settings_checking_update))

            checkState == CheckState.LATEST -> InfoSettingRow(title = stringResource(R.string.settings_update_latest))

            checkState == CheckState.NO_ASSET -> InfoSettingRow(title = stringResource(R.string.settings_update_no_asset))

            checkState == CheckState.FAILED -> ActionSettingRow(
                title = stringResource(R.string.settings_update_failed),
                onClick = { viewModel.check() },
            )

            else -> ActionSettingRow(
                title = stringResource(R.string.settings_check_update),
                onClick = { viewModel.check() },
            )
        }
    }

    if (showReleaseInfo && available != null) {
        ReleaseInfoSheet(
            available = available,
            onDismiss = { showReleaseInfo = false },
            onDownload = { viewModel.download() },
            onOpenInBrowser = { context.openUrl(available.releaseUrl) },
        )
    }
}

private fun Context.installApk(file: File): Boolean = runCatching {
    val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
    val intent = Intent(Intent.ACTION_VIEW).apply {
        setDataAndType(uri, "application/vnd.android.package-archive")
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }
    startActivity(intent)
}.isSuccess

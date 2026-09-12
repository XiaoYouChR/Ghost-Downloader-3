package com.xychr.ghostdownloader.ui.pages.settings

import android.net.Uri
import android.os.Environment
import android.provider.DocumentsContract
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.model.Settings
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.NumberSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage
import com.xychr.ghostdownloader.ui.components.settings.SliderSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.navigation.*

@Composable
fun DownloadPage(
    onNavigate: (Route) -> Unit,
    onBack: () -> Unit,
    viewModel: SettingsViewModel,
) {
    val settings by viewModel.settings.collectAsStateWithLifecycle()

    SettingsPage(stringResource(R.string.settings_section_download), onBack) {
        settings?.let { DownloadRows(it, viewModel::set, onNavigate) } ?: LoadingRow()
    }
}

@Composable
private fun ColumnScope.DownloadRows(
    settings: Settings,
    set: (String, Any) -> Unit,
    onNavigate: (Route) -> Unit,
) {
    val folderPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocumentTree()
    ) { uri -> uri?.let { set("downloadFolder", it.toFolderPath()) } }

    SettingSection {
        ActionSettingRow(
            title = stringResource(R.string.settings_download_folder),
            subtitle = settings.downloadFolder,
            onClick = { folderPicker.launch(null) },
            trailing = {
                IconButton(onClick = { set("downloadFolder", defaultDownloadFolder()) }) {
                    Icon(
                        painterResource(R.drawable.ic_restore),
                        contentDescription = stringResource(R.string.settings_restore_default),
                    )
                }
            },
        )
        SliderSettingRow(
            title = stringResource(R.string.settings_max_task_num),
            value = settings.maxTaskNum,
            range = 1..10,
            valueText = { it.toString() },
            onCommit = { set("maxTaskNum", it) },
        )
        SliderSettingRow(
            title = stringResource(R.string.settings_pre_block_num),
            value = settings.preBlockNum,
            range = 1..256,
            valueText = { it.toString() },
            onCommit = { set("preBlockNum", it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.settings_auto_speed_up),
            subtitle = stringResource(R.string.settings_auto_speed_up_desc),
            checked = settings.autoSpeedUp,
            onCheckedChange = { set("autoSpeedUp", it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.settings_speed_limit_enabled),
            checked = settings.isSpeedLimitEnabled,
            onCheckedChange = { set("isSpeedLimitEnabled", it) },
        )
        NumberSettingRow(
            title = stringResource(R.string.settings_reassign_size),
            value = settings.maxReassignSize,
            range = 64..102400,
            unit = "KB",
            onConfirm = { set("maxReassignSize", it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.settings_preserve_modified),
            subtitle = stringResource(R.string.settings_preserve_modified_desc),
            checked = settings.shouldPreserveLastModified,
            onCheckedChange = { set("shouldPreserveLastModified", it) },
        )
        if (settings.isSpeedLimitEnabled) {
            NumberSettingRow(
                title = stringResource(R.string.settings_speed_limit),
                value = settings.speedLimitation / 1024,
                range = 1..102400,
                unit = "KB/s",
                onConfirm = { set("speedLimitation", it * 1024) },
            )
        }
        SwitchSettingRow(
            title = stringResource(R.string.settings_delete_files_on_remove),
            checked = settings.shouldDeleteFilesOnRemove,
            onCheckedChange = { set("shouldDeleteFilesOnRemove", it) },
        )
    }

    SettingSection {
        ActionSettingRow(
            title = stringResource(R.string.category_manage),
            onClick = { onNavigate(CategorySettingsRoute()) },
        )
    }

}

private fun defaultDownloadFolder(): String =
    Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).absolutePath

// SAF content:// → 裸路径；引擎走 java.io.File，写盘靠 MANAGE_EXTERNAL_STORAGE。
fun Uri.toFolderPath(): String {
    val documentId = DocumentsContract.getTreeDocumentId(this)
    val volume = documentId.substringBefore(':')
    val relative = documentId.substringAfter(':', "")
    val base = if (volume == "primary") "/storage/emulated/0" else "/storage/$volume"
    return if (relative.isEmpty()) base else "$base/$relative"
}

package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.SettingRanges
import com.xychr.ghostdownloader.model.Settings
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.NumberSettingRow
import com.xychr.ghostdownloader.ui.components.settings.PathSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsScaffold
import com.xychr.ghostdownloader.ui.components.settings.SliderSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.platform.defaultDownloadFolder
import com.xychr.ghostdownloader.ui.platform.rememberFolderPicker

@Composable
fun DownloadPage(
    onBack: () -> Unit,
    viewModel: SettingsViewModel,
) {
    val settings by viewModel.settings.collectAsStateWithLifecycle()

    SettingsScaffold(stringResource(R.string.settings_section_download), onBack) {
        settings?.let { DownloadRows(it, viewModel::set) } ?: LoadingRow()
    }
}

@Composable
private fun ColumnScope.DownloadRows(
    settings: Settings,
    set: (String, Any) -> Unit,
) {
    val picker = rememberFolderPicker { set("downloadFolder", it) }

    SettingSection {
        PathSettingRow(
            title = stringResource(R.string.settings_download_folder),
            path = settings.downloadFolder,
            picker = picker,
            onReset = { set("downloadFolder", defaultDownloadFolder()) },
        )
        SliderSettingRow(
            title = stringResource(R.string.settings_max_task_num),
            value = settings.maxTaskNum,
            range = SettingRanges["maxTaskNum"],
            valueText = { it.toString() },
            onCommit = { set("maxTaskNum", it) },
        )
        SliderSettingRow(
            title = stringResource(R.string.settings_pre_block_num),
            value = settings.preBlockNum,
            range = SettingRanges["preBlockNum"],
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
            range = SettingRanges["maxReassignSize"],
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
            val limit = SettingRanges["speedLimitation"]
            NumberSettingRow(
                title = stringResource(R.string.settings_speed_limit),
                value = settings.speedLimitation / 1024,
                range = limit.first / 1024..limit.last / 1024,
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
}


package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.NumberSettingRow
import com.xychr.ghostdownloader.ui.components.settings.OptionsSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SliderSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.components.settings.TextSettingRow
import kotlinx.serialization.json.JsonObject

@Composable
fun BitTorrentSettings(config: JsonObject, k: PackKeys, set: (String, Any) -> Unit) {
    val auto = stringResource(R.string.value_auto)
    val unlimited = stringResource(R.string.value_unlimited)

    SettingSection(title = stringResource(R.string.bt_section_network)) {
        SwitchSettingRow(
            title = stringResource(R.string.bt_enable_dht),
            subtitle = stringResource(R.string.bt_enable_dht_desc),
            checked = config.bool(k("enableDht")),
            onCheckedChange = { set(k("enableDht"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.bt_enable_lsd),
            subtitle = stringResource(R.string.bt_enable_lsd_desc),
            checked = config.bool(k("enableLsd")),
            onCheckedChange = { set(k("enableLsd"), it) },
        )
        NumberSettingRow(
            title = stringResource(R.string.bt_listen_port),
            value = config.int(k("listenPort")),
            range = 0..65535,
            onConfirm = { set(k("listenPort"), it) },
            valueText = { if (it == 0) auto else "$it" },
        )
        SliderSettingRow(
            title = stringResource(R.string.bt_max_connections),
            value = config.int(k("maxConnections")),
            range = 20..2000,
            valueText = { "$it" },
            onCommit = { set(k("maxConnections"), it) },
        )
        SliderSettingRow(
            title = stringResource(R.string.bt_metadata_timeout),
            value = config.int(k("metadataTimeout")),
            range = 5..300,
            valueText = { "$it s" },
            onCommit = { set(k("metadataTimeout"), it) },
        )
    }

    SettingSection(title = stringResource(R.string.bt_section_tracker)) {
        SwitchSettingRow(
            title = stringResource(R.string.bt_enable_web_trackers),
            subtitle = stringResource(R.string.bt_enable_web_trackers_desc),
            checked = config.bool(k("enableWebTrackers")),
            onCheckedChange = { set(k("enableWebTrackers"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.bt_auto_refresh_web_trackers),
            checked = config.bool(k("autoRefreshWebTrackers")),
            onCheckedChange = { set(k("autoRefreshWebTrackers"), it) },
        )
        TextSettingRow(
            title = stringResource(R.string.bt_custom_trackers),
            value = config.str(k("webTrackerCustomList")),
            onConfirm = { set(k("webTrackerCustomList"), it) },
            emptyHint = stringResource(R.string.bt_custom_trackers_desc),
            singleLine = false,
        )
    }

    SettingSection(title = stringResource(R.string.bt_section_transfer)) {
        SwitchSettingRow(
            title = stringResource(R.string.bt_sequential_download),
            subtitle = stringResource(R.string.bt_sequential_download_desc),
            checked = config.bool(k("enableSequentialDownload")),
            onCheckedChange = { set(k("enableSequentialDownload"), it) },
        )
        OptionsSettingRow(
            title = stringResource(R.string.bt_storage_mode),
            value = config.str(k("storageMode")),
            options = listOf(
                "sparse" to stringResource(R.string.bt_storage_sparse),
                "allocate" to stringResource(R.string.bt_storage_allocate),
            ),
            onSelect = { set(k("storageMode"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.bt_save_magnet_file),
            subtitle = stringResource(R.string.bt_save_magnet_file_desc),
            checked = config.bool(k("saveMagnetFile")),
            onCheckedChange = { set(k("saveMagnetFile"), it) },
        )
    }

    SettingSection(title = stringResource(R.string.bt_section_seeding)) {
        NumberSettingRow(
            title = stringResource(R.string.bt_max_upload_speed),
            value = config.int(k("maxUploadSpeed")) / 1024,
            range = 0..102400,
            onConfirm = { set(k("maxUploadSpeed"), it * 1024) },
            unit = "KB/s",
            valueText = { if (it == 0) unlimited else "$it KB/s" },
        )
        NumberSettingRow(
            title = stringResource(R.string.bt_seeding_ratio_limit),
            value = config.int(k("seedingRatioLimit")),
            range = 0..10000,
            onConfirm = { set(k("seedingRatioLimit"), it) },
            unit = "%",
            valueText = { if (it == 0) unlimited else "$it %" },
        )
        NumberSettingRow(
            title = stringResource(R.string.bt_seeding_time_limit),
            value = config.int(k("seedingTimeLimit")),
            range = 0..43200,
            onConfirm = { set(k("seedingTimeLimit"), it) },
            unit = "min",
            valueText = { if (it == 0) unlimited else "$it min" },
        )
    }
}

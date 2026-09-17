package com.xychr.ghostdownloader.features.bittorrent_pack

import com.xychr.ghostdownloader.packs.*

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.SettingRanges
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.NumberSettingRow
import com.xychr.ghostdownloader.ui.components.settings.OptionsSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SliderSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

@Composable
fun BitTorrentSettings(
    config: JsonObject,
    k: PackKeys,
    set: (String, Any) -> Unit,
    send: suspend (String, List<Any?>) -> JsonElement,
) {
    val auto = stringResource(R.string.value_auto)
    val unlimited = stringResource(R.string.value_unlimited)
    var isManagingTrackers by remember { mutableStateOf(false) }

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
            range = SettingRanges[k("listenPort")],
            onConfirm = { set(k("listenPort"), it) },
            valueText = { if (it == 0) auto else "$it" },
        )
        SliderSettingRow(
            title = stringResource(R.string.bt_max_connections),
            value = config.int(k("maxConnections")),
            range = SettingRanges[k("maxConnections")],
            valueText = { "$it" },
            onCommit = { set(k("maxConnections"), it) },
        )
        SliderSettingRow(
            title = stringResource(R.string.bt_metadata_timeout),
            value = config.int(k("metadataTimeout")),
            range = SettingRanges[k("metadataTimeout")],
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
        val sourceCount = config.strings(k("webTrackerSources")).size
        val cachedCount = config.sizes(k("webTrackerSourceCache")).values.sum()
        ActionSettingRow(
            title = stringResource(R.string.bt_web_tracker),
            subtitle = stringResource(R.string.bt_web_tracker_summary, sourceCount, cachedCount),
            onClick = { isManagingTrackers = true },
        )
    }

    if (isManagingTrackers) {
        WebTrackerSheet(
            config = config,
            keys = k,
            set = set,
            send = send,
            onDismiss = { isManagingTrackers = false },
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
            range = SettingRanges[k("maxUploadSpeed")].let { it.first / 1024..it.last / 1024 },
            onConfirm = { set(k("maxUploadSpeed"), it * 1024) },
            unit = "KB/s",
            valueText = { if (it == 0) unlimited else "$it KB/s" },
        )
        NumberSettingRow(
            title = stringResource(R.string.bt_seeding_ratio_limit),
            value = config.int(k("seedingRatioLimit")),
            range = SettingRanges[k("seedingRatioLimit")],
            onConfirm = { set(k("seedingRatioLimit"), it) },
            unit = "%",
            valueText = { if (it == 0) unlimited else "$it %" },
        )
        NumberSettingRow(
            title = stringResource(R.string.bt_seeding_time_limit),
            value = config.int(k("seedingTimeLimit")),
            range = SettingRanges[k("seedingTimeLimit")],
            onConfirm = { set(k("seedingTimeLimit"), it) },
            unit = "min",
            valueText = { if (it == 0) unlimited else "$it min" },
        )
    }
}

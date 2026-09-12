package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.NumberSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.components.settings.TextSettingRow
import kotlinx.serialization.json.JsonObject

@Composable
fun ED2kSettings(config: JsonObject, k: PackKeys, set: (String, Any) -> Unit) {
    val auto = stringResource(R.string.value_auto)
    val unlimited = stringResource(R.string.value_unlimited)

    SettingSection(title = stringResource(R.string.ed2k_section_network)) {
        SwitchSettingRow(
            title = stringResource(R.string.ed2k_enable_dht),
            subtitle = stringResource(R.string.ed2k_enable_dht_desc),
            checked = config.bool(k("enableDht")),
            onCheckedChange = { set(k("enableDht"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.ed2k_enable_upnp),
            subtitle = stringResource(R.string.ed2k_enable_upnp_desc),
            checked = config.bool(k("enableUpnp")),
            onCheckedChange = { set(k("enableUpnp"), it) },
        )
        NumberSettingRow(
            title = stringResource(R.string.ed2k_listen_port),
            value = config.int(k("listenPort")),
            range = 0..65535,
            onConfirm = { set(k("listenPort"), it) },
            valueText = { if (it == 0) auto else "$it" },
        )
    }

    SettingSection(title = stringResource(R.string.ed2k_section_source)) {
        TextSettingRow(
            title = stringResource(R.string.ed2k_server_met_source),
            value = config.str(k("serverMetSource")),
            onConfirm = { set(k("serverMetSource"), it) },
            emptyHint = stringResource(R.string.ed2k_server_met_source_desc),
        )
        TextSettingRow(
            title = stringResource(R.string.ed2k_nodes_dat_source),
            value = config.str(k("nodesDatSource")),
            onConfirm = { set(k("nodesDatSource"), it) },
            emptyHint = stringResource(R.string.ed2k_nodes_dat_source_desc),
        )
    }

    SettingSection(title = stringResource(R.string.ed2k_section_sharing)) {
        NumberSettingRow(
            title = stringResource(R.string.ed2k_sharing_time_limit),
            value = config.int(k("sharingTimeLimit")),
            range = 0..43200,
            onConfirm = { set(k("sharingTimeLimit"), it) },
            unit = "min",
            valueText = { if (it == 0) unlimited else "$it min" },
        )
    }
}

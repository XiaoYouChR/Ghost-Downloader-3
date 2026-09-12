package com.xychr.ghostdownloader.packs

import androidx.compose.material3.ListItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.util.formatDuration
import com.xychr.ghostdownloader.ui.util.formatSpeed
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long

object Ed2kUi : PackUi {
    override val packId = "ed2k"

    override val settingsTitle = R.string.pack_ed2k

    override val searchItems = listOf(
        R.string.ed2k_enable_dht to R.string.ed2k_enable_dht_desc,
        R.string.ed2k_enable_upnp to R.string.ed2k_enable_upnp_desc,
        R.string.ed2k_listen_port to null,
        R.string.ed2k_server_met_source to R.string.ed2k_server_met_source_desc,
        R.string.ed2k_nodes_dat_source to R.string.ed2k_nodes_dat_source_desc,
        R.string.ed2k_sharing_time_limit to null,
    )

    override val settingsContent: (@Composable (JsonObject, PackKeys, (String, Any) -> Unit) -> Unit) =
        { config, keys, set -> ED2kSettings(config, keys, set) }

    override val taskExtra: (@Composable (JsonObject) -> Unit) = { packFields ->
        val peers = packFields["peers"]?.jsonObject
        val seedingSeconds = packFields["seedingSeconds"]?.jsonPrimitive?.long

        if (peers != null) {
            val active = peers["active"]?.jsonPrimitive?.int ?: 0
            val total = peers["total"]?.jsonPrimitive?.int ?: 0
            PackCaption(stringResource(R.string.task_peers, active, total))
        }
        if (seedingSeconds != null && seedingSeconds > 0) {
            PackCaption(stringResource(R.string.task_shared_time, formatDuration(seedingSeconds)))
        }
    }

    override val detailExtra: (@Composable (JsonObject) -> Unit) = { packFields ->
        val peers = packFields["peers"]?.jsonObject
        val seedingSeconds = packFields["seedingSeconds"]?.jsonPrimitive?.long
        val upload = packFields["uploadSpeed"]?.jsonPrimitive?.long

        PackSectionTitle(stringResource(R.string.task_detail_bt_info))
        if (peers != null) {
            val active = peers["active"]?.jsonPrimitive?.int ?: 0
            val total = peers["total"]?.jsonPrimitive?.int ?: 0
            ListItem(
                supportingContent = { Text("$active / $total") },
            ) { Text(stringResource(R.string.task_detail_peers)) }
        }
        if (upload != null && upload > 0) {
            ListItem(
                supportingContent = { Text(formatSpeed(upload)) },
            ) { Text(stringResource(R.string.task_detail_upload_speed)) }
        }
        if (seedingSeconds != null && seedingSeconds > 0) {
            ListItem(
                supportingContent = { Text(stringResource(R.string.task_upload_time, formatDuration(seedingSeconds))) },
            ) { Text(stringResource(R.string.task_sharing)) }
        }
    }
}

package com.xychr.ghostdownloader.packs

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.util.formatDuration
import com.xychr.ghostdownloader.ui.util.formatSpeed
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long

object BitTorrentUi : PackUi {
    override val packId = "bt"

    override val settingsTitle = R.string.pack_bittorrent

    override val searchItems = listOf(
        R.string.bt_enable_dht to R.string.bt_enable_dht_desc,
        R.string.bt_enable_lsd to R.string.bt_enable_lsd_desc,
        R.string.bt_listen_port to null,
        R.string.bt_max_connections to null,
        R.string.bt_metadata_timeout to null,
        R.string.bt_enable_web_trackers to R.string.bt_enable_web_trackers_desc,
        R.string.bt_auto_refresh_web_trackers to null,
        R.string.bt_custom_trackers to R.string.bt_custom_trackers_desc,
        R.string.bt_sequential_download to R.string.bt_sequential_download_desc,
        R.string.bt_storage_mode to null,
        R.string.bt_save_magnet_file to R.string.bt_save_magnet_file_desc,
        R.string.bt_max_upload_speed to null,
        R.string.bt_seeding_ratio_limit to null,
        R.string.bt_seeding_time_limit to null,
    )

    override val settingsContent: (@Composable (JsonObject, PackKeys, (String, Any) -> Unit) -> Unit) =
        { config, keys, set -> BitTorrentSettings(config, keys, set) }

    override val taskExtra: (@Composable (JsonObject) -> Unit) = { packFields ->
        val peers = packFields["peers"]?.jsonObject
        val shareRatio = packFields["shareRatio"]?.jsonPrimitive?.double
        val seedingSeconds = packFields["seedingSeconds"]?.jsonPrimitive?.long

        if (peers != null) {
            val active = peers["active"]?.jsonPrimitive?.int ?: 0
            val total = peers["total"]?.jsonPrimitive?.int ?: 0
            PackCaption(stringResource(R.string.task_peers, active, total))
        }
        if (shareRatio != null) {
            PackCaption(stringResource(R.string.task_share_ratio, "%.1f%%".format(shareRatio)))
        }
        if (seedingSeconds != null && seedingSeconds > 0) {
            PackCaption(stringResource(R.string.task_shared_time, formatDuration(seedingSeconds)))
        }
    }

    override val detailExtra: (@Composable (JsonObject) -> Unit) = { packFields ->
        val peers = packFields["peers"]?.jsonObject
        val shareRatio = packFields["shareRatio"]?.jsonPrimitive?.double
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
        if (shareRatio != null || (seedingSeconds != null && seedingSeconds > 0)) {
            ListItem(
                supportingContent = {
                    if (seedingSeconds != null && seedingSeconds > 0)
                        Text(stringResource(R.string.task_upload_time, formatDuration(seedingSeconds)))
                },
            ) {
                Text(
                    if (shareRatio != null) stringResource(R.string.task_share_ratio, "%.1f%%".format(shareRatio))
                    else stringResource(R.string.task_sharing)
                )
            }
        }
    }
}

@Composable
internal fun PackCaption(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
internal fun PackSectionTitle(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleSmall,
        color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(bottom = 4.dp),
    )
}

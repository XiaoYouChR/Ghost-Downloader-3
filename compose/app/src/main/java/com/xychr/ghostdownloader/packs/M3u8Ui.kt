package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

object M3u8Ui : PackUi {
    override val packId = "m3u8"

    override val settingsTitle = R.string.pack_m3u8

    override val searchItems = listOf(
        R.string.m3u8_output_format to null,
        R.string.m3u8_subtitle_format to null,
        R.string.m3u8_binary_merge to R.string.m3u8_binary_merge_desc,
        R.string.m3u8_delete_temp to R.string.m3u8_delete_temp_desc,
        R.string.m3u8_omit_date_info to null,
        R.string.m3u8_keep_image_segments to null,
        R.string.m3u8_mp4_realtime_decryption to R.string.m3u8_mp4_realtime_decryption_desc,
        R.string.m3u8_auto_select to R.string.m3u8_auto_select_desc,
        R.string.m3u8_select_all_audio_subtitle to null,
        R.string.m3u8_ad_keyword to R.string.m3u8_ad_keyword_desc,
        R.string.m3u8_thread_count to null,
        R.string.m3u8_retry_count to null,
        R.string.m3u8_request_timeout to null,
        R.string.m3u8_concurrent_download to null,
        R.string.m3u8_check_segments_count to null,
        R.string.m3u8_append_url_params to R.string.m3u8_append_url_params_desc,
        R.string.m3u8_max_speed to null,
        R.string.m3u8_live_keep_segments to null,
        R.string.m3u8_live_pipe_mux to R.string.m3u8_live_pipe_mux_desc,
        R.string.m3u8_live_fix_vtt to null,
        R.string.m3u8_live_wait_time to null,
        R.string.m3u8_live_take_count to null,
    )

    override val settingsContent: (@Composable (JsonObject, PackKeys, (String, Any) -> Unit) -> Unit) =
        { config, keys, set -> M3U8Settings(config, keys, set) }

    override val taskExtra: (@Composable (JsonObject) -> Unit) = { packFields ->
        val liveElapsed = packFields["liveElapsed"]?.jsonPrimitive?.contentOrNull
        val recordLimit = packFields["recordLimit"]?.jsonPrimitive?.contentOrNull

        if (!liveElapsed.isNullOrEmpty()) {
            PackCaption(
                stringResource(R.string.task_recorded, liveElapsed) +
                    recordLimit?.takeIf(String::isNotEmpty)?.let { " / $it" }.orEmpty()
            )
        }
    }
}

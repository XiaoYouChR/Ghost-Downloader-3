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
fun M3U8Settings(config: JsonObject, k: PackKeys, set: (String, Any) -> Unit) {
    val unlimited = stringResource(R.string.value_unlimited)
    val auto = stringResource(R.string.value_auto)

    SettingSection(title = stringResource(R.string.m3u8_section_output)) {
        OptionsSettingRow(
            title = stringResource(R.string.m3u8_output_format),
            value = config.str(k("outputFormat")),
            options = listOf("mp4" to "MP4", "mkv" to "MKV"),
            onSelect = { set(k("outputFormat"), it) },
        )
        OptionsSettingRow(
            title = stringResource(R.string.m3u8_subtitle_format),
            value = config.str(k("subtitleFormat")),
            options = listOf("SRT" to "SRT", "VTT" to "VTT"),
            onSelect = { set(k("subtitleFormat"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_binary_merge),
            subtitle = stringResource(R.string.m3u8_binary_merge_desc),
            checked = config.bool(k("shouldBinaryMerge")),
            onCheckedChange = { set(k("shouldBinaryMerge"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_delete_temp),
            subtitle = stringResource(R.string.m3u8_delete_temp_desc),
            checked = config.bool(k("shouldDeleteTemp")),
            onCheckedChange = { set(k("shouldDeleteTemp"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_omit_date_info),
            checked = config.bool(k("shouldOmitDateInfo")),
            onCheckedChange = { set(k("shouldOmitDateInfo"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_mp4_realtime_decryption),
            subtitle = stringResource(R.string.m3u8_mp4_realtime_decryption_desc),
            checked = config.bool(k("shouldUseMp4RealTimeDecryption")),
            onCheckedChange = { set(k("shouldUseMp4RealTimeDecryption"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_keep_image_segments),
            checked = config.bool(k("shouldKeepImageSegments")),
            onCheckedChange = { set(k("shouldKeepImageSegments"), it) },
        )
    }

    SettingSection(title = stringResource(R.string.m3u8_section_select)) {
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_auto_select),
            subtitle = stringResource(R.string.m3u8_auto_select_desc),
            checked = config.bool(k("shouldAutoSelect")),
            onCheckedChange = { set(k("shouldAutoSelect"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_select_all_audio_subtitle),
            checked = config.bool(k("shouldSelectAllAudioSubtitle")),
            onCheckedChange = { set(k("shouldSelectAllAudioSubtitle"), it) },
        )
        TextSettingRow(
            title = stringResource(R.string.m3u8_ad_keyword),
            value = config.str(k("adKeyword")),
            onConfirm = { set(k("adKeyword"), it) },
            emptyHint = stringResource(R.string.m3u8_ad_keyword_desc),
        )
    }

    SettingSection(title = stringResource(R.string.m3u8_section_network)) {
        SliderSettingRow(
            title = stringResource(R.string.m3u8_thread_count),
            value = config.int(k("threadCount")),
            range = 1..64,
            valueText = { "$it" },
            onCommit = { set(k("threadCount"), it) },
        )
        SliderSettingRow(
            title = stringResource(R.string.m3u8_retry_count),
            value = config.int(k("retryCount")),
            range = 0..20,
            valueText = { "$it" },
            onCommit = { set(k("retryCount"), it) },
        )
        NumberSettingRow(
            title = stringResource(R.string.m3u8_request_timeout),
            value = config.int(k("requestTimeout")),
            range = 5..600,
            onConfirm = { set(k("requestTimeout"), it) },
            unit = "s",
        )
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_concurrent_download),
            checked = config.bool(k("shouldConcurrentDownload")),
            onCheckedChange = { set(k("shouldConcurrentDownload"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_check_segments_count),
            checked = config.bool(k("shouldCheckSegmentsCount")),
            onCheckedChange = { set(k("shouldCheckSegmentsCount"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_append_url_params),
            subtitle = stringResource(R.string.m3u8_append_url_params_desc),
            checked = config.bool(k("shouldAppendUrlParams")),
            onCheckedChange = { set(k("shouldAppendUrlParams"), it) },
        )
        NumberSettingRow(
            title = stringResource(R.string.m3u8_max_speed),
            value = config.int(k("maxSpeed")),
            range = -1..1000000,
            onConfirm = { set(k("maxSpeed"), it) },
            valueText = { if (it <= 0) unlimited else "$it" },
        )
        OptionsSettingRow(
            title = stringResource(R.string.m3u8_speed_unit),
            value = config.str(k("speedUnit")),
            options = listOf("Mbps" to "Mbps", "Kbps" to "Kbps"),
            onSelect = { set(k("speedUnit"), it) },
        )
    }

    SettingSection(title = stringResource(R.string.m3u8_section_live)) {
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_live_keep_segments),
            checked = config.bool(k("shouldKeepLiveSegments")),
            onCheckedChange = { set(k("shouldKeepLiveSegments"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_live_pipe_mux),
            subtitle = stringResource(R.string.m3u8_live_pipe_mux_desc),
            checked = config.bool(k("shouldUseLivePipeMux")),
            onCheckedChange = { set(k("shouldUseLivePipeMux"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.m3u8_live_fix_vtt),
            checked = config.bool(k("shouldFixLiveVtt")),
            onCheckedChange = { set(k("shouldFixLiveVtt"), it) },
        )
        NumberSettingRow(
            title = stringResource(R.string.m3u8_live_wait_time),
            value = config.int(k("liveWaitTime")),
            range = 0..100000,
            onConfirm = { set(k("liveWaitTime"), it) },
            unit = "s",
            valueText = { if (it == 0) auto else "$it s" },
        )
        NumberSettingRow(
            title = stringResource(R.string.m3u8_live_take_count),
            value = config.int(k("liveTakeCount")),
            range = 0..1000,
            onConfirm = { set(k("liveTakeCount"), it) },
            valueText = { if (it == 0) auto else "$it" },
        )
    }
}

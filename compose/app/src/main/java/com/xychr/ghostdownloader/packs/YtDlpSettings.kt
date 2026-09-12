package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.components.settings.TextSettingRow
import kotlinx.serialization.json.JsonObject

@Composable
fun YtDlpSettings(config: JsonObject, k: PackKeys, set: (String, Any) -> Unit) {
    SettingSection {
        SwitchSettingRow(
            title = stringResource(R.string.ytdlp_prefer_mp4),
            subtitle = stringResource(R.string.ytdlp_prefer_mp4_desc),
            checked = config.bool(k("shouldPreferMp4")),
            onCheckedChange = { set(k("shouldPreferMp4"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.ytdlp_embed_metadata),
            subtitle = stringResource(R.string.ytdlp_embed_metadata_desc),
            checked = config.bool(k("shouldEmbedMetadata")),
            onCheckedChange = { set(k("shouldEmbedMetadata"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.ytdlp_embed_chapters),
            subtitle = stringResource(R.string.ytdlp_embed_chapters_desc),
            checked = config.bool(k("shouldEmbedChapters")),
            onCheckedChange = { set(k("shouldEmbedChapters"), it) },
        )
        TextSettingRow(
            title = stringResource(R.string.ytdlp_subtitle_languages),
            value = config.str(k("subtitleLanguages")),
            onConfirm = { set(k("subtitleLanguages"), it) },
            emptyHint = stringResource(R.string.ytdlp_subtitle_languages_desc),
            placeholder = "en,zh-Hans",
        )
    }
}

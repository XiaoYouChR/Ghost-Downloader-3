package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import com.xychr.ghostdownloader.R
import kotlinx.serialization.json.JsonObject

object YtDlpUi : PackUi {
    override val packId = "ytdlp"

    override val settingsTitle = R.string.pack_yt_dlp

    override val searchItems = listOf(
        R.string.ytdlp_prefer_mp4 to R.string.ytdlp_prefer_mp4_desc,
        R.string.ytdlp_embed_metadata to R.string.ytdlp_embed_metadata_desc,
        R.string.ytdlp_embed_chapters to R.string.ytdlp_embed_chapters_desc,
        R.string.ytdlp_subtitle_languages to R.string.ytdlp_subtitle_languages_desc,
    )

    override val settingsContent: (@Composable (JsonObject, PackKeys, (String, Any) -> Unit) -> Unit) =
        { config, keys, set -> YtDlpSettings(config, keys, set) }
}

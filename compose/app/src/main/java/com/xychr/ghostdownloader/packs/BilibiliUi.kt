package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import com.xychr.ghostdownloader.R
import kotlinx.serialization.json.JsonObject

object BilibiliUi : PackUi {
    override val packId = "bili"

    override val settingsTitle = R.string.pack_bilibili

    override val searchItems = listOf(
        R.string.bili_scan_login to null,
        R.string.bili_import_cookie to null,
        R.string.bili_logout to null,
        R.string.bili_default_quality to null,
        R.string.bili_alternative_quality to null,
        R.string.bili_hdr to R.string.bili_hdr_desc,
        R.string.bili_dolby to R.string.bili_dolby_desc,
    )

    override val settingsContent: (@Composable (JsonObject, PackKeys, (String, Any) -> Unit) -> Unit) =
        { config, keys, set ->
            BilibiliLoginRows()
            BilibiliSettings(config, keys, set)
        }
}

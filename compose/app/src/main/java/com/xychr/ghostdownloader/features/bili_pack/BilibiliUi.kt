package com.xychr.ghostdownloader.features.bili_pack

import androidx.compose.runtime.Composable
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.model.DraftPreview
import com.xychr.ghostdownloader.packs.DraftMediaSection
import com.xychr.ghostdownloader.packs.PackKeys
import com.xychr.ghostdownloader.packs.PackSettingsContent
import com.xychr.ghostdownloader.packs.PackUi
import kotlinx.serialization.json.JsonObject

object BilibiliUi : PackUi {
    override val packId = "bili"

    override val settingsTitle = R.string.pack_bilibili

    override val searchItems = listOf(
        R.string.bili_login to null,
        R.string.bili_import_cookie to null,
        R.string.bili_logout to null,
        R.string.bili_default_quality to null,
        R.string.bili_alternative_quality to null,
        R.string.bili_hdr to R.string.bili_hdr_desc,
        R.string.bili_dolby to R.string.bili_dolby_desc,
    )

    override val settingsContent: PackSettingsContent =
        { config, keys, set, send ->
            BilibiliLoginRows()
            BilibiliSettings(config, keys, set)
        }

    override val draftExtra: (@Composable (JsonObject, String, suspend (String, List<Any?>) -> Unit) -> Unit) =
        { packFields, url, send ->
            DraftMediaSection(packFields, url, send,
                fetchPreview = { engineRepository.query<DraftPreview>("draftPreview", it) })
        }
}

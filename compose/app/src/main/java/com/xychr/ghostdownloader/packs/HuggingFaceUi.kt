package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import com.xychr.ghostdownloader.R
import kotlinx.serialization.json.JsonObject

object HuggingFaceUi : PackUi {
    override val packId = "huggingface"

    override val settingsTitle = R.string.pack_huggingface

    override val searchItems = listOf(
        R.string.huggingface_enabled to R.string.huggingface_enabled_desc,
        R.string.huggingface_access_token to R.string.huggingface_access_token_desc,
        R.string.proxy_site to null,
    )

    override val settingsContent: (@Composable (JsonObject, PackKeys, (String, Any) -> Unit) -> Unit) =
        { config, keys, set -> HuggingFaceSettings(config, keys, set) }
}

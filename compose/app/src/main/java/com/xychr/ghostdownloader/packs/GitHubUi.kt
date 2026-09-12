package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import com.xychr.ghostdownloader.R
import kotlinx.serialization.json.JsonObject

object GitHubUi : PackUi {
    override val packId = "github"

    override val settingsTitle = R.string.pack_github

    override val searchItems = listOf(
        R.string.github_enabled to R.string.github_enabled_desc,
        R.string.proxy_site to null,
    )

    override val settingsContent: (@Composable (JsonObject, PackKeys, (String, Any) -> Unit) -> Unit) =
        { config, keys, set -> GitHubSettings(config, keys, set) }
}

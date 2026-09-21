package com.xychr.ghostdownloader.features.github_pack

import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.packs.PackSettingsContent
import com.xychr.ghostdownloader.packs.PackUi

object GitHubUi : PackUi {
    override val packId = "github"

    override val settingsTitle = R.string.pack_github

    override val searchItems = listOf(
        R.string.github_enabled to R.string.github_enabled_desc,
        R.string.proxy_site to null,
    )

    override val settingsContent: PackSettingsContent =
        { config, keys, set, send -> GitHubSettings(config, keys, set, send) }
}

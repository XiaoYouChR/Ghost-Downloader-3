package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.OptionsSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.components.settings.TextSettingRow
import kotlinx.serialization.json.JsonObject

private val PROXY_SITES: List<String> by lazy {
    engineStrings("github_pack.config", "GITHUB_PROXY_SITES")
}

@Composable
fun GitHubSettings(config: JsonObject, k: PackKeys, set: (String, Any) -> Unit) {
    val custom = config.str(k("customSite"))

    SettingSection {
        SwitchSettingRow(
            title = stringResource(R.string.github_enabled),
            subtitle = stringResource(R.string.github_enabled_desc),
            checked = config.bool(k("enabled")),
            onCheckedChange = { set(k("enabled"), it) },
        )
        OptionsSettingRow(
            title = stringResource(R.string.proxy_site),
            value = config.str(k("selectedSite")),
            options = PROXY_SITES.map { it to it } + listOf(
                "__custom__" to stringResource(R.string.proxy_site_custom),
            ),
            onSelect = { set(k("selectedSite"), it) },
        )
        TextSettingRow(
            title = stringResource(R.string.proxy_site_custom),
            value = custom,
            onConfirm = { set(k("customSite"), it) },
            emptyHint = stringResource(R.string.proxy_site_custom_desc),
            placeholder = "https://example.com",
        )
    }
}

package com.xychr.ghostdownloader.features.github_pack

import com.xychr.ghostdownloader.packs.*

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.OptionsSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.components.settings.TextSettingRow
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

private val PROXY_SITES: List<String> by lazy {
    engineStrings("github_pack.config", "GITHUB_PROXY_SITES")
}

private const val CUSTOM_SITE_KEY = "__custom__"

@Composable
fun GitHubSettings(
    config: JsonObject,
    k: PackKeys,
    set: (String, Any) -> Unit,
    send: suspend (String, List<Any?>) -> JsonElement,
) {
    val custom = config.str(k("customSite"))
    var latencies by remember { mutableStateOf<Map<String, Int>>(emptyMap()) }

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
            options = PROXY_SITES.map { it to proxySiteLabel(it, latencies[it]) } + listOf(
                CUSTOM_SITE_KEY to stringResource(R.string.proxy_site_custom),
            ),
            onSelect = { set(k("selectedSite"), it) },
            onOpen = { latencies = probeSites(send) },
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

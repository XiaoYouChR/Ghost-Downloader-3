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
    engineStrings("huggingface_pack.config", "HF_PROXY_SITES")
}

@Composable
fun HuggingFaceSettings(config: JsonObject, k: PackKeys, set: (String, Any) -> Unit) {
    val custom = config.str(k("customSite"))
    val token = config.str(k("accessToken"))

    SettingSection {
        SwitchSettingRow(
            title = stringResource(R.string.huggingface_enabled),
            subtitle = stringResource(R.string.huggingface_enabled_desc),
            checked = config.bool(k("isEnabled")),
            onCheckedChange = { set(k("isEnabled"), it) },
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
        TextSettingRow(
            title = stringResource(R.string.huggingface_access_token),
            value = token,
            onConfirm = { set(k("accessToken"), it) },
            emptyHint = stringResource(R.string.huggingface_access_token_desc),
            placeholder = "hf_...",
        )
    }
}

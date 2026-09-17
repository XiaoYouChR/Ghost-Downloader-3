package com.xychr.ghostdownloader.features.huggingface_pack

import com.xychr.ghostdownloader.packs.*

import android.content.Intent
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.core.net.toUri
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.OptionsSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.components.settings.TextSettingRow
import com.xychr.ghostdownloader.ui.platform.start
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

private val PROXY_SITES: List<String> by lazy {
    engineStrings("huggingface_pack.config", "HF_PROXY_SITES")
}

private val TOKEN_URL: String by lazy {
    engineString("huggingface_pack.config", "TOKEN_URL")
}

private const val CUSTOM_SITE_KEY = "__custom__"

@Composable
fun HuggingFaceSettings(
    config: JsonObject,
    k: PackKeys,
    set: (String, Any) -> Unit,
    send: suspend (String, List<Any?>) -> JsonElement,
) {
    val context = LocalContext.current
    val custom = config.str(k("customSite"))
    var latencies by remember { mutableStateOf<Map<String, Int>>(emptyMap()) }

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
        TextSettingRow(
            title = stringResource(R.string.huggingface_access_token),
            value = config.str(k("accessToken")),
            onConfirm = { set(k("accessToken"), it) },
            emptyHint = stringResource(R.string.huggingface_access_token_desc),
            placeholder = "hf_...",
            isSecret = true,
            trailing = {
                if (TOKEN_URL.isNotEmpty()) {
                    IconButton(onClick = { context.start(Intent(Intent.ACTION_VIEW, TOKEN_URL.toUri())) }) {
                        Icon(
                            painterResource(R.drawable.ic_open_in_new),
                            contentDescription = stringResource(R.string.huggingface_access_token_get),
                        )
                    }
                }
            },
        )
    }
}

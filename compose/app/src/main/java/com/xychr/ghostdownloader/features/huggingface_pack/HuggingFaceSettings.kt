package com.xychr.ghostdownloader.features.huggingface_pack

import android.content.Intent
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.core.net.toUri
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.packs.PackKeys
import com.xychr.ghostdownloader.packs.bool
import com.xychr.ghostdownloader.packs.str
import com.xychr.ghostdownloader.ui.components.settings.OptionsSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import com.xychr.ghostdownloader.ui.components.settings.TextSettingRow
import com.xychr.ghostdownloader.ui.platform.start
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive

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
    var proxySites by remember { mutableStateOf<List<String>>(emptyList()) }
    var tokenUrl by remember { mutableStateOf("") }
    var latencies by remember { mutableStateOf<Map<String, Int>>(emptyMap()) }
    LaunchedEffect(Unit) {
        proxySites = send("proxySiteList", emptyList()).jsonArray.map { it.jsonPrimitive.content }
        tokenUrl = send("tokenUrl", emptyList()).jsonPrimitive.content
    }

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
            options = proxySites.map { it to proxySiteLabel(it, latencies[it]) } + listOf(
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
                if (tokenUrl.isNotEmpty()) {
                    IconButton(onClick = { context.start(Intent(Intent.ACTION_VIEW, tokenUrl.toUri())) }) {
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

@Composable
private fun proxySiteLabel(url: String, latency: Int?): String {
    val host = url.substringAfter("://").trimEnd('/')
    return when {
        latency == null -> host
        latency < 0 -> "$host (${stringResource(R.string.proxy_site_unavailable)})"
        else -> "$host ($latency ms)"
    }
}

private suspend fun probeSites(send: suspend (String, List<Any?>) -> JsonElement): Map<String, Int> =
    (send("probeSites", emptyList()) as? JsonObject).orEmpty()
        .mapValues { (_, value) -> value.jsonPrimitive.intOrNull ?: 0 }

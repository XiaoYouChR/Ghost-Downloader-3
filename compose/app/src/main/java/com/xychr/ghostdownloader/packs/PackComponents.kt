package com.xychr.ghostdownloader.packs

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import com.xychr.ghostdownloader.R

@Composable
fun PackCaption(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
fun PackSectionTitle(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleSmall,
        color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(bottom = 4.dp),
    )
}

@Composable
fun proxySiteLabel(url: String, latency: Int?): String {
    val host = url.substringAfter("://").trimEnd('/')
    return when {
        latency == null -> host
        latency < 0 -> "$host (${stringResource(R.string.proxy_site_unavailable)})"
        else -> "$host ($latency ms)"
    }
}

suspend fun probeSites(send: suspend (String, List<Any?>) -> JsonElement): Map<String, Int> =
    (send("probeSites", emptyList()) as? JsonObject).orEmpty()
        .mapValues { (_, value) -> value.jsonPrimitive.intOrNull ?: 0 }

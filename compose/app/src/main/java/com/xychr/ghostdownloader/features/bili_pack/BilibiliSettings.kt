package com.xychr.ghostdownloader.features.bili_pack

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.packs.PackKeys
import com.xychr.ghostdownloader.packs.bool
import com.xychr.ghostdownloader.packs.int
import com.xychr.ghostdownloader.packs.str
import com.xychr.ghostdownloader.ui.components.settings.OptionsSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

@Composable
fun BilibiliSettings(
    config: JsonObject,
    k: PackKeys,
    set: (String, Any) -> Unit,
    send: suspend (String, List<Any?>) -> JsonElement,
) {
    var qualities by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }
    LaunchedEffect(Unit) {
        qualities = send("qualityOptions", emptyList()).jsonArray.map {
            val obj = it.jsonObject
            obj["value"]!!.jsonPrimitive.content to obj["label"]!!.jsonPrimitive.content
        }
    }

    SettingSection {
        OptionsSettingRow(
            title = stringResource(R.string.bili_default_quality),
            value = config.int(k("defaultQuality")).toString(),
            options = qualities.map { (value, label) -> value to label },
            onSelect = { set(k("defaultQuality"), it.toInt()) },
        )
        OptionsSettingRow(
            title = stringResource(R.string.bili_alternative_quality),
            value = config.str(k("alternativeQuality")),
            options = listOf(
                "max" to stringResource(R.string.bili_quality_max),
                "min" to stringResource(R.string.bili_quality_min),
            ),
            onSelect = { set(k("alternativeQuality"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.bili_hdr),
            subtitle = stringResource(R.string.bili_hdr_desc),
            checked = config.bool(k("shouldIncludeHdr")),
            onCheckedChange = { set(k("shouldIncludeHdr"), it) },
        )
        SwitchSettingRow(
            title = stringResource(R.string.bili_dolby),
            subtitle = stringResource(R.string.bili_dolby_desc),
            checked = config.bool(k("shouldIncludeDolby")),
            onCheckedChange = { set(k("shouldIncludeDolby"), it) },
        )
    }
}

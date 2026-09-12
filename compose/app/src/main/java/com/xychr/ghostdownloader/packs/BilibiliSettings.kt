package com.xychr.ghostdownloader.packs

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.OptionsSettingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SwitchSettingRow
import kotlinx.serialization.json.JsonObject

private val QUALITIES: List<Pair<String, String>> by lazy {
    engineStrings("bili_pack.config", "QUALITY_VALUES")
        .zip(engineStrings("bili_pack.config", "QUALITY_LABELS"))
}

@Composable
fun BilibiliSettings(config: JsonObject, k: PackKeys, set: (String, Any) -> Unit) {
    SettingSection {
        OptionsSettingRow(
            title = stringResource(R.string.bili_default_quality),
            value = config.int(k("defaultQuality")).toString(),
            options = QUALITIES.map { (value, label) -> value.toString() to label },
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

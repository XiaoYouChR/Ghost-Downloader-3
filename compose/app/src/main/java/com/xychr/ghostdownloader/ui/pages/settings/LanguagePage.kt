package com.xychr.ghostdownloader.ui.pages.settings

import android.app.Activity
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.RadioRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage
import com.xychr.ghostdownloader.ui.platform.loadLanguageTag
import com.xychr.ghostdownloader.ui.platform.saveLanguageTag

private data class LanguageOption(
    val tag: String?,
    val label: String,
)

private val languages = listOf(
    LanguageOption(null, ""),
    LanguageOption("zh-CN", "简体中文"),
    LanguageOption("zh-TW", "繁體中文（台灣）"),
    LanguageOption("zh-HK", "繁體中文（香港）"),
    LanguageOption("en", "English"),
    LanguageOption("ja", "日本語"),
    LanguageOption("ru", "Русский"),
    LanguageOption("pt-BR", "Português (Brasil)"),
    LanguageOption("es", "Español"),
)

@Composable
fun LanguagePage(onBack: () -> Unit) {
    val context = LocalContext.current
    var currentTag by remember { mutableStateOf(loadLanguageTag(context)) }

    SettingsPage(stringResource(R.string.settings_section_language), onBack) {
        SettingSection {
            languages.forEach { option ->
                val label = if (option.tag == null) stringResource(R.string.settings_language_system) else option.label
                RadioRow(
                    text = label,
                    selected = currentTag == option.tag,
                    onClick = {
                        if (currentTag != option.tag) {
                            saveLanguageTag(context, option.tag)
                            (context as? Activity)?.recreate()
                        }
                    },
                )
            }
        }
    }
}

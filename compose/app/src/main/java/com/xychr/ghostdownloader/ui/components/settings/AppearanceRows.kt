package com.xychr.ghostdownloader.ui.components.settings

import android.app.Activity
import android.os.Build
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.platform.LocalSetThemeMode
import com.xychr.ghostdownloader.ui.platform.ThemeMode
import com.xychr.ghostdownloader.ui.platform.loadLanguageTag
import com.xychr.ghostdownloader.ui.platform.loadThemeMode
import com.xychr.ghostdownloader.ui.platform.saveLanguageTag
import com.xychr.ghostdownloader.ui.platform.systemLanguageName

private val languages = listOf(
    "zh-CN" to "简体中文",
    "zh-TW" to "繁體中文（台灣）",
    "zh-HK" to "繁體中文（香港）",
    "en" to "English",
    "ja" to "日本語",
    "ru" to "Русский",
    "pt-BR" to "Português (Brasil)",
    "es" to "Español",
)

private val themes = listOf(
    ThemeMode.SYSTEM to R.string.settings_theme_system,
    ThemeMode.LIGHT to R.string.settings_theme_light,
    ThemeMode.DARK to R.string.settings_theme_dark,
)

@Composable
fun AppearanceSections() {
    val context = LocalContext.current
    var currentTag by remember { mutableStateOf(loadLanguageTag(context)) }
    var currentTheme by remember { mutableStateOf(loadThemeMode(context)) }
    val setThemeMode = LocalSetThemeMode.current

    fun selectLanguage(tag: String?) {
        if (tag == currentTag) return
        currentTag = tag
        saveLanguageTag(context, tag)
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            (context as? Activity)?.recreate()
        }
    }

    fun selectTheme(mode: ThemeMode) {
        if (mode == currentTheme) return
        currentTheme = mode
        setThemeMode(mode)
    }

    SettingSection(title = stringResource(R.string.settings_theme)) {
        themes.forEach { (mode, labelRes) ->
            RadioSettingRow(
                title = stringResource(labelRes),
                isSelected = currentTheme == mode,
                onClick = { selectTheme(mode) },
            )
        }
    }
    Column(Modifier.selectableGroup()) {
        SettingSection(title = stringResource(R.string.settings_section_language)) {
            RadioSettingRow(
                title = stringResource(R.string.settings_language_system),
                isSelected = currentTag == null,
                onClick = { selectLanguage(null) },
                subtitle = remember { systemLanguageName() },
            )
        }
        SettingSection {
            languages.forEach { (tag, label) ->
                RadioSettingRow(
                    title = label,
                    isSelected = currentTag == tag,
                    onClick = { selectLanguage(tag) },
                )
            }
        }
    }
}

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
import com.xychr.ghostdownloader.ui.platform.ThemeMode
import com.xychr.ghostdownloader.ui.platform.loadLanguageTag
import com.xychr.ghostdownloader.ui.platform.loadThemeMode
import com.xychr.ghostdownloader.ui.platform.saveLanguageTag
import com.xychr.ghostdownloader.ui.platform.saveThemeMode
import com.xychr.ghostdownloader.ui.platform.systemLanguageName

/** 每种语言用它自己的写法标注——用当前界面语言去翻译语言名，找不到母语的人反而选不出来。 */
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

    fun selectLanguage(tag: String?) {
        if (tag == currentTag) return
        currentTag = tag
        saveLanguageTag(context, tag)
        // API 33+ 由系统在 applicationLocales 变更后重建 Activity，这里再调一次会重建两遍
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            (context as? Activity)?.recreate()
        }
    }

    fun selectTheme(mode: ThemeMode) {
        if (mode == currentTheme) return
        currentTheme = mode
        saveThemeMode(context, mode)
        (context as? Activity)?.recreate()
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
    // 单选组跨越两个视觉分区，读屏的「第 n 项，共 9 项」才数得对
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

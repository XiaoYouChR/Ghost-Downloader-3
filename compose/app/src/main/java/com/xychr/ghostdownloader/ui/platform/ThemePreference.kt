package com.xychr.ghostdownloader.ui.platform

import android.content.Context

enum class ThemeMode { SYSTEM, LIGHT, DARK }

private const val PREFS_NAME = "theme"
private const val KEY_MODE = "mode"

fun loadThemeMode(context: Context): ThemeMode {
    val name = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        .getString(KEY_MODE, null)
    return ThemeMode.entries.firstOrNull { it.name == name } ?: ThemeMode.SYSTEM
}

fun saveThemeMode(context: Context, mode: ThemeMode) {
    context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        .edit().putString(KEY_MODE, mode.name).apply()
}

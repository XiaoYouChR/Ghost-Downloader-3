package com.xychr.ghostdownloader.ui.platform

import android.content.Context

private const val PREFS_NAME = "updates"
private const val KEY_IGNORED = "ignoredVersion"

fun loadIgnoredUpdateVersion(context: Context): String? =
    context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).getString(KEY_IGNORED, null)

fun saveIgnoredUpdateVersion(context: Context, version: String) {
    context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        .edit().putString(KEY_IGNORED, version).apply()
}

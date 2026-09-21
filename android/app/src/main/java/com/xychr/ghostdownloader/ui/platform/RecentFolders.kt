package com.xychr.ghostdownloader.ui.platform

import android.content.Context

private const val PREFS_NAME = "folders"
private const val KEY_RECENT = "recent"
private const val MAX_RECENT_FOLDERS = 20
private const val SEPARATOR = "\n"

fun loadRecentFolders(context: Context): List<String> =
    context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        .getString(KEY_RECENT, "").orEmpty().split(SEPARATOR).filter(String::isNotEmpty)

fun saveRecentFolder(context: Context, path: String) {
    if (path.isEmpty()) return
    val next = (listOf(path) + loadRecentFolders(context).filter { it != path })
        .take(MAX_RECENT_FOLDERS)
    context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        .edit().putString(KEY_RECENT, next.joinToString(SEPARATOR)).apply()
}

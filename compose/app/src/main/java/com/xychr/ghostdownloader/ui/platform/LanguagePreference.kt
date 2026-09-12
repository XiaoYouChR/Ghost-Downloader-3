package com.xychr.ghostdownloader.ui.platform

import android.app.LocaleManager
import android.content.Context
import android.content.res.Configuration
import android.os.Build
import android.os.LocaleList
import java.util.Locale

private const val PREFS_NAME = "language"
private const val KEY_TAG = "tag"

fun loadLanguageTag(context: Context): String? {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        val locales = context.getSystemService(LocaleManager::class.java).applicationLocales
        if (!locales.isEmpty) return locales.get(0)!!.toLanguageTag()
    }
    return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        .getString(KEY_TAG, null)
}

fun saveLanguageTag(context: Context, tag: String?) {
    context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        .edit().apply {
            if (tag == null) remove(KEY_TAG) else putString(KEY_TAG, tag)
        }.apply()

    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        val localeManager = context.getSystemService(LocaleManager::class.java)
        localeManager.applicationLocales = if (tag == null) {
            LocaleList.getEmptyLocaleList()
        } else {
            LocaleList.forLanguageTags(tag)
        }
    }
}

fun buildLocalizedContext(base: Context): Context {
    val tag = base.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        .getString(KEY_TAG, null) ?: return base
    val locale = Locale.forLanguageTag(tag)
    Locale.setDefault(locale)
    val config = Configuration(base.resources.configuration)
    config.setLocale(locale)
    config.setLocales(LocaleList(locale))
    return base.createConfigurationContext(config)
}

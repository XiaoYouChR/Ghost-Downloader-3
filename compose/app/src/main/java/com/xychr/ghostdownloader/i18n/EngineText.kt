package com.xychr.ghostdownloader.i18n

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource

@Composable
fun engineText(template: String, params: Map<String, String>): String {
    val text = engineStrings[template]?.let { stringResource(it) } ?: template
    return params.entries.fold(text) { acc, (name, value) -> acc.replace("{$name}", value) }
}

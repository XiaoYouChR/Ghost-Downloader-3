package com.xychr.ghostdownloader.ui.components.settings

import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color

val LocalSettingsAnchor = compositionLocalOf<String?> { null }

data class SettingsAnchor(
    val modifier: Modifier = Modifier,
    val containerColor: Color? = null,
)

@Composable
fun settingsAnchor(title: String): SettingsAnchor {
    if (LocalSettingsAnchor.current != title) return SettingsAnchor()
    val requester = remember { BringIntoViewRequester() }
    LaunchedEffect(title) { requester.bringIntoView() }
    return SettingsAnchor(
        modifier = Modifier.bringIntoViewRequester(requester),
        containerColor = MaterialTheme.colorScheme.primaryContainer,
    )
}

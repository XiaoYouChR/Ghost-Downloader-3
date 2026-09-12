package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.packs.PackKeys
import com.xychr.ghostdownloader.packs.PackRegistry
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage

@Composable
fun PackSettingsPage(
    packId: String,
    onBack: () -> Unit,
    viewModel: SettingsViewModel,
) {
    val entry = PackRegistry.entry(packId) ?: return
    val packUi = entry.packUi
    val content = packUi.settingsContent ?: return
    val keys = PackKeys(entry.configClass!!)

    val config by viewModel.config.collectAsStateWithLifecycle()

    SettingsPage(stringResource(packUi.settingsTitle), onBack) {
        config?.let { content(it, keys, viewModel::set) } ?: LoadingRow()
    }
}

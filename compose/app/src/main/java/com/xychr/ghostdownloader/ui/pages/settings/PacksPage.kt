package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.EmptyRow
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsScaffold
import com.xychr.ghostdownloader.packs.PackKeys
import com.xychr.ghostdownloader.packs.PackRegistry
import com.xychr.ghostdownloader.packs.has
import com.xychr.ghostdownloader.ui.navigation.PackInfoRoute
import com.xychr.ghostdownloader.ui.navigation.PackSettingsRoute
import com.xychr.ghostdownloader.ui.navigation.Route
import kotlinx.serialization.json.JsonObject

@Composable
fun PacksPage(
    onNavigate: (Route) -> Unit,
    onBack: () -> Unit,
    viewModel: SettingsViewModel,
) {
    val config by viewModel.config.collectAsStateWithLifecycle()

    SettingsScaffold(stringResource(R.string.settings_section_packs), onBack) {
        config?.let { PackRows(it, onNavigate) } ?: LoadingRow()
    }
}

@Composable
private fun ColumnScope.PackRows(config: JsonObject, onNavigate: (Route) -> Unit) {
    val packs = PackRegistry.withSettings()
        .filter { config.has(PackKeys(it.configClass!!)) }

    SettingSection {
        ActionSettingRow(
            title = stringResource(R.string.settings_pack_info),
            onClick = { onNavigate(PackInfoRoute) },
            trailing = {
                Icon(
                    painterResource(R.drawable.ic_chevron_right),
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            },
        )
    }

    if (packs.isEmpty()) {
        EmptyRow(stringResource(R.string.settings_packs_empty))
        return
    }

    SettingSection {
        packs.forEach { entry ->
            ActionSettingRow(
                title = stringResource(entry.packUi.settingsTitle),
                onClick = { onNavigate(PackSettingsRoute(entry.packUi.packId)) },
                trailing = {
                    Icon(
                        painterResource(R.drawable.ic_chevron_right),
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                },
            )
        }
    }
}

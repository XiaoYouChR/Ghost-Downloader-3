package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.ActionSettingRow
import com.xychr.ghostdownloader.ui.components.settings.EmptyRow
import com.xychr.ghostdownloader.ui.components.settings.LoadingRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsPage
import com.xychr.ghostdownloader.engine.EngineRepository
import com.xychr.ghostdownloader.packs.PackKeys
import com.xychr.ghostdownloader.packs.PackRegistry
import com.xychr.ghostdownloader.packs.has
import com.xychr.ghostdownloader.ui.navigation.PackInfoRoute
import com.xychr.ghostdownloader.ui.navigation.PackSettingsRoute
import com.xychr.ghostdownloader.ui.navigation.Route
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Composable
fun PacksPage(
    onNavigate: (Route) -> Unit,
    onBack: () -> Unit,
    viewModel: SettingsViewModel,
) {
    val config by viewModel.config.collectAsStateWithLifecycle()

    SettingsPage(stringResource(R.string.settings_section_packs), onBack) {
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

@Serializable
private data class PackInfo(
    val packId: String = "",
    val name: String = "",
    val version: String = "",
)

@Composable
fun PackInfoPage(onBack: () -> Unit) {
    val packs = produceState<List<PackInfo>>(emptyList()) {
        value = runCatching {
            EngineRepository.query<List<PackInfo>>("packInfos")
        }.getOrDefault(emptyList())
    }

    SettingsPage(stringResource(R.string.settings_pack_info), onBack) {
        if (packs.value.isEmpty()) {
            EmptyRow(stringResource(R.string.settings_packs_empty))
        } else {
            SettingSection {
                packs.value.forEach { pack ->
                    PackInfoRow(pack)
                }
            }
        }
    }
}

@Composable
private fun PackInfoRow(pack: PackInfo) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                text = pack.name,
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(
                text = pack.packId,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Text(
            text = "v${pack.version}",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

package com.xychr.ghostdownloader.ui.pages.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.components.settings.EmptyRow
import com.xychr.ghostdownloader.ui.components.settings.SettingSection
import com.xychr.ghostdownloader.ui.components.settings.SettingsScaffold
import com.xychr.ghostdownloader.engine.EngineRepository
import kotlinx.serialization.Serializable

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

    SettingsScaffold(stringResource(R.string.settings_pack_info), onBack) {
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

package com.xychr.ghostdownloader.ui.components.liquid

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.kyant.backdrop.Backdrop
import com.xychr.ghostdownloader.R

enum class BottomTab { TASKS, SETTINGS }

@Composable
fun LiquidBottomBar(
    selectedTab: BottomTab,
    onTabSelected: (BottomTab) -> Unit,
    backdrop: Backdrop,
    modifier: Modifier = Modifier,
) {
    val labels = listOf(stringResource(R.string.nav_tasks), stringResource(R.string.nav_settings))
    Box(modifier.fillMaxWidth(), contentAlignment = Alignment.BottomCenter) {
        LiquidBottomTabs(
            selectedTabIndex = { selectedTab.ordinal },
            onTabSelected = { onTabSelected(BottomTab.entries[it]) },
            backdrop = backdrop,
            tabLabels = labels,
            modifier = Modifier
                .padding(horizontal = 24.dp)
                .padding(bottom = 8.dp)
                .widthIn(max = 440.dp)
                .fillMaxWidth(if (LocalDensity.current.fontScale > 1.3f) 1f else 0.8f),
        ) {
            BottomTab.entries.forEach { tab ->
                val isSelected = tab == selectedTab
                val iconRes = when (tab) {
                    BottomTab.TASKS -> if (isSelected) R.drawable.ic_home_filled else R.drawable.ic_home
                    BottomTab.SETTINGS -> if (isSelected) R.drawable.ic_settings_filled else R.drawable.ic_settings
                }
                LiquidBottomTab {
                    Icon(
                        painterResource(iconRes),
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(24.dp),
                    )
                    Text(
                        labels[tab.ordinal],
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.labelSmall,
                        textAlign = TextAlign.Center,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

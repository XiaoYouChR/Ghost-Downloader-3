package com.xychr.ghostdownloader.ui.components.task

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.PlainTooltip
import androidx.compose.material3.Text
import androidx.compose.material3.TooltipAnchorPosition
import androidx.compose.material3.TooltipBox
import androidx.compose.material3.TooltipDefaults
import androidx.compose.material3.rememberTooltipState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskIconButton(icon: Int, label: String, isEnabled: Boolean = true, onClick: () -> Unit) {
    TooltipBox(
        positionProvider = TooltipDefaults.rememberTooltipPositionProvider(TooltipAnchorPosition.Above),
        tooltip = { PlainTooltip { Text(label) } },
        state = rememberTooltipState(),
    ) {
        IconButton(onClick, enabled = isEnabled, modifier = Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp)) {
            Icon(painterResource(icon), label)
        }
    }
}

@Composable
fun TaskMenuItem(
    label: String,
    icon: Int,
    isEnabled: Boolean = true,
    onClick: () -> Unit,
) {
    DropdownMenuItem(
        text = { Text(label) },
        leadingIcon = { Icon(painterResource(icon), null) },
        enabled = isEnabled,
        onClick = onClick,
    )
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun ExpandChevron(isExpanded: Boolean, modifier: Modifier = Modifier) {
    val rotation by animateFloatAsState(
        targetValue = if (isExpanded) 270f else 90f,
        animationSpec = MaterialTheme.motionScheme.fastSpatialSpec<Float>(),
        label = "chevron-rotation",
    )
    Icon(
        painter = painterResource(R.drawable.ic_chevron_right),
        contentDescription = null,
        modifier = modifier.size(20.dp).graphicsLayer { rotationZ = rotation },
        tint = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

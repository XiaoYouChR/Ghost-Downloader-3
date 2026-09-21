package com.xychr.ghostdownloader.ui.components.liquid

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.FloatingActionButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.util.lerp
import com.kyant.backdrop.Backdrop
import com.kyant.backdrop.drawBackdrop
import com.kyant.backdrop.effects.blur
import com.kyant.backdrop.effects.colorControls
import com.kyant.backdrop.effects.lens
import com.kyant.backdrop.highlight.Highlight
import com.xychr.ghostdownloader.R
import kotlin.math.sign

@Composable
fun LiquidAddButton(
    onClick: () -> Unit,
    backdrop: Backdrop,
    modifier: Modifier = Modifier,
) {
    val interaction = remember { MutableInteractionSource() }
    val isPressed by interaction.collectIsPressedAsState()
    val press by animateFloatAsState(
        targetValue = if (isPressed) 1f else 0f,
        animationSpec = spring(dampingRatio = 0.7f, stiffness = 500f),
        label = "add button press",
    )
    val isLightTheme = MaterialTheme.colorScheme.surface.luminance() > 0.5f
    val l = ((if (isLightTheme) 0.58f else 0.42f) * 2f - 1f).let { sign(it) * it * it }
    val containerColor = (if (isLightTheme) Color.White else Color.Black).copy(alpha = 0.55f)
    val accentColor = MaterialTheme.colorScheme.primary
    FloatingActionButton(
        onClick = onClick,
        modifier = modifier.drawBackdrop(
            backdrop = backdrop,
            shape = { CircleShape },
            effects = {
                colorControls(
                    brightness = if (l > 0f) lerp(0.1f, 0.5f, l) else lerp(0.1f, -0.2f, -l),
                    contrast = if (l > 0f) lerp(1f, 0f, l) else 1f,
                    saturation = 1.5f,
                )
                blur(6.dp.toPx())
                lens(6.dp.toPx(), size.minDimension * 0.75f,
                    depthEffect = true, chromaticAberration = true)
            },
            highlight = { Highlight.Plain },
            layerBlock = {
                scaleX = 1f - 0.06f * press
                scaleY = 1f - 0.06f * press
            },
            onDrawSurface = {
                drawRect(containerColor)
                drawRect(accentColor.copy(alpha = 0.08f + 0.06f * press.coerceIn(0f, 1f)))
            },
        ),
        shape = CircleShape,
        containerColor = Color.Transparent,
        contentColor = MaterialTheme.colorScheme.onSurface,
        elevation = FloatingActionButtonDefaults.elevation(0.dp, 0.dp, 0.dp, 0.dp),
        interactionSource = interaction,
    ) {
        Icon(painterResource(R.drawable.ic_add), stringResource(R.string.task_add))
    }
}

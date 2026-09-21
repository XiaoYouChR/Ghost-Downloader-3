// SPDX-License-Identifier: Apache-2.0
// Based on AndroidLiquidGlass 2.0.0 by Kyant0 — modified.
// Original: catalog/components/LiquidBottomTabs.kt, LiquidBottomTab.kt
package com.xychr.ghostdownloader.ui.components.liquid

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.EaseOut
import androidx.compose.animation.core.spring
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.snapshots.Snapshot
import androidx.compose.runtime.snapshotFlow
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.toRect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.Paint
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.util.fastCoerceIn
import androidx.compose.ui.util.fastRoundToInt
import androidx.compose.ui.util.lerp
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.graphics.luminance
import com.kyant.backdrop.Backdrop
import com.kyant.backdrop.backdrops.layerBackdrop
import com.kyant.backdrop.backdrops.rememberCombinedBackdrop
import com.kyant.backdrop.backdrops.rememberLayerBackdrop
import com.kyant.backdrop.drawBackdrop
import com.kyant.backdrop.effects.blur
import com.kyant.backdrop.effects.colorControls
import com.kyant.backdrop.effects.lens
import com.kyant.backdrop.highlight.Highlight
import com.kyant.backdrop.shadow.InnerShadow
import com.kyant.backdrop.shadow.Shadow
import kotlin.math.abs
import kotlin.math.sign
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

internal val LocalLiquidBottomTabScale = staticCompositionLocalOf { { 1f } }

@Composable
internal fun LiquidBottomTabs(
    selectedTabIndex: () -> Int,
    onTabSelected: (index: Int) -> Unit,
    backdrop: Backdrop,
    tabLabels: List<String>,
    modifier: Modifier = Modifier,
    content: @Composable RowScope.() -> Unit,
) {
    val tabsCount = tabLabels.size
    val isLightTheme = MaterialTheme.colorScheme.surface.luminance() > 0.5f
    val accentColor = MaterialTheme.colorScheme.primary
    val containerColor = (if (isLightTheme) Color.White else Color.Black).copy(alpha = 0.55f)

    val l = ((if (isLightTheme) 0.58f else 0.42f) * 2f - 1f).let { sign(it) * it * it }
    val glassBrightness = if (l > 0f) lerp(0.1f, 0.5f, l) else lerp(0.1f, -0.2f, -l)
    val glassContrast = if (l > 0f) lerp(1f, 0f, l) else 1f

    val tabsBackdrop = rememberLayerBackdrop()

    BoxWithConstraints(
        modifier,
        contentAlignment = Alignment.CenterStart,
    ) {
        val density = LocalDensity.current
        val barHeight = maxOf(64.dp, 48.dp + with(density) { MaterialTheme.typography.labelSmall.lineHeight.toDp() })
        val tabWidth = with(density) {
            (constraints.maxWidth.toFloat() - 8f.dp.toPx()) / tabsCount
        }

        val offsetAnimation = remember { Animatable(0f) }
        val panelOffset by remember(density, constraints.maxWidth) {
            derivedStateOf {
                val fraction = (offsetAnimation.value / constraints.maxWidth).fastCoerceIn(-1f, 1f)
                with(density) {
                    4f.dp.toPx() * fraction.sign * EaseOut.transform(abs(fraction))
                }
            }
        }

        val isLtr = LocalLayoutDirection.current == LayoutDirection.Ltr
        val animationScope = rememberCoroutineScope()
        val currentSelectedTabIndex by rememberUpdatedState(selectedTabIndex)
        val currentOnTabSelected by rememberUpdatedState(onTabSelected)
        val drag = remember(animationScope, tabWidth, isLtr) {
            LiquidDrag(
                animationScope = animationScope,
                // withoutReadObservation: 玻璃绘制层不订阅 Tab 状态，由下方 snapshotFlow 驱动。
                initialValue = Snapshot.withoutReadObservation {
                    currentSelectedTabIndex().toFloat()
                },
                valueRange = 0f..(tabsCount - 1).toFloat(),
                visibilityThreshold = 0.001f,
                initialScale = 1f,
                pressedScale = 78f / 56f,
                onDragStarted = {},
                onDragCancelled = {
                    updateTarget(currentSelectedTabIndex().toFloat())
                    animationScope.launch { offsetAnimation.animateTo(0f, spring(1f, 300f, 0.5f)) }
                },
                onDragStopped = {
                    val targetIndex = targetValue.fastRoundToInt().fastCoerceIn(0, tabsCount - 1)
                    updateTarget(targetIndex.toFloat())
                    currentOnTabSelected(targetIndex)
                    animationScope.launch {
                        offsetAnimation.animateTo(
                            0f,
                            spring(1f, 300f, 0.5f),
                        )
                    }
                },
                onDrag = { _, dragAmount ->
                    updateValue(
                        (targetValue + dragAmount.x / tabWidth * if (isLtr) 1f else -1f)
                            .fastCoerceIn(0f, (tabsCount - 1).toFloat()),
                    )
                    animationScope.launch {
                        offsetAnimation.snapTo(offsetAnimation.value + dragAmount.x)
                    }
                },
            )
        }
        // 单向驱动：主壳状态 → 气泡，不回写，避免快速切换时索引互相覆盖。
        LaunchedEffect(drag) {
            snapshotFlow { currentSelectedTabIndex() }
                .collectLatest { index ->
                    drag.updateTarget(
                        index.fastCoerceIn(0, tabsCount - 1).toFloat(),
                    )
                }
        }

        val highlight = remember(drag, isLtr) {
            LiquidHighlight(
                animationScope = animationScope,
                position = { size, _ ->
                    Offset(
                        if (isLtr) (drag.value + 0.5f) * tabWidth + panelOffset
                        else size.width - (drag.value + 0.5f) * tabWidth + panelOffset,
                        size.height / 2f,
                    )
                },
            )
        }

        Row(
            Modifier
                .clearAndSetSemantics {}
                .graphicsLayer {
                    translationX = panelOffset
                }
                .drawBackdrop(
                    backdrop = backdrop,
                    shape = { CircleShape },
                    effects = {
                        colorControls(
                            brightness = glassBrightness,
                            contrast = glassContrast,
                            saturation = 1.5f,
                        )
                        blur(6.dp.toPx())
                        lens(
                            6.dp.toPx(),
                            size.minDimension * 0.75f,
                            depthEffect = true,
                            chromaticAberration = true,
                        )
                    },
                    highlight = { Highlight.Plain },
                    layerBlock = {
                        val progress = drag.pressProgress
                        val scale = lerp(1f, 1f + 16f.dp.toPx() / size.width, progress)
                        scaleX = scale
                        scaleY = scale
                    },
                    onDrawSurface = { drawRect(containerColor) },
                )
                .then(highlight.modifier)
                .height(barHeight)
                .fillMaxWidth()
                .padding(4f.dp),
            verticalAlignment = Alignment.CenterVertically,
            content = content,
        )

        // 强调色克隆层：alpha(0f) 不可见，录制进 tabsBackdrop，透过选中气泡透出。
        CompositionLocalProvider(
            LocalLiquidBottomTabScale provides {
                lerp(1f, 1.2f, drag.pressProgress)
            },
        ) {
            Row(
                Modifier
                    .clearAndSetSemantics {}
                    .alpha(0f)
                    .layerBackdrop(tabsBackdrop)
                    .graphicsLayer {
                        translationX = panelOffset
                    }
                    .drawBackdrop(
                        backdrop = backdrop,
                        shape = { CircleShape },
                        effects = {
                            val progress = drag.pressProgress
                            colorControls(
                                brightness = glassBrightness,
                                contrast = glassContrast,
                                saturation = 1.5f,
                            )
                            blur(6.dp.toPx())
                            lens(
                                6.dp.toPx() * progress,
                                size.minDimension *
                                    0.75f * progress,
                                depthEffect = true,
                                chromaticAberration = true,
                            )
                        },
                        highlight = {
                            val progress = drag.pressProgress
                            Highlight.Default.copy(alpha = progress)
                        },
                        onDrawSurface = { drawRect(containerColor) },
                    )
                    .then(highlight.modifier)
                    .height(barHeight - 8.dp)
                    .fillMaxWidth()
                    .padding(horizontal = 4f.dp)
                    .toColorFilterLayer(ColorFilter.tint(accentColor)),
                verticalAlignment = Alignment.CenterVertically,
                content = content,
            )
        }

        Box(
            Modifier
                .padding(horizontal = 4f.dp)
                .graphicsLayer {
                    translationX =
                        if (isLtr) drag.value * tabWidth + panelOffset
                        else size.width - (drag.value + 1f) * tabWidth + panelOffset
                }
                .drawBackdrop(
                    backdrop = rememberCombinedBackdrop(backdrop, tabsBackdrop),
                    shape = { CircleShape },
                    effects = {
                        val progress = drag.pressProgress
                        lens(
                            10f.dp.toPx() * progress,
                            14f.dp.toPx() * progress,
                            chromaticAberration = true,
                        )
                    },
                    highlight = {
                        val progress = drag.pressProgress
                        Highlight.Default.copy(alpha = progress)
                    },
                    shadow = {
                        val progress = drag.pressProgress
                        Shadow(alpha = progress)
                    },
                    innerShadow = {
                        val progress = drag.pressProgress
                        InnerShadow(
                            radius = 8f.dp * progress,
                            alpha = progress,
                        )
                    },
                    layerBlock = {
                        scaleX = drag.scaleX
                        scaleY = drag.scaleY
                        val velocity = drag.velocity / 10f
                        scaleX /= 1f - (velocity * 0.75f).fastCoerceIn(-0.2f, 0.2f)
                        scaleY *= 1f - (velocity * 0.25f).fastCoerceIn(-0.2f, 0.2f)
                    },
                    onDrawSurface = {
                        val progress = drag.pressProgress
                        drawRect(
                            if (isLightTheme) Color.Black.copy(0.1f)
                            else Color.White.copy(0.1f),
                            alpha = 1f - progress,
                        )
                        drawRect(Color.Black.copy(alpha = 0.03f * progress))
                    },
                )
                .height(barHeight - 8.dp)
                .fillMaxWidth(1f / tabsCount),
        )

        LiquidTabHitTargets(
            selectedTabIndex = currentSelectedTabIndex,
            tabLabels = tabLabels,
            onTabSelected = currentOnTabSelected,
            barHeight = barHeight,
            modifier = highlight.gestureModifier.then(drag.modifier),
        )
    }
}

// Stable hit targets stay above the transformed lens; only the selected target handles dragging.
@Composable
private fun LiquidTabHitTargets(
    selectedTabIndex: () -> Int,
    tabLabels: List<String>,
    onTabSelected: (Int) -> Unit,
    barHeight: Dp,
    modifier: Modifier = Modifier,
) {
    val selectedIndex = selectedTabIndex()
    Row(
        Modifier.height(barHeight).fillMaxWidth().padding(4.dp).selectableGroup(),
    ) {
        tabLabels.forEachIndexed { index, label ->
            Box(
                Modifier
                    .fillMaxHeight()
                    .weight(1f)
                    .selectable(
                        selected = index == selectedIndex,
                        interactionSource = null,
                        indication = null,
                        role = Role.Tab,
                        onClick = { onTabSelected(index) },
                    )
                    .semantics { contentDescription = label }
                    .then(if (index == selectedIndex) modifier else Modifier),
            )
        }
    }
}

@Composable
internal fun RowScope.LiquidBottomTab(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    val scale = LocalLiquidBottomTabScale.current
    Column(
        modifier
            .clip(CircleShape)
            .fillMaxHeight()
            .weight(1f)
            .graphicsLayer {
                val scale = scale()
                scaleX = scale
                scaleY = scale
            },
        verticalArrangement = Arrangement.spacedBy(2f.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
        content = content,
    )
}

private fun Modifier.toColorFilterLayer(colorFilter: ColorFilter): Modifier = drawWithCache {
    val paint = Paint().apply { this.colorFilter = colorFilter }
    onDrawWithContent {
        drawIntoCanvas { canvas ->
            canvas.saveLayer(size.toRect(), paint)
            drawContent()
            canvas.restore()
        }
    }
}

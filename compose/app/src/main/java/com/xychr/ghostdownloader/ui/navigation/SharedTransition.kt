package com.xychr.ghostdownloader.ui.navigation

import androidx.compose.animation.AnimatedVisibilityScope
import androidx.compose.animation.ExperimentalSharedTransitionApi
import androidx.compose.animation.SharedTransitionScope
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.Modifier

/**
 * Container transform 要同时拿到 SharedTransitionLayout 和当前目标的 AnimatedVisibilityScope。
 * 把这两个 scope 逐层当参数传会污染每个屏幕的签名，所以走 CompositionLocal——
 * 这也是官方 navigation + shared element 示例的做法。
 */
val LocalSharedTransitionScope = compositionLocalOf<SharedTransitionScope?> { null }
val LocalNavAnimatedVisibilityScope = compositionLocalOf<AnimatedVisibilityScope?> { null }

/** FAB 与新建页两端共用，任务卡片的 key 由 taskId 拼出所以不在这里 */
const val DRAFT_CONTAINER = "draft"

/**
 * 给参与 container transform 的元素打标记。两端用同一个 key 就会互相变形。
 * 两个 scope 任一缺席（比如预览环境）时退化成无动画，不影响布局。
 */
@OptIn(ExperimentalSharedTransitionApi::class)
@Composable
fun Modifier.sharedContainer(key: String): Modifier {
    val transition = LocalSharedTransitionScope.current ?: return this
    val visibility = LocalNavAnimatedVisibilityScope.current ?: return this

    return with(transition) {
        this@sharedContainer.sharedBounds(
            rememberSharedContentState(key),
            animatedVisibilityScope = visibility,
        )
    }
}

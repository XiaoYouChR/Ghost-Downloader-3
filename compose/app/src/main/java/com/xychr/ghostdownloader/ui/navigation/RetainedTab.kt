package com.xychr.ghostdownloader.ui.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.Layout
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.compose.LocalLifecycleOwner

private class TabState : LifecycleOwner {
    var hasVisited = false
    override val lifecycle = LifecycleRegistry(this)
}

@Composable
internal fun RetainedTab(
    isActive: Boolean,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    val parent = LocalLifecycleOwner.current.lifecycle
    val state = remember(parent) { TabState() }
    val updateLifecycle by rememberUpdatedState {
        state.lifecycle.currentState = minOf(
            parent.currentState,
            if (isActive) Lifecycle.State.RESUMED else Lifecycle.State.CREATED,
        )
    }
    DisposableEffect(parent, state) {
        val observer = LifecycleEventObserver { _, _ -> updateLifecycle() }
        parent.addObserver(observer)
        onDispose {
            parent.removeObserver(observer)
            state.lifecycle.currentState = Lifecycle.State.DESTROYED
        }
    }
    SideEffect { updateLifecycle() }

    if (isActive) state.hasVisited = true
    if (!state.hasVisited) return

    // Retain state without paying hidden measure/lookahead work when the active flow navigates.
    CompositionLocalProvider(LocalLifecycleOwner provides state) {
        Layout(
            content = { Box { content() } },
            modifier = modifier,
        ) { measurables, constraints ->
            if (isActive) {
                val placeable = measurables.single().measure(constraints)
                layout(placeable.width, placeable.height) { placeable.place(0, 0) }
            } else {
                layout(constraints.minWidth, constraints.minHeight) {}
            }
        }
    }
}

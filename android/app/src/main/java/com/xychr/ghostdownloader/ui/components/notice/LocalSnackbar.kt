package com.xychr.ghostdownloader.ui.components.notice

import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.staticCompositionLocalOf

val LocalSnackbar = staticCompositionLocalOf<SnackbarHostState> {
    error("LocalSnackbar 未提供")
}

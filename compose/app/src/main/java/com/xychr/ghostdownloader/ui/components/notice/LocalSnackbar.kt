package com.xychr.ghostdownloader.ui.components.notice

import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.staticCompositionLocalOf

/**
 * Snackbar 同一时刻只能有一条，所以全应用共用一个 host——
 * 每页各自 remember 一个会得到三个互不知情的队列，切页时消息会丢或叠。
 */
val LocalSnackbar = staticCompositionLocalOf<SnackbarHostState> {
    error("LocalSnackbar 未提供")
}

package com.xychr.ghostdownloader.ui.navigation

import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.AnimatedContentTransitionScope.SlideDirection
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import kotlinx.serialization.Serializable

sealed interface Route

@Serializable
enum class DraftPart { Summary, Files, Media, Subtitles, Trim }

private const val navigationDurationMillis = 300

val navEnterTransition: AnimatedContentTransitionScope<*>.() -> EnterTransition = {
    fadeIn(tween(navigationDurationMillis)) + slideIntoContainer(SlideDirection.Start, tween(navigationDurationMillis))
}
val navExitTransition: AnimatedContentTransitionScope<*>.() -> ExitTransition = {
    fadeOut(tween(navigationDurationMillis)) + slideOutOfContainer(SlideDirection.Start, tween(navigationDurationMillis))
}
val navPopEnterTransition: AnimatedContentTransitionScope<*>.() -> EnterTransition = {
    fadeIn(tween(navigationDurationMillis)) + slideIntoContainer(SlideDirection.End, tween(navigationDurationMillis))
}
val navPopExitTransition: AnimatedContentTransitionScope<*>.() -> ExitTransition = {
    fadeOut(tween(navigationDurationMillis)) + slideOutOfContainer(SlideDirection.End, tween(navigationDurationMillis))
}

@Serializable data object TasksRoute : Route
@Serializable data object SettingsRoute : Route

// 任务
@Serializable data object DraftRoute : Route
@Serializable data class TaskDetailRoute(val taskId: String) : Route
@Serializable data class TaskFilesRoute(val taskId: String) : Route
@Serializable data class TaskEditRoute(val taskId: String) : Route
@Serializable data class DraftEditRoute(
    val url: String,
    val part: DraftPart = DraftPart.Summary,
) : Route

// 设置分类
@Serializable data object DownloadSettingsRoute : Route
@Serializable data object NetworkSettingsRoute : Route
@Serializable data object IdentitySettingsRoute : Route
@Serializable data object IdentityRulesRoute : Route
@Serializable data object HeadersPresetsRoute : Route
@Serializable data object ClientProfileRoute : Route
@Serializable data object ProxySettingsRoute : Route
@Serializable data object ServiceSettingsRoute : Route
@Serializable data object PacksSettingsRoute : Route
@Serializable data object PackInfoRoute : Route
@Serializable data object RuntimesSettingsRoute : Route
@Serializable data object PermissionsSettingsRoute : Route
@Serializable data object AboutSettingsRoute : Route
@Serializable data object LanguageSettingsRoute : Route
@Serializable data class PackSettingsRoute(val pack: String) : Route

// 分类管理。categoryId 为空表示新建
@Serializable data class CategorySettingsRoute(val returnToTasks: Boolean = false) : Route
@Serializable data class CategoryEditRoute(val categoryId: String = "") : Route

// 身份模拟。index 为 -1 表示新建
@Serializable data class IdentityPresetEditRoute(val index: Int = -1) : Route
@Serializable data class HeadersPresetEditRoute(val index: Int = -1, val copyFrom: Int = -1) : Route

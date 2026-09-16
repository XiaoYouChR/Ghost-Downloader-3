package com.xychr.ghostdownloader.ui.navigation

import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.AnimatedContentTransitionScope.SlideDirection
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import com.xychr.ghostdownloader.ui.theme.EmphasizedAccelerate
import com.xychr.ghostdownloader.ui.theme.EmphasizedDecelerate
import kotlinx.serialization.Serializable

sealed interface Route

const val EXTRA_DESTINATION = "destination"
const val DESTINATION_DRAFT = "draft"

private const val TASK_PREFIX = "task:"

fun toDestination(taskId: String) = TASK_PREFIX + taskId

fun toRoute(destination: String): Route =
    if (destination == DESTINATION_DRAFT) DraftRoute
    else TaskDetailRoute(destination.removePrefix(TASK_PREFIX))

val navEnterTransition: AnimatedContentTransitionScope<*>.() -> EnterTransition = {
    fadeIn(tween(400, easing = EmphasizedDecelerate)) +
        slideIntoContainer(SlideDirection.Start, tween(400, easing = EmphasizedDecelerate))
}
val navExitTransition: AnimatedContentTransitionScope<*>.() -> ExitTransition = {
    fadeOut(tween(200, easing = EmphasizedAccelerate)) +
        slideOutOfContainer(SlideDirection.Start, tween(200, easing = EmphasizedAccelerate))
}
val navPopEnterTransition: AnimatedContentTransitionScope<*>.() -> EnterTransition = {
    fadeIn(tween(400, easing = EmphasizedDecelerate)) +
        slideIntoContainer(SlideDirection.End, tween(400, easing = EmphasizedDecelerate))
}
val navPopExitTransition: AnimatedContentTransitionScope<*>.() -> ExitTransition = {
    fadeOut(tween(200, easing = EmphasizedAccelerate)) +
        slideOutOfContainer(SlideDirection.End, tween(200, easing = EmphasizedAccelerate))
}

@Serializable data object TasksRoute : Route
@Serializable data object SettingsRoute : Route

// 任务
@Serializable data object DraftRoute : Route
@Serializable data class DraftEditRoute(val url: String) : Route
@Serializable data class TaskDetailRoute(val taskId: String) : Route
@Serializable data class TaskFilesRoute(val taskId: String) : Route
@Serializable data class TaskEditRoute(val taskId: String) : Route
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

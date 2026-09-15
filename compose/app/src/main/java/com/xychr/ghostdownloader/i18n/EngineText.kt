package com.xychr.ghostdownloader.i18n

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import com.xychr.ghostdownloader.model.TaskError

/**
 * 引擎存的是机器可读的消息模板（同时作为 i18n key），翻译发生在这里。
 * 通知在 Composition 之外构建，所以真正的实现挂在 Context 上，@Composable 版只是入口。
 */
fun Context.engineText(template: String, params: Map<String, String>): String {
    val text = engineStrings[template]?.let(::getString) ?: template
    return params.entries.fold(text) { acc, (name, value) -> acc.replace("{$name}", value) }
}

@Composable
fun engineText(template: String, params: Map<String, String>): String =
    LocalContext.current.engineText(template, params)

fun Context.engineText(error: TaskError): String = engineText(error.message, error.params)

@Composable
fun engineText(error: TaskError): String = LocalContext.current.engineText(error)

fun Context.engineText(error: Throwable): String = engineText(error.toTaskError())

fun Throwable.toTaskError(): TaskError {
    val raw = message.orEmpty()
    val stripped = raw.substringAfter(": ", raw)
    if (engineStrings.containsKey(stripped)) return TaskError(stripped)
    return TaskError("发生了意外错误：{detail}", mapOf("detail" to raw.ifEmpty { this::class.simpleName.orEmpty() }))
}

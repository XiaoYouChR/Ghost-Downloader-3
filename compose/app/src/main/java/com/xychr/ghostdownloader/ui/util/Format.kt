package com.xychr.ghostdownloader.ui.util

fun formatTimestamp(epoch: Long): String {
    if (epoch <= 0) return ""
    val instant = java.time.Instant.ofEpochSecond(epoch)
    val local = java.time.LocalDateTime.ofInstant(instant, java.time.ZoneId.systemDefault())
    return local.format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"))
}

fun formatSpeed(bytesPerSec: Long): String {
    if (bytesPerSec <= 0) return ""
    val kb = bytesPerSec / 1024.0
    if (kb < 1024) return "%.1f KB/s".format(kb)
    return "%.1f MB/s".format(kb / 1024.0)
}

fun formatSize(bytes: Long): String {
    if (bytes <= 0) return "0 B"
    val units = listOf("B", "KB", "MB", "GB", "TB")
    var value = bytes.toDouble()
    var unit = 0
    while (value >= 1024 && unit < units.lastIndex) {
        value /= 1024
        unit++
    }
    return if (unit == 0) "${value.toInt()} B" else "%.1f %s".format(value, units[unit])
}

/** 文件大小未知时引擎送的是负数哨兵值，画成 -- 而不是编一个数字出来。 */
fun formatSizeProgress(received: Long, total: Long): String =
    if (total > 0) "${formatSize(received)}/${formatSize(total)}"
    else "${formatSize(received)}/--"

fun formatDuration(seconds: Long): String {
    val h = seconds / 3600
    val m = seconds % 3600 / 60
    val s = seconds % 60
    return when {
        h > 0 -> "%d:%02d:%02d".format(h, m, s)
        else -> "%d:%02d".format(m, s)
    }
}

/**
 * formatDuration 的逆。接受 "h:mm:ss"、"m:ss" 和纯秒数，认不出返回 null——
 * 让调用方把非法输入标红，而不是悄悄当成 0。
 */
fun parseDuration(text: String): Int? {
    val parts = text.trim().split(":")
    if (parts.isEmpty() || parts.size > 3) return null
    return parts.fold(0) { acc, part -> acc * 60 + (part.toIntOrNull() ?: return null) }
}

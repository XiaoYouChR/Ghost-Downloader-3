package com.xychr.ghostdownloader.ui.platform

import android.content.ContentResolver
import android.content.Intent
import android.net.Uri
import java.io.File

fun extractUrls(intent: Intent, cacheDir: File, resolver: ContentResolver): List<String> =
    when (intent.action) {
        Intent.ACTION_SEND -> extractFromSend(intent)
        Intent.ACTION_VIEW -> extractFromView(intent, cacheDir, resolver)
        else -> emptyList()
    }

private fun extractFromSend(intent: Intent): List<String> {
    val text = intent.getStringExtra(Intent.EXTRA_TEXT) ?: return emptyList()
    return text.lines().map(String::trim).filter(String::isNotEmpty)
}

private fun extractFromView(
    intent: Intent,
    cacheDir: File,
    resolver: ContentResolver,
): List<String> {
    val uri = intent.data ?: return emptyList()
    if (uri.scheme == "content") return listOfNotNull(copyToCache(uri, cacheDir, resolver))
    return listOf(uri.toString())
}

private fun copyToCache(uri: Uri, cacheDir: File, resolver: ContentResolver): String? {
    val dest = File(cacheDir, "shared_${System.currentTimeMillis()}.torrent")
    resolver.openInputStream(uri)?.use { input ->
        dest.outputStream().use { output -> input.copyTo(output) }
    } ?: return null
    return Uri.fromFile(dest).toString()
}

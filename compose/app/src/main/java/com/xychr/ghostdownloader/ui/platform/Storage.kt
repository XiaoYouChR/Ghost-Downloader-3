package com.xychr.ghostdownloader.ui.platform

import android.net.Uri
import android.os.Environment
import android.provider.DocumentsContract

// SAF content:// → 裸路径；引擎走 java.io.File，写盘靠 MANAGE_EXTERNAL_STORAGE。
fun Uri.toFolderPath(): String {
    val documentId = DocumentsContract.getTreeDocumentId(this)
    val volume = documentId.substringBefore(':')
    val relative = documentId.substringAfter(':', "")
    val base = if (volume == "primary") "/storage/emulated/0" else "/storage/$volume"
    return if (relative.isEmpty()) base else "$base/$relative"
}

fun defaultDownloadFolder(): String =
    Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).absolutePath

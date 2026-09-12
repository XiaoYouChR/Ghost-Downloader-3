package com.xychr.ghostdownloader.ui.platform

import android.content.Context
import android.content.Intent
import android.provider.DocumentsContract
import android.webkit.MimeTypeMap
import androidx.core.content.FileProvider
import com.xychr.ghostdownloader.R
import java.io.File

fun Context.openTaskFile(path: String) {
    val file = File(path)
    if (!file.isFile) {
        android.widget.Toast.makeText(this, R.string.task_file_unavailable, android.widget.Toast.LENGTH_LONG).show()
        return
    }
    try {
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
        val mime = MimeTypeMap.getSingleton()
            .getMimeTypeFromExtension(file.extension.lowercase()) ?: "*/*"
        val isOpened = start(
            Intent(Intent.ACTION_VIEW)
                .setDataAndType(uri, mime)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        )
        if (!isOpened) android.widget.Toast.makeText(this, R.string.task_file_unavailable, android.widget.Toast.LENGTH_LONG).show()
    } catch (error: IllegalArgumentException) {
        android.widget.Toast.makeText(this, R.string.task_file_unavailable, android.widget.Toast.LENGTH_LONG).show()
    }
}

/**
 * 文件管理器打开目录没有统一 Intent：先试 SAF 的目录 URI（系统「文件」应用认这个），
 * 不行再退回让用户自己挑一个能看目录的应用。
 */
fun Context.openFolder(outputFolder: String) {
    val relative = outputFolder.removePrefix(PRIMARY_STORAGE).trim('/')
    val documentUri = DocumentsContract.buildDocumentUri(
        EXTERNAL_STORAGE_AUTHORITY,
        if (relative.isEmpty()) "primary:" else "primary:$relative",
    )

    val open = Intent(Intent.ACTION_VIEW)
        .setDataAndType(documentUri, DocumentsContract.Document.MIME_TYPE_DIR)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    if (start(open)) return

    start(Intent(Intent.ACTION_VIEW).setDataAndType(documentUri, "*/*"))
}

private const val PRIMARY_STORAGE = "/storage/emulated/0"
private const val EXTERNAL_STORAGE_AUTHORITY = "com.android.externalstorage.documents"

private fun Context.start(intent: Intent): Boolean = runCatching {
    startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}.isSuccess

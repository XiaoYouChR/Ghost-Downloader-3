package com.xychr.ghostdownloader.ui.platform

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import android.webkit.MimeTypeMap
import android.widget.Toast
import androidx.core.content.FileProvider
import com.xychr.ghostdownloader.R
import java.io.File

/**
 * 构建与启动分开：通知的动作只能是 PendingIntent，拿不到"启动失败再退回"的机会，
 * 所以"怎么打开一个下载产物"这段知识必须能脱离启动单独取用。
 */
fun Context.taskFileIntent(path: String): Intent? {
    val file = File(path)
    val uri = toContentUri(file) ?: return null
    return Intent(Intent.ACTION_VIEW)
        .setDataAndType(uri, file.toMimeType())
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
}

private fun Context.toContentUri(file: File): Uri? {
    if (!file.isFile) return null
    return try {
        FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
    } catch (error: IllegalArgumentException) {
        null
    }
}

private fun File.toMimeType(): String =
    MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension.lowercase()) ?: "*/*"

/**
 * 文件管理器打开目录没有统一 Intent：系统「文件」应用认 SAF 的目录 URI。
 * 从通知里走只有这一发，从界面里走 openFolder 还会再退回一次通配 MIME。
 */
fun Context.folderIntent(folder: String): Intent {
    val relative = folder.removePrefix(PRIMARY_STORAGE).trim('/')
    val documentUri = DocumentsContract.buildDocumentUri(
        EXTERNAL_STORAGE_AUTHORITY,
        if (relative.isEmpty()) "primary:" else "primary:$relative",
    )
    return Intent(Intent.ACTION_VIEW)
        .setDataAndType(documentUri, DocumentsContract.Document.MIME_TYPE_DIR)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
}

fun Context.openTaskFile(path: String) {
    val intent = taskFileIntent(path)
    if (intent == null || !start(intent)) {
        Toast.makeText(this, R.string.task_file_unavailable, Toast.LENGTH_LONG).show()
    }
}

fun Context.shareTaskFile(path: String): Boolean {
    val file = File(path)
    val uri = toContentUri(file) ?: return false
    val send = Intent(Intent.ACTION_SEND)
        .setType(file.toMimeType())
        .putExtra(Intent.EXTRA_STREAM, uri)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    return start(Intent.createChooser(send, null))
}

fun Context.openFolder(folder: String) {
    val intent = folderIntent(folder)
    if (start(intent)) return
    if (start(Intent(Intent.ACTION_VIEW).setDataAndType(intent.data, "*/*"))) return
    Toast.makeText(this, R.string.task_folder_unavailable, Toast.LENGTH_LONG).show()
}

private const val PRIMARY_STORAGE = "/storage/emulated/0"
private const val EXTERNAL_STORAGE_AUTHORITY = "com.android.externalstorage.documents"

package com.xychr.ghostdownloader.ui.util

import com.xychr.ghostdownloader.R

private val VIDEO = setOf(
    "mp4", "mkv", "avi", "mov", "flv", "webm", "wmv", "ts", "m4v", "mpg", "mpeg", "3gp", "vob",
)
private val AUDIO = setOf(
    "mp3", "flac", "aac", "m4a", "ogg", "wav", "wma", "opus", "ape", "alac",
)
private val IMAGE = setOf(
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "ico", "tiff", "tif", "heic", "avif",
)
private val ARCHIVE = setOf(
    "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "zst", "lz4",
)
private val APPLICATION = setOf(
    "exe", "msi", "apk", "dmg", "deb", "rpm", "appimage", "pkg",
)
private val SUBTITLE = setOf(
    "srt", "ass", "ssa", "vtt", "sub", "idx", "lrc",
)
private val BOOK = setOf(
    "epub", "mobi", "azw", "azw3", "fb2", "djvu", "cbr", "cbz",
)
private val CODE = setOf(
    "py", "js", "ts", "java", "kt", "c", "cpp", "h", "rs", "go", "sh", "bat", "ps1", "rb", "lua",
)

fun fileTypeIconRes(name: String): Int {
    val ext = name.substringAfterLast('.', "").lowercase()
    return when {
        ext in VIDEO -> R.drawable.ic_cat_video
        ext in AUDIO -> R.drawable.ic_cat_music
        ext in IMAGE -> R.drawable.ic_cat_photo
        ext in ARCHIVE -> R.drawable.ic_cat_archive
        ext in APPLICATION -> R.drawable.ic_cat_application
        ext in SUBTITLE -> R.drawable.ic_cat_chat
        ext in BOOK -> R.drawable.ic_cat_book
        ext in CODE -> R.drawable.ic_cat_code
        else -> R.drawable.ic_file
    }
}

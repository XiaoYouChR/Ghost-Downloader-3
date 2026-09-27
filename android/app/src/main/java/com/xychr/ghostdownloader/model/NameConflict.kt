package com.xychr.ghostdownloader.model

import kotlinx.serialization.Serializable

@Serializable
data class NameConflict(
    val taskId: String = "",
    val name: String = "",
    val isFolder: Boolean = false,
    val existingSize: Long = 0,
    val modifiedAt: Long = 0,
    val newSize: Long = 0,
    val restCount: Int = 0,
)

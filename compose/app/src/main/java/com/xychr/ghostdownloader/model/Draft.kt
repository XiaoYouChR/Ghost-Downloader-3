package com.xychr.ghostdownloader.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Serializable
data class DraftFile(
    val index: Int = 0,
    val path: String = "",
    val size: Long = 0,
    val isSelected: Boolean = true,
)

@Serializable
data class DraftOption(val key: String = "", val label: String = "")

@Serializable
data class DraftProjection(
    val items: List<DraftItem> = emptyList(),
    val outputFolder: String = "",
    val subworkerCount: Int = 0,
)

@Serializable
data class DraftItem(
    val url: String = "",
    val isParsing: Boolean = true,
    val name: String = "",
    val categoryChoice: String? = null,
    val categoryId: String = "",
    val outputFolder: String = "",
    val fileSize: Long = 0,
    val files: List<DraftFile> = emptyList(),
    val error: TaskError? = null,
    val canRenameFiles: Boolean = false,
    val canEdit: Boolean = false,
    val packId: String = "",
    val packFields: JsonObject = JsonObject(emptyMap()),
)

@Serializable
data class PreviewSheet(
    val url: String,
    val columns: Int,
    val rows: Int,
    val times: List<Double>,
)

@Serializable
data class DraftPreview(
    val sheets: List<PreviewSheet> = emptyList(),
    val headers: Map<String, String> = emptyMap(),
)

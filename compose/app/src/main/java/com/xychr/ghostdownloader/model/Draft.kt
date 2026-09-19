package com.xychr.ghostdownloader.model

import kotlinx.serialization.Serializable
import androidx.compose.runtime.Immutable
import kotlinx.serialization.json.JsonObject

@Immutable
@Serializable
data class DraftFile(
    val index: Int = 0,
    val path: String = "",
    val groups: List<String> = emptyList(),
    val size: Long = 0,
    val isSelected: Boolean = true,
)

@Serializable
data class DraftOption(val key: String = "", val label: String = "")

data class DraftControl(
    val id: String,
    val options: List<DraftOption>,
    val title: String = "",
    val value: String = "",
    val isMultiple: Boolean = false,
    val isOptional: Boolean = false,
)

@Serializable
data class DraftProjection(
    val items: List<DraftItem> = emptyList(),
    val outputFolder: String = "",
    val subworkerCount: Int = 0,
)

@Immutable
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

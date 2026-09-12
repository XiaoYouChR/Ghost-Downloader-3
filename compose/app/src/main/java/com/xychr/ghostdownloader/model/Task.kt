package com.xychr.ghostdownloader.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

object TaskStatus {
    const val RUNNING = "RUNNING"
    const val WAITING = "WAITING"
    const val PAUSED = "PAUSED"
    const val COMPLETED = "COMPLETED"
    const val FAILED = "FAILED"
}

@Serializable
data class TaskError(
    val message: String,
    val params: Map<String, String> = emptyMap(),
)

@Serializable
data class TaskUiState(
    val id: String = "",
    val packId: String = "",
    val canPause: Boolean = false,
    val canEdit: Boolean = false,
    val categoryId: String = "",
    val outputPath: String = "",
    val hasOutputFile: Boolean = false,
    val selectedFileCount: Int = 0,
    val name: String = "",
    val url: String = "",
    val progress: Double = 0.0,
    val speed: Long = 0,
    val received: Long = 0,
    val status: String = "",
    val fileSize: Long = 0,
    val fileCount: Int = 0,
    val createdAt: Long = 0,
    val completedAt: Long = 0,
    val error: TaskError? = null,
    val progressMode: String = "determinate",
    val statusText: String = "",
    val secondarySpeed: Long = 0,
    val canStop: Boolean = false,
    val packFields: JsonObject = JsonObject(emptyMap()),
)

val TaskUiState.isActive: Boolean
    get() = status != TaskStatus.COMPLETED

val TaskUiState.isFinished: Boolean
    get() = status == TaskStatus.COMPLETED

@Serializable
data class TaskSnapshot(
    val progress: Double = 0.0,
    val speed: Long = 0,
    val received: Long = 0,
)

@Serializable
data class TaskDetail(
    val id: String = "",
    val packId: String = "",
    val canPause: Boolean = false,
    val categoryId: String = "",
    val outputPath: String = "",
    val hasOutputFile: Boolean = false,
    val name: String = "",
    val url: String = "",
    val progress: Double = 0.0,
    val speed: Long = 0,
    val received: Long = 0,
    val status: String = "",
    val fileSize: Long = 0,
    val createdAt: Long = 0,
    val completedAt: Long = 0,
    val canEdit: Boolean = false,
    val canRename: Boolean = false,
    val outputFolder: String = "",
    val error: TaskError? = null,
    val files: List<TaskFile> = emptyList(),
    val progressMode: String = "determinate",
    val statusText: String = "",
    val secondarySpeed: Long = 0,
    val canStop: Boolean = false,
    val packFields: JsonObject = JsonObject(emptyMap()),
)

@Serializable
data class TaskFile(
    val index: Int = 0,
    val categoryId: String = "",
    val path: String = "",
    val size: Long = 0,
    val isSelected: Boolean = true,
    val isCompleted: Boolean = false,
    val progress: Double = 0.0,
)

package com.xychr.ghostdownloader.model

import kotlinx.serialization.Serializable

@Serializable
data class Category(
    val categoryId: String = "",
    val name: String = "",
    val icon: String = "DOCUMENT",
    val extensions: List<String> = emptyList(),
    val folder: String? = null,
)

@Serializable
data class CategoryState(
    val isEnabled: Boolean = false,
    val categories: List<Category> = emptyList(),
    val defaultFolder: String = "",
)

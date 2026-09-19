package com.xychr.ghostdownloader.packs

import com.xychr.ghostdownloader.model.DraftControl
import com.xychr.ghostdownloader.model.DraftOption
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

class PackKeys(configClass: String) {
    val prefix = "pack_${configClass}_"

    operator fun invoke(attr: String) = prefix + attr
}

fun JsonObject.has(pack: PackKeys) = keys.any { it.startsWith(pack.prefix) }

fun JsonObject.bool(key: String) = this[key]?.jsonPrimitive?.booleanOrNull ?: false
fun JsonObject.int(key: String) = this[key]?.jsonPrimitive?.intOrNull ?: 0
fun JsonObject.str(key: String) = this[key]?.jsonPrimitive?.contentOrNull ?: ""

fun JsonObject.strings(key: String): List<String> =
    (this[key] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }.orEmpty()

fun JsonObject.sizes(key: String): Map<String, Int> =
    (this[key] as? JsonObject)?.mapValues { (it.value as? JsonArray)?.size ?: 0 }.orEmpty()

fun JsonObject.optionList(key: String): List<DraftOption> =
    (this[key] as? JsonArray)?.map {
        val obj = it.jsonObject
        DraftOption(obj["key"]?.jsonPrimitive?.content ?: "", obj["label"]?.jsonPrimitive?.content ?: "")
    } ?: emptyList()

fun JsonObject.controlList(): List<DraftControl> =
    (this["controls"] as? JsonArray).orEmpty().mapNotNull { element ->
        val control = element.jsonObject
        val options = control.optionList("options")
        if (options.isEmpty()) return@mapNotNull null
        DraftControl(
            id = control.str("id"),
            options = options,
            title = control.str("title"),
            value = control.str("value"),
            isMultiple = control.bool("isMultiple"),
            isOptional = control.bool("isOptional"),
        )
    }

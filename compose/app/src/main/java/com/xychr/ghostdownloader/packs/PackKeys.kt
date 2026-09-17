package com.xychr.ghostdownloader.packs

import com.chaquo.python.Python
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
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

fun engineString(module: String, name: String): String =
    Python.getInstance().getModule(module).get(name)?.toString().orEmpty()

fun engineStrings(module: String, name: String): List<String> =
    Python.getInstance().getModule(module).get(name)!!.asList().map { it.toString() }

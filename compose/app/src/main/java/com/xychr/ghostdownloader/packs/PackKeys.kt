package com.xychr.ghostdownloader.packs

import com.chaquo.python.Python
import kotlinx.serialization.json.JsonObject
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

fun engineStrings(module: String, name: String): List<String> =
    Python.getInstance().getModule(module).get(name)!!.asList().map { it.toString() }

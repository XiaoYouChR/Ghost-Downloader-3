package com.xychr.ghostdownloader.packs

import com.chaquo.python.Python
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive

class PackKeys(configClass: String) {
    val prefix = "pack_${configClass}_"

    operator fun invoke(attr: String) = prefix + attr
}

fun JsonObject.has(pack: PackKeys) = keys.any { it.startsWith(pack.prefix) }

fun JsonObject.bool(key: String) = getValue(key).jsonPrimitive.boolean
fun JsonObject.int(key: String) = getValue(key).jsonPrimitive.int
fun JsonObject.str(key: String) = getValue(key).jsonPrimitive.content

fun engineStrings(module: String, name: String): List<String> =
    Python.getInstance().getModule(module).get(name)!!.asList().map { it.toString() }

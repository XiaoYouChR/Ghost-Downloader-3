package com.xychr.ghostdownloader.engine

import com.chaquo.python.PyObject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json

@JvmInline
value class Encoded(@PublishedApi internal val value: String)

object EngineRepository {

    private lateinit var engine: PyObject

    @PublishedApi internal val json = Json { ignoreUnknownKeys = true }

    fun bind(engine: PyObject) {
        this.engine = engine
    }

    @PublishedApi internal suspend fun callEngine(name: String, vararg args: Any?): String {
        val unwrapped = Array(args.size) { i -> val a = args[i]; if (a is Encoded) a.value else a }
        return withContext(Dispatchers.IO) { engine.callAttr(name, *unwrapped).toString() }
    }

    suspend inline fun <reified T> query(name: String, vararg args: Any?): T =
        json.decodeFromString(callEngine(name, *args))

    suspend fun invoke(name: String, vararg args: Any?) {
        val unwrapped = Array(args.size) { i -> val a = args[i]; if (a is Encoded) a.value else a }
        withContext(Dispatchers.IO) { engine.callAttr(name, *unwrapped) }
    }

    inline fun <reified T> observe(key: String): Flow<T> = EngineFlows.stream(key)

    inline fun <reified T> encode(value: T): Encoded = Encoded(json.encodeToString(value))
}

package com.xychr.ghostdownloader.ui.components.settings

import kotlinx.serialization.Serializable

@Serializable
data class HeaderEntry(val name: String, val value: String)

data class HeaderParse(val entries: List<HeaderEntry>, val invalidLines: List<Int>) {
    val isValid: Boolean get() = invalidLines.isEmpty()
}

fun matchHeaderName(name: String): Boolean =
    name.trim().isNotEmpty() && name.trim().all {
        it in 'a'..'z' || it in 'A'..'Z' || it in '0'..'9' || it in "!#$%&'*+-.^_`|~"
    }

fun matchHeaderValue(value: String): Boolean = value.none { it.code < 32 && it != '\t' || it.code == 127 }

fun parseHeaderText(text: String): HeaderParse {
    val entries = mutableListOf<HeaderEntry>()
    val invalid = mutableListOf<Int>()
    val names = mutableSetOf<String>()
    text.lines().forEachIndexed { index, line ->
        if (line.isBlank()) return@forEachIndexed
        val colon = line.indexOf(':')
        val name = line.substringBefore(':').trim()
        val value = if (colon >= 0) line.substring(colon + 1).trim() else ""
        if (colon < 1 || !matchHeaderName(name) || !matchHeaderValue(value) || !names.add(name.lowercase())) {
            invalid += index + 1
        }
        entries += HeaderEntry(name, value)
    }
    return HeaderParse(entries, invalid)
}

fun toHeaderText(entries: List<HeaderEntry>): String = entries.joinToString("\n") { "${it.name}: ${it.value}" }

fun matchHeaderEntries(entries: List<HeaderEntry>): Boolean = entries.all {
    matchHeaderName(it.name) && matchHeaderValue(it.value)
} && entries.map { it.name.trim().lowercase() }.distinct().size == entries.size

fun buildMergedHeaders(current: List<HeaderEntry>, incoming: List<HeaderEntry>): List<HeaderEntry> {
    val replacements = incoming.map { it.name.trim().lowercase() }.toSet()
    return current.filterNot { it.name.trim().lowercase() in replacements } + incoming
}

enum class HeaderImportError { QUOTES, MULTIPLE_REQUESTS, FILE_INPUT, INVALID_HEADERS, EMPTY }
data class HeaderImport(val entries: List<HeaderEntry> = emptyList(), val error: HeaderImportError? = null)

// 仅解析支持的 cURL 参数。不执行 shell，也不展开变量、读取文件或推测丢失的参数。
fun parseHeaderImport(source: String): HeaderImport {
    val text = source.trim().replace("\r\n", "\n")
    if (!Regex("^curl(?:\\s|$)", RegexOption.IGNORE_CASE).containsMatchIn(text)) {
        val parsed = parseHeaderText(text)
        return HeaderImport(parsed.entries, when {
            !parsed.isValid -> HeaderImportError.INVALID_HEADERS
            parsed.entries.isEmpty() -> HeaderImportError.EMPTY
            else -> null
        })
    }
    val tokens = parseCurlTokens(text.replace("\\\n", " ").replace("^\n", " "))
        ?: return HeaderImport(error = HeaderImportError.QUOTES)
    val entries = mutableListOf<HeaderEntry>()
    var index = 1
    var urlCount = 0
    while (index < tokens.size) {
        val token = tokens[index++]
        if (token in listOf(";", "&", "&&", "|", "||") || token.equals("curl", true)) {
            return HeaderImport(error = HeaderImportError.MULTIPLE_REQUESTS)
        }
        if (token in listOf("-K", "--config") || token.startsWith("--config="))
            return HeaderImport(error = HeaderImportError.FILE_INPUT)
        if (token in listOf("-d", "--data", "--data-raw", "--data-binary", "--data-urlencode", "--url",
                "-X", "--request", "-o", "--output", "--proxy", "-x")) {
            if (index == tokens.size) return HeaderImport(error = HeaderImportError.INVALID_HEADERS)
            if (token == "--url" && ++urlCount > 1) return HeaderImport(error = HeaderImportError.MULTIPLE_REQUESTS)
            index++
            continue
        }
        val isJoinedShortFlag = token.length > 2 && token.take(2) in listOf("-H", "-b", "-A", "-e")
        val flag = if (isJoinedShortFlag) token.take(2) else token.substringBefore('=')
        val headerName = when (flag) {
            "-H", "--header" -> ""
            "-b", "--cookie" -> "Cookie"
            "-A", "--user-agent" -> "User-Agent"
            "-e", "--referer" -> "Referer"
            else -> null
        }
        if (headerName == null) {
            when {
                token in listOf("--compressed", "--location", "-L", "--insecure", "-k", "--http1.1", "--http2",
                    "--globoff", "--silent", "-s", "--show-error", "-S", "--fail", "-f", "--head", "-I") -> Unit
                !token.startsWith('-') && token.none(Char::isWhitespace) -> {
                    if (++urlCount > 1) return HeaderImport(error = HeaderImportError.MULTIPLE_REQUESTS)
                }
                else -> return HeaderImport(error = HeaderImportError.INVALID_HEADERS)
            }
            continue
        }
        val value = if (isJoinedShortFlag) token.drop(2) else if ('=' in token) token.substringAfter('=')
            else tokens.getOrNull(index++) ?: return HeaderImport(error = HeaderImportError.INVALID_HEADERS)
        if (value.startsWith('@') || (headerName == "Cookie" && '=' !in value)) {
            return HeaderImport(error = HeaderImportError.FILE_INPUT)
        }
        if (headerName.isEmpty()) {
            val parsed = parseHeaderText(value)
            if (!parsed.isValid || parsed.entries.size != 1) return HeaderImport(error = HeaderImportError.INVALID_HEADERS)
            entries += parsed.entries
        } else entries += HeaderEntry(headerName, value)
    }
    return HeaderImport(entries, when {
        entries.isEmpty() -> HeaderImportError.EMPTY
        !matchHeaderEntries(entries) -> HeaderImportError.INVALID_HEADERS
        else -> null
    })
}

private fun parseCurlTokens(text: String): List<String>? {
    if (text.contains("$'")) return null
    val tokens = mutableListOf<String>()
    val token = StringBuilder()
    var quote: Char? = null
    var isStarted = false
    var index = 0
    while (index < text.length) {
        val char = text[index++]
        when {
            char == '\\' && quote != '\'' -> {
                if (index == text.length) return null
                val next = text[index]
                if (quote == '"' && next !in "\\\"$`\n") token.append(char)
                else { token.append(next); index++ }
                isStarted = true
            }
            char == quote -> quote = null
            quote != null -> token.append(char)
            char == '\'' || char == '"' -> { quote = char; isStarted = true }
            char.isWhitespace() -> {
                if (isStarted) { tokens += token.toString(); token.clear(); isStarted = false }
            }
            char in ";&|" -> {
                if (isStarted) { tokens += token.toString(); token.clear(); isStarted = false }
                tokens += char.toString()
            }
            else -> { token.append(char); isStarted = true }
        }
    }
    if (quote != null) return null
    if (isStarted) tokens += token.toString()
    return tokens
}

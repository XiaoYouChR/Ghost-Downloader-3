package com.xychr.ghostdownloader.ui.components.draft
import com.xychr.ghostdownloader.model.*

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.ui.util.formatDuration
import com.xychr.ghostdownloader.ui.util.parseDuration
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL
import kotlin.math.roundToInt

data class PreviewFrame(val sheet: Int, val index: Int)

fun DraftPreview.frameAt(seconds: Int): PreviewFrame? {
    var result: PreviewFrame? = null
    sheets.forEachIndexed { sheetIndex, sheet ->
        sheet.times.forEachIndexed { index, time ->
            if (time <= seconds && index < sheet.columns * sheet.rows) result = PreviewFrame(sheetIndex, index)
        }
    }
    return result
}

@Composable
fun DraftTrim(
    item: DraftItem,
    start: Int,
    end: Int,
    onChange: (Int, Int) -> Unit,
    fetchPreview: suspend (String) -> DraftPreview,
    modifier: Modifier = Modifier,
) {
    var startText by rememberSaveable { mutableStateOf(formatDuration(start.toLong())) }
    var endText by rememberSaveable { mutableStateOf(formatDuration((end.takeIf { it > 0 } ?: item.duration).toLong())) }
    val startValue = parseDuration(startText)
    val endValue = parseDuration(endText)
    val isValid = startValue != null && endValue != null && startValue >= 0 &&
        startValue < endValue && endValue <= item.duration
    var position by rememberSaveable { mutableIntStateOf(start) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (item.hasPreview) DraftPreviewImage(item.url, position, fetchPreview)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedTextField(startText, {
                startText = it
                val value = parseDuration(it)
                position = value?.coerceIn(0, item.duration) ?: position
                onChange(value ?: -1, endValue ?: -1)
            }, label = { Text(stringResource(R.string.draft_trim_start)) },
                isError = !isValid, singleLine = true, modifier = Modifier.weight(1f))
            OutlinedTextField(endText, {
                endText = it
                val value = parseDuration(it)
                position = value?.coerceIn(0, item.duration) ?: position
                onChange(startValue ?: -1, value ?: -1)
            }, label = { Text(stringResource(R.string.draft_trim_end)) },
                isError = !isValid, singleLine = true, modifier = Modifier.weight(1f))
        }
        if (!isValid) Text(stringResource(R.string.draft_invalid_range), color = MaterialTheme.colorScheme.error)
        val rangeStart = (startValue ?: 0).coerceIn(0, item.duration)
        val rangeEnd = (endValue ?: item.duration).coerceIn(rangeStart, item.duration)
        RangeSlider(value = rangeStart.toFloat()..rangeEnd.toFloat(),
            onValueChange = {
                val from = it.start.roundToInt()
                val to = it.endInclusive.roundToInt()
                position = if (from != rangeStart) from else to
                startText = formatDuration(from.toLong())
                endText = formatDuration(to.toLong())
                onChange(from, to)
            }, valueRange = 0f..item.duration.toFloat())
        TextButton(onClick = {
            startText = formatDuration(0)
            endText = formatDuration(item.duration.toLong())
            onChange(0, 0)
        }) { Text(stringResource(R.string.draft_trim_off)) }
    }
}

@Composable
fun DraftPreviewImage(
    url: String,
    seconds: Int,
    fetchPreview: suspend (String) -> DraftPreview,
    modifier: Modifier = Modifier,
    fetchSheet: suspend (PreviewSheet, Map<String, String>) -> Bitmap = ::fetchPreviewSheet,
) {
    var preview by remember(url) { mutableStateOf<DraftPreview?>(null) }
    var frame by remember(url) { mutableStateOf<Bitmap?>(null) }
    var error by remember(url) { mutableStateOf<String?>(null) }
    var retry by remember(url) { mutableIntStateOf(0) }
    var isLoading by remember(url) { mutableStateOf(false) }
    // Only two sheets stay resident; a long video's storyboard must not fill the heap.
    val cache = remember(url) { linkedMapOf<String, Bitmap>() }
    var loadedSheet by remember(url) { mutableStateOf<Pair<Int, Bitmap>?>(null) }
    val currentFetch by rememberUpdatedState(fetchPreview)
    val currentFetchSheet by rememberUpdatedState(fetchSheet)
    LaunchedEffect(url, retry) {
        isLoading = true
        error = null
        try { preview = currentFetch(url) }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { error = failure.message ?: failure.toString() }
        finally { isLoading = false }
    }
    val address = preview?.frameAt(seconds)
    LaunchedEffect(preview, address?.sheet, retry) {
        val data = preview ?: return@LaunchedEffect
        val target = address ?: return@LaunchedEffect
        isLoading = true
        error = null
        try {
            val sheet = data.sheets[target.sheet]
            val bitmap = cache[sheet.url] ?: currentFetchSheet(sheet, data.headers).also {
                cache[sheet.url] = it
                if (cache.size > 2) cache.remove(cache.keys.first())
            }
            loadedSheet = target.sheet to bitmap
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { error = failure.message ?: failure.toString() }
        finally { isLoading = false }
    }
    LaunchedEffect(loadedSheet, address) {
        val target = address ?: return@LaunchedEffect
        val (index, bitmap) = loadedSheet ?: return@LaunchedEffect
        if (index != target.sheet) return@LaunchedEffect
        val sheet = preview!!.sheets[index]
        if (sheet.columns <= 0 || sheet.rows <= 0) return@LaunchedEffect
        val width = bitmap.width / sheet.columns
        val height = bitmap.height / sheet.rows
        if (width > 0 && height > 0) frame = Bitmap.createBitmap(bitmap,
            target.index % sheet.columns * width, target.index / sheet.columns * height, width, height)
    }
    Column(modifier) {
        Surface(shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.surfaceContainer) {
            Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f), contentAlignment = Alignment.Center) {
                frame?.let { Image(it.asImageBitmap(), stringResource(R.string.draft_preview),
                    Modifier.fillMaxSize(), contentScale = ContentScale.Fit) }
                if (isLoading) CircularProgressIndicator()
                else if (frame == null && error == null) Text(stringResource(R.string.draft_preview_unavailable))
            }
        }
        if (error != null) {
            Text(stringResource(R.string.draft_preview_failed), color = MaterialTheme.colorScheme.error)
            TextButton(onClick = { retry++ }) { Text(stringResource(R.string.draft_retry)) }
        }
    }
}

private suspend fun fetchPreviewSheet(sheet: PreviewSheet, headers: Map<String, String>): Bitmap =
    withContext(Dispatchers.IO) {
        val connection = URL(sheet.url).openConnection() as HttpURLConnection
        connection.connectTimeout = 15000
        connection.readTimeout = 15000
        headers.forEach { (name, value) -> connection.setRequestProperty(name, value) }
        try {
            connection.inputStream.use { input ->
                BitmapFactory.decodeStream(input) ?: error("Invalid preview image")
            }
        } finally { connection.disconnect() }
    }

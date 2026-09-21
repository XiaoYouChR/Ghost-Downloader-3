package com.xychr.ghostdownloader.ui.components.task

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.model.HashState
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HashSheet(taskId: String, name: String, onDismiss: () -> Unit, modifier: Modifier = Modifier) {
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf(HashState()) }
    var algorithms by remember { mutableStateOf(emptyList<String>()) }
    var algorithm by remember { mutableStateOf("sha256") }
    var isMenuOpen by remember { mutableStateOf(false) }

    LaunchedEffect(taskId) {
        engineRepository.observe<HashState>("hashState").collect {
            state = if (it.taskId == taskId) it else HashState()
        }
    }
    LaunchedEffect(Unit) {
        val available = runCatching { engineRepository.query<List<String>>("hashAlgorithms") }
            .getOrDefault(emptyList())
        algorithms = available
        if (algorithm !in available) algorithm = available.lastOrNull { it == "sha256" } ?: available.lastOrNull().orEmpty()
    }

    fun cancel() {
        scope.launch { engineRepository.invoke("cancelFileHash") }
    }

    ModalBottomSheet(onDismissRequest = { cancel(); onDismiss() }, modifier = modifier) {
        Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 24.dp)) {
            Text(stringResource(R.string.task_hash_title), style = MaterialTheme.typography.titleLarge)
            Text(
                text = name,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp),
            )
            Spacer(Modifier.padding(top = 16.dp))

            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.task_hash_algorithm))
                Spacer(Modifier.weight(1f))
                TextButton(onClick = { isMenuOpen = true }, enabled = !state.isRunning) {
                    Text(algorithm.ifEmpty { stringResource(R.string.task_hash_loading) })
                }
                DropdownMenu(isMenuOpen, onDismissRequest = { isMenuOpen = false }) {
                    for (item in algorithms) {
                        DropdownMenuItem(
                            text = { Text(item) },
                            onClick = { algorithm = item; isMenuOpen = false },
                        )
                    }
                }
            }

            if (state.isRunning) {
                Spacer(Modifier.padding(top = 8.dp))
                LinearProgressIndicator(
                    progress = { state.progress / 100f },
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    text = stringResource(R.string.task_hash_progress, state.progress),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }

            val digest = state.digest
            val error = state.error
            if (digest.isNotEmpty() || error != null) {
                Spacer(Modifier.padding(top = 16.dp))
                Text(
                    text = if (error != null) engineText(error) else state.algorithm,
                    style = MaterialTheme.typography.labelLarge,
                    color = if (error != null) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (digest.isNotEmpty()) {
                    SelectionContainer {
                        Text(
                            text = digest,
                            style = MaterialTheme.typography.bodySmall,
                            fontFamily = FontFamily.Monospace,
                            modifier = Modifier.padding(top = 4.dp).verticalScroll(rememberScrollState()),
                        )
                    }
                }
            }

            Spacer(Modifier.padding(top = 16.dp))
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                if (state.isRunning) {
                    TextButton(onClick = { cancel() }) { Text(stringResource(R.string.action_cancel)) }
                } else {
                    Button(
                        onClick = {
                            scope.launch { engineRepository.invoke("startFileHash", taskId, algorithm) }
                        },
                        enabled = algorithm.isNotEmpty(),
                    ) {
                        Text(stringResource(
                            if (digest.isNotEmpty() || error != null) R.string.task_hash_again
                            else R.string.task_hash_start,
                        ))
                    }
                }
                Spacer(Modifier.weight(1f))
                if (state.isRunning) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
            }
        }
    }
}

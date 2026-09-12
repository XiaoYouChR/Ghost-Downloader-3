package com.xychr.ghostdownloader.ui.components.category

import androidx.annotation.DrawableRes
import androidx.compose.animation.Crossfade
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import com.xychr.ghostdownloader.R

@Composable
fun CategoryAction(name: String, @DrawableRes icon: Int, onClick: () -> Unit,
                   modifier: Modifier = Modifier, isEnabled: Boolean = true, isOpen: Boolean = false) {
    val description = stringResource(R.string.task_category_action, name)
    val expanded = stringResource(if (isOpen) R.string.task_expanded else R.string.task_collapsed)
    val angle by animateFloatAsState(if (isOpen) 270f else 90f, tween(180), label = "category-arrow")
    AssistChip(onClick = onClick, enabled = isEnabled,
        modifier = modifier.heightIn(min = 48.dp).animateContentSize()
            .semantics { contentDescription = description; stateDescription = expanded },
        label = {
            Text(name, Modifier.clearAndSetSemantics {})
        },
        leadingIcon = {
            Crossfade(icon, animationSpec = tween(150), label = "category-icon") {
                Icon(painterResource(it), null, Modifier.size(18.dp))
            }
        },
        trailingIcon = {
            Icon(painterResource(R.drawable.ic_chevron_right), null,
                Modifier.size(18.dp).graphicsLayer { rotationZ = angle })
        })
}

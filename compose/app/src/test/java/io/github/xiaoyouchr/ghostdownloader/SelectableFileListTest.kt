package com.xychr.ghostdownloader

import com.xychr.ghostdownloader.ui.components.FileRow
import com.xychr.ghostdownloader.ui.components.FolderRow
import com.xychr.ghostdownloader.ui.components.SelectableFile
import com.xychr.ghostdownloader.ui.components.TreeRow
import com.xychr.ghostdownloader.ui.components.buildRows
import org.junit.Assert.assertEquals
import org.junit.Test

class SelectableFileListTest {

    private fun file(index: Int, path: String) = SelectableFile(index, path, 0)

    private fun labels(tree: List<TreeRow>) = tree.map { row ->
        val indent = "  ".repeat(row.depth)
        when (row) {
            is FolderRow -> "$indent${row.name}/"
            is FileRow -> "$indent${row.file.index}"
        }
    }

    @Test
    fun filesNestUnderTheirFolders() {
        val tree = buildRows(
            listOf(file(0, "第01话/01.mp4"), file(1, "第01话/02.mp4"), file(2, "第02话/01.mp4")),
            emptySet(),
        )
        assertEquals(listOf("第01话/", "  0", "  1", "第02话/", "  2"), labels(tree))
    }

    @Test
    fun collapseHidesDescendantsButKeepsTheFolderItself() {
        val tree = buildRows(
            listOf(file(0, "第01话/01.mp4"), file(1, "第02话/01.mp4")),
            collapsed = setOf("第01话"),
        )
        assertEquals(listOf("第01话/", "第02话/", "  1"), labels(tree))
    }

    @Test
    fun collapsingANestedFolderKeepsItsAncestors() {
        val tree = buildRows(
            listOf(file(0, "a/b/c.txt"), file(1, "a/b/d.txt"), file(2, "a/e.txt")),
            collapsed = setOf("a/b"),
        )
        assertEquals(listOf("a/", "  b/", "  2"), labels(tree))
    }

    @Test
    fun aFileNamedLikeItsFolderDoesNotMergeWithIt() {
        val tree = buildRows(listOf(file(0, "a/b.txt"), file(1, "a/b/c.txt")), emptySet())
        assertEquals(listOf("a/", "  0", "  b/", "    1"), labels(tree))
    }

    @Test
    fun siblingFoldersKeepSeparateBranches() {
        val tree = buildRows(listOf(file(0, "a/b.txt"), file(1, "a/c.txt"), file(2, "d/e.txt")), emptySet())
        assertEquals(listOf("a/", "  0", "  1", "d/", "  2"), labels(tree))
    }

    @Test
    fun filesWithoutFoldersSitAtTheRoot() {
        assertEquals(listOf("0"), labels(buildRows(listOf(file(0, "readme.txt")), emptySet())))
    }

    @Test
    fun folderDescendantsCoverEveryNestedFile() {
        val tree = buildRows(listOf(file(0, "a/b/c.txt"), file(1, "a/d.txt")), emptySet())
        val folder = tree.filterIsInstance<FolderRow>().first { it.path == "a" }
        assertEquals(listOf(0, 1), folder.descendants)
    }

    @Test
    fun collapsingATopFolderAlsoHidesItsNestedFolders() {
        val files = listOf(
            file(0, "a/b/c.txt"), file(1, "a/b/d.txt"), file(2, "a/e.txt"), file(3, "f.txt"),
        )
        assertEquals(listOf("a/", "3"), labels(buildRows(files, setOf("a"))))
    }
}

from __future__ import annotations

from app.models.task import ResourceTaskOptions
from features.http_pack.pack import HttpParser
from tests.helpers import buildFileContent, buildRangeHandler


async def test_parse_resource_without_range_probes_server(startServer, tmp_path):
    content = buildFileContent(4096)
    url = await startServer(buildRangeHandler(content))
    options = ResourceTaskOptions(
        url=url, outputFolder=tmp_path, headers={}, clientProfile="raw",
        name="from-extension.bin", size=len(content), canUseRangeRequests=False,
    )

    task = await HttpParser().parse(options)

    assert task.name == "from-extension.bin"
    assert task.steps[0].canUseRangeRequests
    assert task.steps[0].fileSize == len(content)

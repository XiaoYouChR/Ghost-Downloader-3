from __future__ import annotations

from aiohttp import web


def buildFileContent(size: int) -> bytes:
    return bytes(i % 256 for i in range(size))


def buildRangeHandler(content: bytes):
    async def handler(request: web.Request) -> web.Response:
        rangeHeader = request.headers.get("Range")
        if rangeHeader is None:
            return web.Response(
                body=content,
                headers={"Content-Length": str(len(content)),
                          "Accept-Ranges": "bytes"},
            )
        rangeSpec = rangeHeader.replace("bytes=", "")
        parts = rangeSpec.split("-")
        start = int(parts[0])
        end = int(parts[1]) if parts[1] else len(content) - 1
        body = content[start:end + 1]
        return web.Response(
            status=206, body=body,
            headers={
                "Content-Range": f"bytes {start}-{end}/{len(content)}",
                "Content-Length": str(len(body)),
            },
        )
    return handler


async def runStep(step) -> list[int]:
    speeds = []

    def reportSpeed(n):
        speeds.append(n)

    async def waitForSpeedLimit():
        pass

    await step.run(reportSpeed, waitForSpeedLimit)
    return speeds

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import pytest
from aiohttp import web

from app.config.cfg import cfg
from app.config.paths import APP_DATA_DIR
from app.models.task import TaskError, TaskOptions, TaskStatus
from huggingface_pack.config import CUSTOM_SITE_KEY
from huggingface_pack.pack import HuggingFaceParser
from tests.helpers import buildRangeHandler, runStep

REPO_URL = "https://huggingface.co/datasets/org/repo"
REVISION_PATTERN = re.compile(r"^/api/datasets/org/repo/revision/(?P<rev>[^/]+)$")
RESOLVE_PATTERN = re.compile(r"^/datasets/org/repo/resolve/(?P<commit>[^/]+)/(?P<path>.+)$")


@dataclass
class Hub:
    """在本机充当 Mirror Site 的 HuggingFace 仓库。"""
    commits: dict[str, dict[str, bytes]]
    refs: dict[str, str]
    isGated: bool = False
    validTokens: set[str] = field(default_factory=set)

    async def handle(self, request: web.Request) -> web.StreamResponse:
        if m := REVISION_PATTERN.match(request.path):
            commit = self.refs.get(m["rev"], m["rev"])
            siblings = [
                {"rfilename": path, "size": len(content), "lfs": {"size": len(content)}}
                for path, content in self.commits[commit].items()
            ]
            return web.json_response({"sha": commit, "gated": "auto" if self.isGated else False, "siblings": siblings})
        if m := RESOLVE_PATTERN.match(request.path):
            authorization = request.headers.get("Authorization", "")
            if self.isGated and authorization.removeprefix("Bearer ") not in self.validTokens:
                # 与 hf-mirror.com 一致：没带 Token 返回 403，Token 无效返回 401
                return web.Response(status=401 if authorization else 403)
            return await buildRangeHandler(self.commits[m["commit"]][m["path"]])(request)
        return web.Response(status=404)


async def startHub(startServer, hub: Hub, *, token: str = "") -> None:
    url = await startServer(hub.handle)
    setConfig(site=url.removesuffix("/file"), token=token)


def setConfig(*, site: str, token: str) -> None:
    configFile = APP_DATA_DIR / "UserConfig.json"
    data = json.loads(configFile.read_text(encoding="utf-8"))
    data["HuggingFace"] = {"SelectedSite": CUSTOM_SITE_KEY, "CustomSite": site, "AccessToken": token}
    configFile.write_text(json.dumps(data), encoding="utf-8")
    cfg.load(configFile)


def setToken(token: str) -> None:
    configFile = APP_DATA_DIR / "UserConfig.json"
    data = json.loads(configFile.read_text(encoding="utf-8"))
    data["HuggingFace"]["AccessToken"] = token
    configFile.write_text(json.dumps(data), encoding="utf-8")
    cfg.load(configFile)


async def parse(url: str, downloadFolder):
    return await HuggingFaceParser().parse(TaskOptions(url=url, outputFolder=downloadFolder))


async def test_run_downloads_gated_repo_with_token(config, startServer, downloadFolder):
    files = {"a.bin": b"a" * 1000, "sub/b.bin": b"b" * 500}
    await startHub(startServer, Hub({"c1": files}, {"main": "c1"}, isGated=True, validTokens={"t"}), token="t")

    task = await parse(REPO_URL, downloadFolder)
    await runStep(task.steps[0])

    assert task.status == TaskStatus.COMPLETED
    assert (downloadFolder / "org_repo" / "a.bin").read_bytes() == files["a.bin"]
    assert (downloadFolder / "org_repo" / "sub" / "b.bin").read_bytes() == files["sub/b.bin"]


async def test_parse_gated_repo_without_token_asks_for_token(config, startServer, downloadFolder):
    await startHub(startServer, Hub({"c1": {"a.bin": b"a"}}, {"main": "c1"}, isGated=True, validTokens={"t"}))

    with pytest.raises(TaskError, match="请在设置中填写 HuggingFace Access Token"):
        await parse(REPO_URL, downloadFolder)


async def test_run_uses_token_updated_after_parse(config, startServer, downloadFolder):
    hub = Hub({"c1": {"a.bin": b"a" * 1000}}, {"main": "c1"}, isGated=True, validTokens={"old"})
    await startHub(startServer, hub, token="old")
    task = await parse(REPO_URL, downloadFolder)

    hub.validTokens = {"new"}
    setToken("new")
    await runStep(task.steps[0])

    assert (downloadFolder / "a.bin").read_bytes() == b"a" * 1000


async def test_run_with_expired_token_asks_to_update_token(config, startServer, downloadFolder):
    hub = Hub({"c1": {"a.bin": b"a" * 1000}}, {"main": "c1"}, isGated=True, validTokens={"old"})
    await startHub(startServer, hub, token="old")
    task = await parse(REPO_URL, downloadFolder)

    hub.validTokens = set()
    with pytest.raises(TaskError, match="无效或已过期"):
        await runStep(task.steps[0])


async def test_run_after_repo_update_downloads_added_version(config, startServer, downloadFolder):
    hub = Hub({"c1": {"a.bin": b"1" * 1000}, "c2": {"a.bin": b"2" * 1000}}, {"main": "c1"})
    await startHub(startServer, hub)
    task = await parse(REPO_URL, downloadFolder)

    hub.refs["main"] = "c2"
    await runStep(task.steps[0])

    assert (downloadFolder / "a.bin").read_bytes() == b"1" * 1000


async def test_parse_folder_link_selects_folder_files(config, startServer, downloadFolder):
    files = {"a.bin": b"a", "sub/b.bin": b"b", "sub/c.bin": b"c", "subway.bin": b"d"}
    await startHub(startServer, Hub({"c1": files}, {"main": "c1"}))

    task = await parse(f"{REPO_URL}/tree/main/sub", downloadFolder)

    assert [f.relativePath for f in task.files] == ["sub/b.bin", "sub/c.bin"]

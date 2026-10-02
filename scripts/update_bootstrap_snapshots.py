#!/usr/bin/env python3
"""Refresh the Bootstrap List snapshots bundled with the BT and eD2k packs.

Run before a release:
    python scripts/update_bootstrap_snapshots.py
"""
import sys
from pathlib import Path
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "features")]

from bittorrent_pack.config import DEFAULT_TRACKER_LIST_SOURCES  # noqa: E402
from bittorrent_pack.trackers import parseTrackers  # noqa: E402
from ed2k_pack.config import DEFAULT_NODE_LIST_SOURCES, DEFAULT_SERVER_LIST_SOURCES  # noqa: E402
from ed2k_pack.lists import parseNodeList, parseServerList  # noqa: E402


def fetch(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
        return response.read()


def fetchFirstValid(urls: list[str], parse) -> bytes:
    for url in urls:
        try:
            data = fetch(url)
            print(f"{url}: {len(parse(data))}")
            return data
        except Exception as e:
            print(f"{url}: {e}")
    sys.exit("No source returned a valid list")


def main() -> None:
    trackers: list[str] = []
    for url in DEFAULT_TRACKER_LIST_SOURCES:
        try:
            fetched = parseTrackers(fetch(url).decode("utf-8", errors="ignore"))
            print(f"{url}: {len(fetched)}")
            trackers += fetched
        except Exception as e:
            print(f"{url}: {e}")
    if not trackers:
        sys.exit("No tracker source returned a valid list")
    (REPO / "features/bittorrent_pack/lists/trackers.txt").write_text(
        "\n".join(dict.fromkeys(trackers)) + "\n", "utf-8")

    (REPO / "features/ed2k_pack/lists/server.met").write_bytes(
        fetchFirstValid(DEFAULT_SERVER_LIST_SOURCES, parseServerList))
    (REPO / "features/ed2k_pack/lists/nodes.dat").write_bytes(
        fetchFirstValid(DEFAULT_NODE_LIST_SOURCES, parseNodeList))


if __name__ == "__main__":
    main()

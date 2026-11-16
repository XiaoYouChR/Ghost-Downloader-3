from __future__ import annotations

import base64
import json
import math
from typing import Any
from urllib.parse import urljoin, urlparse


def matchVimeoPlaylist(url: str) -> bool:
    path = urlparse(url).path
    return "/v2/playlist/" in path and path.endswith("/playlist.json")


# The init segment only exists as base64 in the JSON, and N_m3u8DL-RE crashes on data: URIs,
# so it becomes a file beside the playlists.
def buildVimeoFiles(body: str, playlistUrl: str) -> dict[str, bytes]:
    playlist = json.loads(body)
    baseUrl = urljoin(playlistUrl, playlist["base_url"])
    files: dict[str, bytes] = {}

    def addMedia(name: str, stream: dict[str, Any]) -> None:
        segments = stream["segments"]
        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:7",
            f"#EXT-X-TARGETDURATION:{math.ceil(max(s['end'] - s['start'] for s in segments))}",
            "#EXT-X-PLAYLIST-TYPE:VOD",
            f'#EXT-X-MAP:URI="{name}.mp4"',
        ]
        for segment in segments:
            lines.append(f"#EXTINF:{segment['end'] - segment['start']:.3f},")
            lines.append(baseUrl + stream["base_url"] + segment["url"])
        lines.append("#EXT-X-ENDLIST")
        files[f"{name}.m3u8"] = "\n".join(lines).encode() + b"\n"
        files[f"{name}.mp4"] = base64.b64decode(stream["init_segment"])

    # One audio track: the download selects all audio, and AAC is what browsers play.
    audio = max(
        playlist.get("audio") or [],
        key=lambda s: (s["codecs"].startswith("mp4a"), s["bitrate"]),
        default=None,
    )
    master = ["#EXTM3U", "#EXT-X-VERSION:7", "#EXT-X-INDEPENDENT-SEGMENTS"]
    if audio is not None:
        addMedia("audio", audio)
        master.append('#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="audio",DEFAULT=YES,AUTOSELECT=YES,URI="audio.m3u8"')
    for index, video in enumerate(playlist["video"]):
        name = f"video-{index}"
        addMedia(name, video)
        codecs = video["codecs"] if audio is None else f"{video['codecs']},{audio['codecs']}"
        bandwidth = video["bitrate"] + (0 if audio is None else audio["bitrate"])
        audioGroup = "" if audio is None else ',AUDIO="audio"'
        master.append(
            f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={video["width"]}x{video["height"]},'
            f'CODECS="{codecs}"{audioGroup}'
        )
        master.append(f"{name}.m3u8")
    files["master.m3u8"] = "\n".join(master).encode() + b"\n"
    return files

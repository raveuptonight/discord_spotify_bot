import asyncio
import os
import re
import logging

import spotipy
from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger(__name__)


class SpotifyClient:
    """Spotify Web API ラッパー"""

    SCOPES = (
        "user-modify-playback-state "
        "user-read-playback-state "
        "user-read-currently-playing"
    )

    def __init__(self):
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise RuntimeError(
                "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET が未設定です。.env を確認してください。"
            )
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback"),
            scope=self.SCOPES,
            cache_path=os.getenv("SPOTIPY_CACHE_PATH", ".spotify_cache"),
            open_browser=False,
        )
        self.sp = spotipy.Spotify(auth_manager=auth_manager)
        self._device_name = os.getenv("LIBRESPOT_DEVICE_NAME", "Discord Bot")
        logger.info("Spotify client ready (device: %s)", self._device_name)

    async def _run(self, func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    async def _get_device_id(self) -> str | None:
        devices = await self.get_devices()
        for d in devices:
            if self._device_name.lower() in d["name"].lower():
                return d["id"]
        logger.warning("デバイス '%s' が見つかりません", self._device_name)
        return None

    @staticmethod
    def parse_spotify_uri(query: str) -> tuple[str, str] | None:
        """URL/URI → (type, uri)。該当しなければ None"""
        m = re.match(
            r"https?://open\.spotify\.com/(track|album|playlist)/([a-zA-Z0-9]+)",
            query,
        )
        if m:
            kind, id_ = m.group(1), m.group(2)
            return (kind, f"spotify:{kind}:{id_}")
        for kind in ("track", "album", "playlist"):
            if query.startswith(f"spotify:{kind}:"):
                return (kind, query)
        return None

    @staticmethod
    def _simplify_track(item: dict) -> dict:
        # エピソード (podcast) は artists/album がないので fallback
        images = item.get("album", {}).get("images", []) or item.get("images", [])
        artists = item.get("artists")
        if artists:
            artist = ", ".join(a["name"] for a in artists)
        else:
            artist = item.get("show", {}).get("name", "")
        return {
            "name": item.get("name", ""),
            "artist": artist,
            "album": item.get("album", {}).get("name", ""),
            "uri": item.get("uri", ""),
            "duration_ms": item.get("duration_ms", 0),
            "image_url": images[0]["url"] if images else None,
        }

    # -- public --

    async def search_tracks(self, query: str, limit: int = 5) -> list[dict]:
        results = await self._run(self.sp.search, q=query, type="track", limit=limit)
        tracks = results.get("tracks", {}).get("items", [])
        return [self._simplify_track(t) for t in tracks]

    async def get_track(self, uri: str) -> dict | None:
        try:
            track_id = uri.split(":")[-1]
            data = await self._run(self.sp.track, track_id)
            return self._simplify_track(data)
        except Exception:
            return None

    async def play(self, uri: str | None = None, context_uri: str | None = None,
                   device_id: str | None = None):
        device_id = device_id or await self._get_device_id()
        if uri:
            await self._run(self.sp.start_playback, device_id=device_id, uris=[uri])
        elif context_uri:
            await self._run(self.sp.start_playback, device_id=device_id, context_uri=context_uri)
        else:
            await self._run(self.sp.start_playback, device_id=device_id)

    async def add_to_queue(self, uri: str, device_id: str | None = None):
        device_id = device_id or await self._get_device_id()
        await self._run(self.sp.add_to_queue, uri=uri, device_id=device_id)

    async def pause(self):
        try:
            await self._run(self.sp.pause_playback)
        except spotipy.exceptions.SpotifyException as e:
            if "NO_ACTIVE_DEVICE" in str(e):
                logger.warning("pause: no active device")
            else:
                raise

    async def resume(self):
        device_id = await self._get_device_id()
        await self._run(self.sp.start_playback, device_id=device_id)

    async def skip(self):
        await self._run(self.sp.next_track)

    async def get_current_track(self) -> dict | None:
        data = await self._run(self.sp.current_playback)
        if data is None or data.get("item") is None:
            return None
        track = self._simplify_track(data["item"])
        track["is_playing"] = data.get("is_playing", False)
        track["progress_ms"] = data.get("progress_ms", 0)
        return track

    async def get_queue(self) -> dict:
        data = await self._run(self.sp.queue)
        current = data.get("currently_playing")
        queue_items = data.get("queue", [])
        return {
            "current": self._simplify_track(current) if current else None,
            "queue": [self._simplify_track(t) for t in queue_items[:10]],
            "total": len(queue_items),
        }

    async def set_volume(self, volume: int):
        volume = max(0, min(100, volume))
        await self._run(self.sp.volume, volume)

    async def get_devices(self) -> list[dict]:
        result = await self._run(self.sp.devices)
        return result.get("devices", [])

    async def transfer_playback(self, device_id: str):
        await self._run(self.sp.transfer_playback, device_id=device_id)

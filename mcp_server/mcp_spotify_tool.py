from __future__ import annotations

from dataclasses import dataclass
import os
import re
import time
from typing import Annotated, Any, Dict, Mapping, Optional

import requests
from pydantic import Field

from mcp_server.cockpit_router import CockpitRouter, ToolMatch


class SpotifyConfigError(RuntimeError):
    """Raised when Spotify credentials are missing or invalid."""


class SpotifyAPIError(RuntimeError):
    """Raised for non-recoverable Spotify API failures."""


@dataclass(frozen=True)
class SpotifyAuthConfig:
    client_id: str
    client_secret: str
    refresh_token: str
    market: str = "US"
    default_device_id: Optional[str] = None


class SpotifyWebAPIClient:
    TOKEN_ENDPOINT = "https://accounts.spotify.com/api/token"
    API_BASE = "https://api.spotify.com/v1"

    def __init__(self, auth_config: SpotifyAuthConfig, timeout: float = 10.0) -> None:
        self._cfg = auth_config
        self._timeout = timeout
        self._access_token: Optional[str] = None
        self._access_token_expire_ts: float = 0.0

    def _ensure_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expire_ts:
            return self._access_token

        response = requests.post(
            self.TOKEN_ENDPOINT,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._cfg.refresh_token,
                "client_id": self._cfg.client_id,
                "client_secret": self._cfg.client_secret,
            },
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise SpotifyConfigError(
                f"Failed to refresh Spotify token. status={response.status_code} body={response.text}"
            )

        payload = response.json()
        token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 3600))
        if not token:
            raise SpotifyConfigError("Spotify token response missing access_token.")

        self._access_token = token
        self._access_token_expire_ts = now + max(expires_in - 30, 10)
        return token

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        expected_status: tuple[int, ...] = (200, 201, 202, 204),
    ) -> requests.Response:
        token = self._ensure_access_token()
        response = requests.request(
            method=method,
            url=f"{self.API_BASE}{path}",
            params=params,
            json=json_body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self._timeout,
        )
        if response.status_code in expected_status:
            return response
        raise SpotifyAPIError(
            f"Spotify API call failed: {method} {path}, status={response.status_code}, body={response.text}"
        )

    def search_track(self, query: str) -> Dict[str, Any]:
        response = self._request(
            "GET",
            "/search",
            params={"q": query, "type": "track", "limit": 1, "market": self._cfg.market},
            expected_status=(200,),
        )
        items = response.json().get("tracks", {}).get("items", [])
        if not items:
            raise SpotifyAPIError(f"No track found for query: {query}")

        first = items[0]
        return {
            "id": first.get("id"),
            "uri": first.get("uri"),
            "name": first.get("name"),
            "artists": [artist.get("name", "") for artist in first.get("artists", [])],
        }

    def list_devices(self) -> list[Dict[str, Any]]:
        response = self._request("GET", "/me/player/devices", expected_status=(200,))
        return response.json().get("devices", [])

    def get_current_playback_state(self) -> Optional[Dict[str, Any]]:
        response = self._request(
            "GET",
            "/me/player",
            params={"additional_types": "track"},
            expected_status=(200, 204),
        )
        if response.status_code == 204:
            return None

        payload = response.json()
        device = payload.get("device", {}) if isinstance(payload.get("device"), dict) else {}
        item = payload.get("item", {}) if isinstance(payload.get("item"), dict) else {}
        return {
            "device_id": device.get("id"),
            "device_name": device.get("name"),
            "is_playing": payload.get("is_playing"),
            "item_id": item.get("id"),
            "item_name": item.get("name"),
        }

    def verify_track_playback(
        self,
        *,
        expected_track_id: str,
        target_device_id: Optional[str],
        timeout_seconds: float = 6.0,
        poll_interval_seconds: float = 0.5,
    ) -> Dict[str, Any]:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be > 0")

        deadline = time.time() + timeout_seconds
        attempts = 0
        last_state: Optional[Dict[str, Any]] = None

        while time.time() < deadline:
            attempts += 1
            state = self.get_current_playback_state()
            if state is not None:
                last_state = state
                track_matches = state.get("item_id") == expected_track_id
                device_matches = (
                    True if target_device_id is None else state.get("device_id") == target_device_id
                )
                if track_matches and device_matches:
                    return {
                        "verified": True,
                        "attempts": attempts,
                        "playback": state,
                    }
            time.sleep(poll_interval_seconds)

        if last_state is None:
            raise SpotifyAPIError(
                f"Playback verification failed: no playback state observed within {timeout_seconds:.1f}s."
            )

        raise SpotifyAPIError(
            "Playback verification failed: "
            f"expected_track_id={expected_track_id}, actual_track_id={last_state.get('item_id')}; "
            f"expected_device_id={target_device_id}, actual_device_id={last_state.get('device_id')}; "
            f"actual_item_name={last_state.get('item_name')}, actual_device_name={last_state.get('device_name')}"
        )

    def play_track(self, query: str, device_id: Optional[str] = None) -> Dict[str, Any]:
        track = self.search_track(query=query)

        target_device_id = device_id or self._cfg.default_device_id
        if target_device_id is None:
            devices = self.list_devices()
            if not devices:
                raise SpotifyAPIError("No available Spotify Connect device found.")
            active = next((device for device in devices if device.get("is_active")), None)
            target_device_id = (active or devices[0]).get("id")

        if not target_device_id:
            raise SpotifyAPIError("Failed to resolve Spotify playback device.")

        self._request(
            "PUT",
            "/me/player/play",
            params={"device_id": target_device_id},
            json_body={"uris": [track["uri"]]},
            expected_status=(204,),
        )
        verification = self.verify_track_playback(
            expected_track_id=str(track["id"]),
            target_device_id=target_device_id,
        )
        return {
            "provider": "spotify-web-api",
            "device_id": target_device_id,
            "track": track,
            "verification": verification,
        }


class SpotifyPlayTrackTool:
    """Cockpit-MCP tool: play a song on Spotify via Web API."""

    name = "spotify.play_track"

    _EN_PATTERNS = [
        re.compile(r"^\s*(play|start|resume)\s+(?P<q>.+?)\s+(on|in)\s+spotify\s*$", re.IGNORECASE),
        re.compile(r"^\s*spotify\s*[:\-]?\s*(play|start)\s+(?P<q>.+?)\s*$", re.IGNORECASE),
    ]

    _ZH_PATTERNS = [
        re.compile(r"^\s*(?:\u5728|\u7528)?\s*spotify\s*(?:\u64ad\u653e|\u653e)\s*(?P<q>.+?)\s*$", re.IGNORECASE),
        re.compile(r"^\s*(?:\u64ad\u653e)\s*(?P<q>.+?)\s*(?:\u5728|\u7528)\s*spotify\s*$", re.IGNORECASE),
    ]

    def __init__(self, client: SpotifyWebAPIClient) -> None:
        self._client = client

    def match(self, task: str) -> Optional[ToolMatch]:
        text = task.strip()
        if not text:
            return None

        for pattern in [*self._EN_PATTERNS, *self._ZH_PATTERNS]:
            matched = pattern.match(text)
            if not matched:
                continue

            query = matched.groupdict().get("q", "").strip(" '\"")
            if not query:
                continue

            return ToolMatch(
                tool_name=self.name,
                score=0.98,
                reason="spotify_play_pattern_matched",
                payload={"track_query": query},
            )

        lowered = text.lower()
        if "spotify" in lowered and any(token in lowered for token in ("play", "\u64ad\u653e", "\u653e")):
            fallback_query = self._heuristic_track_query(text)
            if fallback_query:
                return ToolMatch(
                    tool_name=self.name,
                    score=0.72,
                    reason="spotify_keyword_heuristic_match",
                    payload={"track_query": fallback_query},
                )

        return None

    def execute(self, task: str, context: Mapping[str, Any], match: ToolMatch) -> Dict[str, Any]:
        track_query = str(match.payload.get("track_query", "")).strip()
        if not track_query:
            raise SpotifyAPIError(f"Could not parse track query from task: {task}")

        spotify_device_id = context.get("spotify_device_id")
        result = self._client.play_track(query=track_query, device_id=spotify_device_id)

        return {
            "status": "ok",
            "tool": self.name,
            "operation": "play_track",
            "input": {"task": task, "track_query": track_query},
            "output": result,
        }

    @staticmethod
    def _heuristic_track_query(text: str) -> str:
        cleaned = re.sub(r"\bspotify\b", "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(play|start|resume)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace("\u64ad\u653e", "").replace("\u653e", "")
        cleaned = cleaned.replace("\u5728", "").replace("\u7528", "")
        return cleaned.strip(" :,-'\"")


def build_spotify_tool_from_env(strict: bool = False) -> Optional[SpotifyPlayTrackTool]:
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
    market = os.getenv("SPOTIFY_MARKET", "US")
    default_device_id = os.getenv("SPOTIFY_DEFAULT_DEVICE_ID")

    required = {
        "SPOTIFY_CLIENT_ID": client_id,
        "SPOTIFY_CLIENT_SECRET": client_secret,
        "SPOTIFY_REFRESH_TOKEN": refresh_token,
    }
    missing = [name for name, value in required.items() if not value]

    if missing:
        if strict:
            raise SpotifyConfigError(f"Missing required Spotify env vars: {', '.join(missing)}")
        return None

    cfg = SpotifyAuthConfig(
        client_id=client_id or "",
        client_secret=client_secret or "",
        refresh_token=refresh_token or "",
        market=market,
        default_device_id=default_device_id,
    )
    return SpotifyPlayTrackTool(client=SpotifyWebAPIClient(cfg))


def register_spotify_tool_to_router(router: CockpitRouter, strict: bool = False) -> bool:
    tool = build_spotify_tool_from_env(strict=strict)
    if tool is None:
        return False
    router.register_tool(tool)
    return True


def register_spotify_mcp_tool(
    mcp: Any,
    spotify_tool: Optional[SpotifyPlayTrackTool] = None,
) -> SpotifyPlayTrackTool:
    """
    Register direct MCP tool for Spotify playback.
    This is optional: router can still invoke SpotifyPlayTrackTool without this endpoint.
    """

    tool = spotify_tool or build_spotify_tool_from_env(strict=True)
    if tool is None:
        raise SpotifyConfigError("Spotify tool could not be initialized.")

    @mcp.tool
    def spotify_play_track(
        track_query: Annotated[str, Field(description="Track query, e.g. 'Hotel California Eagles'")],
        spotify_device_id: Annotated[str | None, Field(description="Optional Spotify Connect device id")] = None,
    ) -> Dict[str, Any]:
        match = ToolMatch(
            tool_name=tool.name,
            score=1.0,
            reason="explicit_spotify_tool_call",
            payload={"track_query": track_query},
        )
        return tool.execute(
            task=f"Play {track_query} on Spotify",
            context={"spotify_device_id": spotify_device_id} if spotify_device_id else {},
            match=match,
        )

    return tool

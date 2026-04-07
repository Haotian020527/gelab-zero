"""Media player app API — music playback, source selection, volume."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from ..state import get_state_manager

router = APIRouter(prefix="/api/media", tags=["media"])


class SetVolumeRequest(BaseModel):
    volume: int  # 0-100


class SetSourceRequest(BaseModel):
    source: str  # bluetooth, usb, radio, online


class SetRadioRequest(BaseModel):
    frequency: float  # e.g., 99.6


# ---------------------------------------------------------------------------

@router.get("/status")
def get_media_status():
    sm = get_state_manager()
    return sm.get("media")


@router.post("/play")
def play():
    sm = get_state_manager()
    media = sm.get("media")
    playlist = media.get("playlist", [])

    if media.get("playlist_index", -1) < 0 and playlist:
        # Start from first track
        track = playlist[0]
        sm.update("media",
                  playing=True,
                  playlist_index=0,
                  current_track=track["title"],
                  artist=track["artist"],
                  duration_sec=track["duration"],
                  progress_sec=0,
                  current_screen="media_playing")
    else:
        sm.update("media", playing=True, current_screen="media_playing")

    sm.set_active_app("media")
    return {"status": "ok", "playing": True, "track": sm.get("media")["current_track"]}


@router.post("/pause")
def pause():
    sm = get_state_manager()
    sm.update("media", playing=False)
    return {"status": "ok", "playing": False}


@router.post("/next")
def next_track():
    sm = get_state_manager()
    media = sm.get("media")
    playlist = media.get("playlist", [])
    idx = media.get("playlist_index", -1) + 1
    if idx >= len(playlist):
        idx = 0
    if playlist:
        track = playlist[idx]
        sm.update("media",
                  playlist_index=idx,
                  current_track=track["title"],
                  artist=track["artist"],
                  duration_sec=track["duration"],
                  progress_sec=0,
                  playing=True,
                  current_screen="media_playing")
    return {"status": "ok", "track": sm.get("media")["current_track"]}


@router.post("/previous")
def previous_track():
    sm = get_state_manager()
    media = sm.get("media")
    playlist = media.get("playlist", [])
    idx = media.get("playlist_index", 0) - 1
    if idx < 0:
        idx = len(playlist) - 1 if playlist else 0
    if playlist:
        track = playlist[idx]
        sm.update("media",
                  playlist_index=idx,
                  current_track=track["title"],
                  artist=track["artist"],
                  duration_sec=track["duration"],
                  progress_sec=0,
                  playing=True,
                  current_screen="media_playing")
    return {"status": "ok", "track": sm.get("media")["current_track"]}


@router.post("/volume")
def set_volume(req: SetVolumeRequest):
    sm = get_state_manager()
    vol = max(0, min(100, req.volume))
    sm.update("media", volume=vol)
    return {"status": "ok", "volume": vol}


@router.post("/source")
def set_source(req: SetSourceRequest):
    sm = get_state_manager()
    sm.update("media",
              source=req.source,
              playing=False,
              current_track="未播放",
              artist="",
              playlist_index=-1,
              progress_sec=0,
              current_screen="media_home")
    return {"status": "ok", "source": req.source}


@router.post("/radio")
def set_radio(req: SetRadioRequest):
    sm = get_state_manager()
    sm.update("media",
              source="radio",
              radio_frequency=req.frequency,
              current_track=f"FM {req.frequency}",
              artist="广播电台",
              playing=True,
              current_screen="media_radio")
    return {"status": "ok", "frequency": req.frequency}

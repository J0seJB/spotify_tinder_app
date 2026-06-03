#!/usr/bin/env python3
# api.py - Backend FastAPI para Spotify Tinder App
# Corre con: uvicorn api:app --reload --host 0.0.0.0 --port 8000

from __future__ import annotations
import os, sys, logging, time
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from spotipy.exceptions import SpotifyException

PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_DIR)
load_dotenv(os.path.join(PROJECT_DIR, ".env"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Spotify Tinder API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_cache: Dict[str, Any] = {
    "sp_user": None, "track_meta": {}, "artists_by_id": {},
    "all_liked_ids": [], "total_saved_tracks": 0, "suggestions": [], "shown_ids": set(),
    "approved_ids": set(), "approved_signals": {}, "rejected_signals": {},
    "rejected_ids": set(), "final_approved": [], "seed_ids": [], "loaded": False,
}

class SelectSeedRequest(BaseModel):
    track_ids: List[str]

class FeedbackRequest(BaseModel):
    approved: List[str]
    rejected: List[str]

class CreatePlaylistRequest(BaseModel):
    name: str
    public: bool = False

class CompletePlaylistRequest(BaseModel):
    target_total: int = 25

class PlayerPlayRequest(BaseModel):
    track_id: Optional[str] = None
    uri: Optional[str] = None
    device_id: Optional[str] = None
    position_ms: int = 0
    transfer: bool = True

class PlayerPauseRequest(BaseModel):
    device_id: Optional[str] = None

def _get_sp():
    if _cache["sp_user"] is None:
        from spotify_client import get_user_client
        _cache["sp_user"] = get_user_client()
    return _cache["sp_user"]

def _ensure_loaded(limit=None):
    if _cache["loaded"]:
        return
    from spotify_client import get_user_client, fetch_all_liked
    from main import build_track_meta
    sp_user = get_user_client()
    _cache["sp_user"] = sp_user
    logger.info("Cargando Me Gusta...")
    liked_items = fetch_all_liked(sp_user, limit=limit)
    # En Development Mode, Spotify puede rate-limitar fuerte las llamadas
    # individuales a artistas. Para que la app arranque rapido, el flujo web
    # usa nombres de artistas + Last.fm tags y no bloquea aqui por generos.
    artists_by_id = {}
    track_meta = build_track_meta(liked_items, artists_by_id)
    _cache["artists_by_id"] = artists_by_id
    _cache["track_meta"] = track_meta
    _cache["all_liked_ids"] = list(track_meta.keys())
    _cache["total_saved_tracks"] = len(liked_items)
    _cache["loaded"] = True
    logger.info(f"Cargadas {len(liked_items)} canciones de Spotify, {len(track_meta)} unicas.")

def _extract_signals(tid):
    meta = _cache["track_meta"].get(tid, {})
    genres = list(meta.get("genres", []) or [])
    artists = [a.strip().lower() for a in meta.get("artists", "").split(";") if a.strip()]
    for aid in meta.get("artist_ids", []):
        art = _cache["artists_by_id"].get(aid, {})
        genres.extend(art.get("genres", []))
        name = art.get("name", "")
        if name and name.lower() not in artists:
            artists.append(name.lower())
    return genres + artists

def _track_key(tid: str) -> str:
    meta = _cache["track_meta"].get(tid, {})
    if meta.get("duplicate_key"):
        return meta["duplicate_key"]
    try:
        from main import track_duplicate_key
        return track_duplicate_key(meta.get("name", ""), meta.get("artists", ""))
    except Exception:
        artists = (meta.get("artists", "") or "").split(";")[0].strip().lower()
        return f"{meta.get('name', '').strip().lower()}::{artists}"

def _keys_for_ids(track_ids) -> set[str]:
    return {_track_key(tid) for tid in track_ids if tid}

def _card_from_track(tid: str, score: float, meta: Dict[str, Any]) -> Dict[str, Any]:
    details = _get_track_details(tid)
    return {
        "id": tid,
        "name": meta.get("name", ""),
        "artists": meta.get("artists", ""),
        "album": details["album_name"],
        "score": score,
        "image_url": details["image_url"],
        "preview_url": details["preview_url"],
        "uri": meta.get("uri") or details["uri"],
        "external_url": details["external_url"],
    }

def _update_signals(tids, weight, signal_dict):
    for tid in tids:
        for s in _extract_signals(tid):
            signal_dict[s] = signal_dict.get(s, 0.0) + weight

def _rescore(suggestions):
    approved_s = _cache["approved_signals"]
    rejected_s = _cache["rejected_signals"]
    shown = _cache["shown_ids"]
    approved = _cache["approved_ids"]
    blocked_keys = _keys_for_ids(shown | approved | set(_cache["final_approved"]) | set(_cache.get("rejected_ids", set())))
    scored = []
    for tid, base_score, meta in suggestions:
        if tid in approved or tid in shown:
            continue
        key = _track_key(tid)
        if key and key in blocked_keys:
            continue
        signals = _extract_signals(tid)
        if not signals:
            scored.append((tid, base_score, meta))
            continue
        bonus = sum(approved_s.get(s, 0.0) for s in signals)
        penalty = sum(rejected_s.get(s, 0.0) for s in signals)
        mp = len(signals)
        score = base_score + (bonus / mp) * 0.4 - (penalty / mp) * 0.5
        scored.append((tid, round(max(0.0, min(1.0, score)), 4), meta))

    scored.sort(key=lambda x: -x[1])
    rescored = []
    seen_keys = set(blocked_keys)
    for tid, score, meta in scored:
        key = _track_key(tid)
        if key and key in seen_keys:
            continue
        rescored.append((tid, score, meta))
        blocked_keys.add(key)
        seen_keys.add(key)
    return rescored

def _complete_state() -> Dict[str, Any]:
    remaining = len(_rescore(_cache["suggestions"])) if _cache["suggestions"] else 0
    selected = len(_cache["final_approved"])
    enough_signal = selected >= 5
    return {
        "can_complete": bool(enough_signal and remaining > 0),
        "selected": selected,
        "remaining": remaining,
        "min_selected": 5,
    }

def _get_track_details(tid: str):
    meta = _cache["track_meta"].get(tid, {})
    return {
        "image_url": meta.get("image_url"),
        "preview_url": meta.get("preview_url"),
        "album_name": meta.get("album_name", ""),
        "external_url": meta.get("external_url"),
        "uri": meta.get("uri", ""),
    }

def _spotify_http_exception(exc: SpotifyException) -> HTTPException:
    status = getattr(exc, "http_status", None) or 502
    msg = getattr(exc, "msg", None) or getattr(exc, "reason", None) or str(exc)

    if status == 401:
        detail = "Spotify pidio volver a autorizar la cuenta. Borra el archivo .cache de Spotify y reinicia el backend."
    elif status == 403:
        detail = (
            "Spotify rechazo el control de reproduccion. Normalmente necesitas Spotify Premium "
            "y volver a autorizar con los scopes nuevos; borra .cache-<usuario> si el token es anterior."
        )
    elif status == 404:
        detail = "No hay un dispositivo Spotify disponible. Abre Spotify en tu celular, PC o Web Player e intenta de nuevo."
    elif status == 429:
        detail = "Spotify aplico rate limit. Espera unos segundos e intenta de nuevo."
    else:
        detail = f"Error de Spotify: {msg}"

    return HTTPException(status_code=status if status < 500 else 502, detail=detail)

def _normalize_device(device: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": device.get("id"),
        "name": device.get("name", "Spotify"),
        "type": device.get("type", ""),
        "is_active": bool(device.get("is_active")),
        "is_restricted": bool(device.get("is_restricted")),
        "volume_percent": device.get("volume_percent"),
        "supports_volume": bool(device.get("supports_volume")),
    }

def _select_playback_device(devices: List[Dict[str, Any]], requested_id: Optional[str] = None):
    playable = [d for d in devices if d.get("id") and not d.get("is_restricted")]
    if requested_id:
        return next((d for d in playable if d.get("id") == requested_id), None)
    return (
        next((d for d in playable if d.get("is_active")), None)
        or (playable[0] if playable else None)
    )

def _resolve_track_uri(req: PlayerPlayRequest) -> str:
    uri = (req.uri or "").strip()
    if uri:
        return uri
    track_id = (req.track_id or "").strip()
    if not track_id:
        raise HTTPException(status_code=400, detail="Falta track_id o uri")
    return _cache["track_meta"].get(track_id, {}).get("uri") or f"spotify:track:{track_id}"

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/status")
def status():
    completion = _complete_state()
    return {
        "loaded": _cache["loaded"],
        "total_tracks": len(_cache["all_liked_ids"]),
        "total_spotify": _cache.get("total_saved_tracks", len(_cache["all_liked_ids"])),
        "total_unique": len(_cache["all_liked_ids"]),
        "seeds": len(_cache["seed_ids"]),
        "approved": len(_cache["final_approved"]),
        "completion": completion,
    }

@app.get("/player/devices")
def player_devices():
    try:
        sp = _get_sp()
        devices = [_normalize_device(d) for d in (sp.devices() or {}).get("devices", [])]
        active = next((d for d in devices if d["is_active"]), None)
        return {"devices": devices, "active_device": active}
    except SpotifyException as e:
        raise _spotify_http_exception(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/player/play")
def player_play(req: PlayerPlayRequest):
    uri = _resolve_track_uri(req)
    if not uri.startswith("spotify:track:"):
        raise HTTPException(status_code=400, detail="Solo se puede reproducir una URI spotify:track")

    try:
        sp = _get_sp()
        devices_raw = (sp.devices() or {}).get("devices", [])
        device = _select_playback_device(devices_raw, req.device_id)
        if not device:
            raise HTTPException(
                status_code=404,
                detail="Abre Spotify en un dispositivo y vuelve a intentar.",
            )

        device_id = device.get("id")
        if req.transfer and not device.get("is_active"):
            sp.transfer_playback(device_id=device_id, force_play=True)
            time.sleep(0.5)

        sp.start_playback(
            device_id=device_id,
            uris=[uri],
            position_ms=max(0, int(req.position_ms or 0)),
        )
        return {"ok": True, "uri": uri, "device": _normalize_device(device)}
    except HTTPException:
        raise
    except SpotifyException as e:
        raise _spotify_http_exception(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/player/pause")
def player_pause(req: PlayerPauseRequest):
    try:
        sp = _get_sp()
        sp.pause_playback(device_id=req.device_id)
        return {"ok": True}
    except SpotifyException as e:
        raise _spotify_http_exception(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/load")
def load_tracks(limit: Optional[int] = None):
    try:
        _ensure_loaded(limit=limit)
        return {
            "ok": True,
            "total": len(_cache["all_liked_ids"]),
            "total_spotify": _cache.get("total_saved_tracks", len(_cache["all_liked_ids"])),
            "total_unique": len(_cache["all_liked_ids"]),
            "duplicates_removed": max(0, _cache.get("total_saved_tracks", len(_cache["all_liked_ids"])) - len(_cache["all_liked_ids"])),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search")
def search_tracks(q: str):
    if not _cache["loaded"]:
        raise HTTPException(status_code=400, detail="Primero llama /load")
    q_lower = q.lower()
    results = []
    seen_keys = set()
    for tid, meta in _cache["track_meta"].items():
        key = _track_key(tid)
        if key in seen_keys:
            continue
        if q_lower in meta.get("name", "").lower() or q_lower in meta.get("artists", "").lower():
            results.append({"id": tid, "name": meta.get("name", ""), "artists": meta.get("artists", "")})
            seen_keys.add(key)
        if len(results) >= 10:
            break
    return {"results": results}

@app.post("/seeds")
def set_seeds(req: SelectSeedRequest):
    if not _cache["loaded"]:
        raise HTTPException(status_code=400, detail="Primero llama /load")
    try:
        from ai_playlist import suggest_from_seeds
        _cache["seed_ids"] = req.track_ids
        _cache["shown_ids"] = set(req.track_ids)
        _cache["approved_ids"] = set(req.track_ids)
        _cache["approved_signals"] = {}
        _cache["rejected_signals"] = {}
        _cache["rejected_ids"] = set()
        _cache["final_approved"] = list(req.track_ids)
        _update_signals(req.track_ids, 1.0, _cache["approved_signals"])
        result = suggest_from_seeds(
            seed_track_ids=req.track_ids,
            all_liked_ids=_cache["all_liked_ids"],
            features_by_id={},
            artists_by_id=_cache["artists_by_id"],
            track_meta=_cache["track_meta"],
            top_n=150,
            use_ai_description=False,
        )
        _cache["suggestions"] = result["suggestions"]
        return {
            "ok": True,
            "seeds": len(req.track_ids),
            "suggestions": len(_cache["suggestions"]),
            "profile": {
                "genres": list(result["profile"].get("genres", set()))[:6],
                "tags": result["profile"].get("tags", [])[:6],
                "themes": result["profile"].get("dominant_themes", []),
            }
        }
    except Exception as e:
        logger.exception("Error en /seeds")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/next")
def get_next_batch(count: int = 1):
    """Devuelve la siguiente cancion (o lote) con imagen y URI para Spotify Connect."""
    if not _cache["suggestions"]:
        return {"cards": [], "remaining": 0}
    pool = _rescore(_cache["suggestions"])
    batch = pool[:count]
    cards = []
    for tid, score, meta in batch:
        _cache["shown_ids"].add(tid)
        cards.append(_card_from_track(tid, score, meta))
    completion = _complete_state()
    completion["remaining"] = max(0, len(pool) - len(batch))
    completion["can_complete"] = bool(completion["selected"] >= completion["min_selected"] and completion["remaining"] > 0)
    return {"cards": cards, "remaining": completion["remaining"], "completion": completion}

@app.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    if req.approved:
        _update_signals(req.approved, 1.0, _cache["approved_signals"])
        for tid in req.approved:
            _cache["approved_ids"].add(tid)
            if tid not in _cache["final_approved"]:
                _cache["final_approved"].append(tid)
    if req.rejected:
        _update_signals(req.rejected, 0.6, _cache["rejected_signals"])
        _cache.setdefault("rejected_ids", set()).update(req.rejected)
    remaining = len(_rescore(_cache["suggestions"])) if _cache["suggestions"] else 0
    top_liked = sorted(_cache["approved_signals"].items(), key=lambda x: -x[1])[:5]
    top_avoid = sorted(_cache["rejected_signals"].items(), key=lambda x: -x[1])[:3]
    return {
        "ok": True,
        "approved_total": len(_cache["final_approved"]),
        "remaining": remaining,
        "completion": _complete_state(),
        "learning": {
            "likes": [s for s, _ in top_liked],
            "dislikes": [s for s, _ in top_avoid],
        }
    }

@app.post("/complete-playlist")
def complete_playlist(req: CompletePlaylistRequest):
    if not _cache["suggestions"]:
        raise HTTPException(status_code=400, detail="No hay sugerencias para completar")

    target_total = max(1, min(int(req.target_total or 25), 100))
    current_total = len(_cache["final_approved"])
    state = _complete_state()
    if not state["can_complete"]:
        raise HTTPException(
            status_code=400,
            detail=f"Necesitas al menos {state['min_selected']} canciones seleccionadas y sugerencias restantes",
        )
    if current_total >= target_total:
        return {
            "ok": True,
            "added": 0,
            "approved_total": current_total,
            "target_total": target_total,
            "remaining": state["remaining"],
            "tracks": [],
        }

    needed = target_total - current_total
    selected = []
    selected_cards = []
    for tid, score, meta in _rescore(_cache["suggestions"]):
        if tid in _cache["final_approved"]:
            continue
        selected.append(tid)
        selected_cards.append(_card_from_track(tid, score, meta))
        if len(selected) >= needed:
            break

    for tid in selected:
        _cache["approved_ids"].add(tid)
        _cache["shown_ids"].add(tid)
        _cache["final_approved"].append(tid)
    if selected:
        _update_signals(selected, 0.8, _cache["approved_signals"])

    return {
        "ok": True,
        "added": len(selected),
        "approved_total": len(_cache["final_approved"]),
        "target_total": target_total,
        "remaining": len(_rescore(_cache["suggestions"])),
        "tracks": selected_cards,
    }

@app.post("/create-playlist")
def create_playlist(req: CreatePlaylistRequest):
    if not _cache["final_approved"]:
        raise HTTPException(status_code=400, detail="No hay canciones aprobadas")
    try:
        from spotify_client import ensure_playlist, get_playlist_track_uris, add_tracks_in_chunks
        sp = _get_sp()
        me = sp.current_user()
        user_id = me["id"]
        pid = ensure_playlist(sp, user_id, req.name, req.public)
        existing = get_playlist_track_uris(sp, pid)
        uris = []
        added_keys = set()
        for tid in _cache["final_approved"]:
            uri = _cache["track_meta"].get(tid, {}).get("uri", "")
            key = _track_key(tid)
            if uri and uri not in existing and uri not in uris and key not in added_keys:
                uris.append(uri)
                added_keys.add(key)
        if uris:
            add_tracks_in_chunks(sp, pid, uris)
        return {"ok": True, "playlist_name": req.name, "tracks_added": len(uris), "playlist_id": pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/reset")
def reset_session():
    _cache.update({
        "suggestions": [], "shown_ids": set(), "approved_ids": set(),
        "approved_signals": {}, "rejected_signals": {}, "rejected_ids": set(), "final_approved": [], "seed_ids": [],
    })
    return {"ok": True}

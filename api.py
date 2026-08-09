#!/usr/bin/env python3
# api.py — Backend FastAPI para Spotify Tinder App
# Corre con: uvicorn api:app --reload --host 0.0.0.0 --port 8000

from __future__ import annotations
import os, sys, logging
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, PROJECT_DIR)
load_dotenv(os.path.join(PROJECT_DIR, ".env"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Spotify Tinder API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_cache: Dict[str, Any] = {
    "sp_user": None, "track_meta": {}, "artists_by_id": {},
    "all_liked_ids": [], "suggestions": [], "shown_ids": set(),
    "approved_ids": set(), "approved_signals": {}, "rejected_signals": {},
    "final_approved": [], "seed_ids": [], "loaded": False,
}

class SelectSeedRequest(BaseModel):
    track_ids: List[str]

class FeedbackRequest(BaseModel):
    approved: List[str]
    rejected: List[str]

class CreatePlaylistRequest(BaseModel):
    name: str
    public: bool = False

def _get_sp():
    if _cache["sp_user"] is None:
        from spotify_client import get_user_client
        _cache["sp_user"] = get_user_client()
    return _cache["sp_user"]

from fastapi.responses import RedirectResponse


def _ensure_loaded(limit=None, access_token: Optional[str] = None):
    """Attempt to load a user's liked tracks.

    If access_token is provided, use it to fetch the user's saved tracks.
    Otherwise fall back to the app/user client configured for the server.

    Errors are caught and the API is kept responsive by setting empty caches.
    """
    if _cache["loaded"]:
        return
    from spotify_client import get_user_client, get_app_client, fetch_all_liked, get_artists_info
    from main import build_track_meta
    try:
        # Prefer using the provided access token for user-specific data
        if access_token:
            import spotipy
            sp_user = spotipy.Spotify(auth=access_token, requests_timeout=20, retries=3)
            sp_app = get_app_client()
            _cache["sp_user"] = sp_user
        else:
            sp_user = get_user_client()
            sp_app = get_app_client()
            _cache["sp_user"] = sp_user

        logger.info("Cargando Me Gusta...")
        liked_items = fetch_all_liked(sp_user, limit=limit)
        all_artist_ids = []
        for it in liked_items:
            tr = it.get("track") or {}
            for a in tr.get("artists", []) or []:
                if a.get("id"):
                    all_artist_ids.append(a["id"])
        artists_by_id = get_artists_info(sp_app, all_artist_ids)
        track_meta = build_track_meta(liked_items, artists_by_id)
        _cache["artists_by_id"] = artists_by_id
        _cache["track_meta"] = track_meta
        _cache["all_liked_ids"] = list(track_meta.keys())
        _cache["loaded"] = True
        logger.info(f"Cargadas {len(track_meta)} canciones.")
    except Exception as e:
        # Do not raise — keep the API responsive. Provide helpful log message.
        logger.warning(f"No se pudieron cargar Me Gusta desde Spotify: {e}")
        # Leave caches empty but mark as loaded to avoid repeated failing attempts.
        _cache["artists_by_id"] = {}
        _cache["track_meta"] = {}
        _cache["all_liked_ids"] = []
        _cache["loaded"] = True


@app.get("/login")
def login():
    """Redirect user to Spotify authorization page."""
    try:
        from spotipy.oauth2 import SpotifyOAuth
        cid = os.getenv("SPOTIFY_CLIENT_ID")
        sec = os.getenv("SPOTIFY_CLIENT_SECRET")
        redirect = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8000/callback")
        scope = "user-library-read playlist-modify-public playlist-modify-private"
        auth = SpotifyOAuth(client_id=cid, client_secret=sec, redirect_uri=redirect, scope=scope)
        url = auth.get_authorize_url()
        return RedirectResponse(url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/callback")
def callback(code: Optional[str] = None, state: Optional[str] = None):
    """Exchange authorization code for an access token and redirect to frontend with token in fragment.

    The frontend should capture the access_token from the URL fragment and use it for API calls
    (e.g., include Authorization: Bearer <token> in requests).
    """
    try:
        from spotipy.oauth2 import SpotifyOAuth
        cid = os.getenv("SPOTIFY_CLIENT_ID")
        sec = os.getenv("SPOTIFY_CLIENT_SECRET")
        redirect = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8000/callback")
        scope = "user-library-read playlist-modify-public playlist-modify-private"
        auth = SpotifyOAuth(client_id=cid, client_secret=sec, redirect_uri=redirect, scope=scope)
        token_info = auth.get_access_token(code)
        access_token = token_info.get("access_token") if isinstance(token_info, dict) else token_info
        frontend = os.getenv("FRONTEND_URL", "http://localhost:19006")
        # Redirect with token in fragment so it is not sent to the server in logs
        redirect_url = f"{frontend}#access_token={access_token}"
        return RedirectResponse(redirect_url)
    except Exception as e:
        logger.exception("Error during Spotify callback")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/load")
def load_tracks(limit: int = 3452, authorization: Optional[str] = Header(None)):
    """Load liked tracks for the authenticated user.

    If the frontend provides an Authorization: Bearer <token> header, use that token to load the
    user's library. Otherwise fall back to the server app/user credentials.
    """
    access_token = None
    if authorization and authorization.lower().startswith("bearer "):
        access_token = authorization.split(" ", 1)[1]
    _ensure_loaded(limit=limit, access_token=access_token)
    return {"ok": True, "total": len(_cache["all_liked_ids"]) }

def _extract_signals(tid):
    meta = _cache["track_meta"].get(tid, {})
    genres, artists = [], []
    for aid in meta.get("artist_ids", []):
        art = _cache["artists_by_id"].get(aid, {})
        genres.extend(art.get("genres", []))
        name = art.get("name", "")
        if name:
            artists.append(name.lower())
    return genres + artists

def _update_signals(tids, weight, signal_dict):
    for tid in tids:
        for s in _extract_signals(tid):
            signal_dict[s] = signal_dict.get(s, 0.0) + weight

def _rescore(suggestions):
    approved_s = _cache["approved_signals"]
    rejected_s = _cache["rejected_signals"]
    shown = _cache["shown_ids"]
    approved = _cache["approved_ids"]
    rescored = []
    for tid, base_score, meta in suggestions:
        if tid in approved or tid in shown:
            continue
        signals = _extract_signals(tid)
        if not signals:
            rescored.append((tid, base_score, meta))
            continue
        bonus = sum(approved_s.get(s, 0.0) for s in signals)
        penalty = sum(rejected_s.get(s, 0.0) for s in signals)
        mp = len(signals)
        score = base_score + (bonus / mp) * 0.4 - (penalty / mp) * 0.5
        rescored.append((tid, round(max(0.0, min(1.0, score)), 4), meta))
    rescored.sort(key=lambda x: -x[1])
    return rescored

def _get_track_details(tid: str):
    try:
        sp = _get_sp()
        track = sp.track(tid)
        images = track.get("album", {}).get("images", [])
        image_url = images[0]["url"] if images else None
        preview_url = track.get("preview_url")
        album_name = track.get("album", {}).get("name", "")
        return image_url, preview_url, album_name
    except Exception:
        return None, None, ""

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/status")
def status():
    return {
        "loaded": _cache["loaded"],
        "total_tracks": len(_cache["all_liked_ids"]),
        "seeds": len(_cache["seed_ids"]),
        "approved": len(_cache["final_approved"]),
    }

@app.get("/search")
def search_tracks(q: str):
    if not _cache["loaded"]:
        raise HTTPException(status_code=400, detail="Primero llama /load")
    q_lower = q.lower()
    results = []
    for tid, meta in _cache["track_meta"].items():
        if q_lower in meta.get("name", "").lower() or q_lower in meta.get("artists", "").lower():
            results.append({"id": tid, "name": meta.get("name", ""), "artists": meta.get("artists", "")})
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
    """Devuelve la siguiente canción (o lote) con imagen y preview."""
    if not _cache["suggestions"]:
        return {"cards": [], "remaining": 0}
    pool = _rescore(_cache["suggestions"])
    batch = pool[:count]
    cards = []
    for tid, score, meta in batch:
        _cache["shown_ids"].add(tid)
        image_url, preview_url, album_name = _get_track_details(tid)
        cards.append({
            "id": tid,
            "name": meta.get("name", ""),
            "artists": meta.get("artists", ""),
            "album": album_name,
            "score": score,
            "image_url": image_url,
            "preview_url": preview_url,
        })
    return {"cards": cards, "remaining": max(0, len(pool) - count)}

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
    top_liked = sorted(_cache["approved_signals"].items(), key=lambda x: -x[1])[:5]
    top_avoid = sorted(_cache["rejected_signals"].items(), key=lambda x: -x[1])[:3]
    return {
        "ok": True,
        "approved_total": len(_cache["final_approved"]),
        "learning": {
            "likes": [s for s, _ in top_liked],
            "dislikes": [s for s, _ in top_avoid],
        }
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
        for tid in _cache["final_approved"]:
            uri = _cache["track_meta"].get(tid, {}).get("uri", "")
            if uri and uri not in existing and uri not in uris:
                uris.append(uri)
        if uris:
            add_tracks_in_chunks(sp, pid, uris)
        return {"ok": True, "playlist_name": req.name, "tracks_added": len(uris), "playlist_id": pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/reset")
def reset_session():
    _cache.update({
        "suggestions": [], "shown_ids": set(), "approved_ids": set(),
        "approved_signals": {}, "rejected_signals": {}, "final_approved": [], "seed_ids": [],
    })
    return {"ok": True}

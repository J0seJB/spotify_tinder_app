#!/usr/bin/env python3
# api.py — Backend FastAPI para Spotify Tinder App
# Corre con: uvicorn api:app --reload --host 0.0.0.0 --port 8000

from __future__ import annotations
import os, sys, logging, secrets
import hashlib
import threading
from contextvars import ContextVar
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode, quote, urlsplit
import requests
from fastapi import FastAPI, HTTPException, Header, Request
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

def _new_session_cache() -> Dict[str, Any]:
    return {
        "sp_user": None, "track_meta": {}, "artists_by_id": {},
        "all_liked_ids": [], "suggestions": [], "shown_ids": set(),
        "approved_ids": set(), "approved_signals": {}, "rejected_signals": {},
        "final_approved": [], "seed_ids": [], "loaded": False,
    }


_anonymous_cache = _new_session_cache()
_session_caches: Dict[str, Dict[str, Any]] = {}
_session_caches_lock = threading.Lock()
_current_cache: ContextVar[Optional[Dict[str, Any]]] = ContextVar("spotify_tinder_cache", default=None)


def _cache_for_access_token(access_token: str) -> Dict[str, Any]:
    session_key = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
    with _session_caches_lock:
        return _session_caches.setdefault(session_key, _new_session_cache())


def _active_cache() -> Dict[str, Any]:
    return _current_cache.get() or _anonymous_cache


class _SessionCacheProxy:
    def __getitem__(self, key):
        return _active_cache()[key]

    def __setitem__(self, key, value):
        _active_cache()[key] = value

    def get(self, key, default=None):
        return _active_cache().get(key, default)

    def update(self, values):
        _active_cache().update(values)

    def clear(self):
        _active_cache().clear()

    def copy(self):
        return _active_cache().copy()


_cache = _SessionCacheProxy()


@app.middleware("http")
async def isolate_user_session(request: Request, call_next):
    authorization = request.headers.get("authorization", "")
    access_token = None
    if authorization.lower().startswith("bearer "):
        access_token = authorization.split(" ", 1)[1].strip()
    cache = _cache_for_access_token(access_token) if access_token else _anonymous_cache
    context_token = _current_cache.set(cache)
    try:
        return await call_next(request)
    finally:
        _current_cache.reset(context_token)

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

    This function keeps the API responsive by using a cached load for the same
    auth mode, but it also reloads if a different Spotify user token is provided.
    """
    if _cache["loaded"]:
        if access_token:
            if _cache.get("loaded_auth_mode") == "user":
                return
        elif _cache.get("loaded_auth_mode") == "app":
            return

    from spotify_client import get_user_client, get_app_client, fetch_all_liked, get_artists_info
    from main import build_track_meta
    try:
        if access_token:
            import spotipy
            sp_user = spotipy.Spotify(auth=access_token, requests_timeout=20, retries=3)
            _cache["sp_user"] = sp_user
            loaded_auth_mode = "user"
            logger.info("Cargando biblioteca Spotify del usuario autenticado...")
            liked_items = fetch_all_liked(sp_user, limit=limit, raise_on_error=True)
            artists_by_id = {}
        else:
            sp_user = get_user_client()
            sp_app = get_app_client()
            _cache["sp_user"] = sp_user
            loaded_auth_mode = "app"
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
        _cache["loaded_auth_mode"] = loaded_auth_mode
        logger.info(f"Cargadas {len(track_meta)} canciones.")
    except Exception as e:
        if access_token:
            logger.warning(f"No se pudieron cargar Me Gusta para el token proporcionado: {e}")
            raise
        logger.warning(f"No se pudieron cargar Me Gusta desde Spotify: {e}")
        _cache["artists_by_id"] = {}
        _cache["track_meta"] = {}
        _cache["all_liked_ids"] = []
        _cache["loaded"] = True
        _cache["loaded_auth_mode"] = "app"


@app.get("/login")
def login(request: Request):
    """Redirect user to Spotify authorization page."""
    cid = os.getenv("SPOTIFY_CLIENT_ID")
    redirect = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8000/callback")
    if not cid or not os.getenv("SPOTIFY_CLIENT_SECRET"):
        raise HTTPException(status_code=500, detail="Faltan credenciales de Spotify en el backend.")

    state = secrets.token_urlsafe(32)
    scope = "user-library-read playlist-modify-public playlist-modify-private"
    url = "https://accounts.spotify.com/authorize?" + urlencode({
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": scope,
        "state": state,
    })
    response = RedirectResponse(url)
    response.set_cookie(
        "spotify_oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/callback",
    )
    return response


@app.get("/callback")
def callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Exchange a one-time authorization code and return the token to the SPA."""
    expected_state = request.cookies.get("spotify_oauth_state")
    if not state or not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(status_code=400, detail="La autorización expiró o no es válida. Intenta iniciar sesión otra vez.")
    if error or not code:
        raise HTTPException(status_code=400, detail="Spotify no completó la autorización.")

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8000/callback")
    frontend = os.getenv("FRONTEND_URL", "http://localhost:19006")
    frontend_parts = urlsplit(frontend)
    if (
        frontend_parts.scheme not in ("http", "https")
        or not frontend_parts.netloc
        or frontend_parts.query
        or frontend_parts.fragment
    ):
        raise HTTPException(
            status_code=500,
            detail="FRONTEND_URL debe ser una URL completa, por ejemplo https://tu-app.vercel.app",
        )

    try:
        response = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            auth=(client_id or "", client_secret or ""),
            timeout=20,
        )
        response.raise_for_status()
        token_info = response.json()
    except requests.RequestException:
        logger.exception("Spotify token exchange failed")
        raise HTTPException(status_code=502, detail="Spotify no pudo completar el inicio de sesión.")

    access_token = token_info.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="Spotify no devolvió un token de acceso.")

    redirect_url = f"{frontend.rstrip('/')}#access_token={quote(access_token, safe='')}"
    result = RedirectResponse(redirect_url)
    result.delete_cookie(
        "spotify_oauth_state",
        path="/callback",
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="lax",
    )
    return result


@app.post("/load")
def load_tracks(limit: int = 3452, authorization: Optional[str] = Header(None)):
    """Load liked tracks for the authenticated user.

    If the frontend provides an Authorization: Bearer <token> header, use that token to load the
    user's library. Otherwise fall back to the server app/user credentials.
    """
    access_token = None
    if authorization and authorization.lower().startswith("bearer "):
        access_token = authorization.split(" ", 1)[1]
    try:
        if not access_token:
            raise HTTPException(status_code=401, detail="Inicia sesión con Spotify para cargar tu biblioteca.")
        _ensure_loaded(limit=limit, access_token=access_token)
        return {"ok": True, "total": len(_cache["all_liked_ids"])}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("No se pudo cargar la biblioteca del usuario autenticado")
        if getattr(exc, "http_status", None) == 403:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Spotify denegó el acceso a esta cuenta. Si tu app está en Development mode, "
                    "añade el correo exacto de esta cuenta Spotify en Spotify Developer Dashboard → "
                    "tu app → Settings → Users Management, acepta la invitación y vuelve a iniciar sesión. "
                    "El propietario de la app también necesita Spotify Premium en Development mode."
                ),
            ) from exc
        if getattr(exc, "http_status", None) == 401:
            raise HTTPException(
                status_code=401,
                detail="La sesión de Spotify expiró. Vuelve a iniciar sesión y acepta los permisos solicitados.",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail="Spotify rechazó la carga de tu biblioteca. Vuelve a iniciar sesión y acepta el permiso para leer tu biblioteca.",
        ) from exc

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
    meta = _cache["track_meta"].get(tid, {})
    if "image_url" in meta or "preview_url" in meta or "album_name" in meta:
        return meta.get("image_url"), meta.get("preview_url"), meta.get("album_name", "")
    try:
        sp = _get_sp()
        track = sp.track(tid)
        images = track.get("album", {}).get("images", [])
        image_url = images[0]["url"] if images else None
        preview_url = track.get("preview_url")
        album_name = track.get("album", {}).get("name", "")
        meta.update({
            "image_url": image_url,
            "preview_url": preview_url,
            "album_name": album_name,
        })
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

@app.get("/library")
def get_library(offset: int = 0, limit: int = 50):
    if not _cache["loaded"]:
        raise HTTPException(status_code=400, detail="Primero llama /load")
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Paginación inválida.")
    ids = _cache["all_liked_ids"][offset:offset + limit]
    return {
        "results": [_library_track(tid) for tid in ids],
        "offset": offset,
        "limit": limit,
        "total": len(_cache["all_liked_ids"]),
    }


def _library_track(tid: str) -> Dict[str, Any]:
    meta = _cache["track_meta"].get(tid, {})
    return {
        "id": tid,
        "name": meta.get("name", ""),
        "artists": meta.get("artists", ""),
        "image_url": meta.get("image_url"),
        "preview_url": meta.get("preview_url"),
        "in_library": True,
    }


@app.get("/search")
def search_tracks(q: str, source: str = "library", authorization: Optional[str] = Header(None)):
    if not _cache["loaded"]:
        raise HTTPException(status_code=400, detail="Primero llama /load")
    if len(q.strip()) < 2:
        return {"results": []}

    q_lower = q.lower()
    if source == "library":
        results = []
        for tid in _cache["all_liked_ids"]:
            meta = _cache["track_meta"].get(tid, {})
            if q_lower in meta.get("name", "").lower() or q_lower in meta.get("artists", "").lower():
                results.append(_library_track(tid))
            if len(results) >= 30:
                break
        return {"results": results}
    if source != "spotify":
        raise HTTPException(status_code=400, detail="Origen de búsqueda inválido.")

    access_token = None
    if authorization and authorization.lower().startswith("bearer "):
        access_token = authorization.split(" ", 1)[1].strip()
    if not access_token:
        raise HTTPException(status_code=401, detail="Inicia sesión con Spotify para buscar canciones.")

    try:
        import spotipy
        sp = spotipy.Spotify(auth=access_token, requests_timeout=20, retries=2)
        response = sp.search(q=q.strip(), type="track", limit=20)
    except Exception as exc:
        logger.exception("Spotify catalog search failed")
        raise HTTPException(status_code=502, detail="No se pudo buscar en Spotify. Inténtalo de nuevo.") from exc

    results = []
    for track in response.get("tracks", {}).get("items", []):
        track_id = track.get("id")
        if not track_id:
            continue
        artist_objects = track.get("artists", []) or []
        artist_ids = [artist.get("id") for artist in artist_objects if artist.get("id")]
        album = track.get("album", {}) or {}
        images = album.get("images", []) or []
        meta = {
            "name": track.get("name", ""),
            "uri": track.get("uri", f"spotify:track:{track_id}"),
            "artists": "; ".join(artist.get("name", "") for artist in artist_objects if artist.get("name")),
            "artist_ids": artist_ids,
            "genres": [],
            "album_name": album.get("name", ""),
            "image_url": images[0].get("url") if images else None,
            "preview_url": track.get("preview_url"),
        }
        _cache["track_meta"][track_id] = meta
        for artist in artist_objects:
            if artist.get("id"):
                _cache["artists_by_id"].setdefault(
                    artist["id"],
                    {"name": artist.get("name", ""), "genres": []},
                )
        results.append({
            "id": track_id,
            "name": meta["name"],
            "artists": meta["artists"],
            "image_url": meta["image_url"],
            "preview_url": meta["preview_url"],
            "in_library": track_id in _cache["all_liked_ids"],
        })
    return {"results": results}

@app.post("/seeds")
def set_seeds(req: SelectSeedRequest):
    if not _cache["loaded"]:
        raise HTTPException(status_code=400, detail="Primero llama /load")
    if not req.track_ids:
        raise HTTPException(status_code=400, detail="Selecciona al menos una canción semilla.")
    missing_ids = [track_id for track_id in req.track_ids if track_id not in _cache["track_meta"]]
    if missing_ids:
        raise HTTPException(status_code=400, detail="Busca las canciones semilla antes de seleccionarlas.")
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
def create_playlist(req: CreatePlaylistRequest, authorization: Optional[str] = Header(None)):
    if not _cache["final_approved"]:
        raise HTTPException(status_code=400, detail="No hay canciones aprobadas")
    access_token = None
    if authorization and authorization.lower().startswith("bearer "):
        access_token = authorization.split(" ", 1)[1].strip()
    if not access_token:
        raise HTTPException(status_code=401, detail="Inicia sesión con Spotify antes de guardar la playlist.")
    try:
        from spotify_client import ensure_playlist, get_playlist_track_uris, add_tracks_in_chunks
        import spotipy
        sp = spotipy.Spotify(auth=access_token, requests_timeout=20, retries=3)
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

# spotify_client.py - clientes Spotify compartidos (sin duplicar en cada modulo)
from __future__ import annotations
import os
import time
import logging
from typing import List, Dict, Any, Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyClientCredentials
from spotipy.exceptions import SpotifyException
from dotenv import load_dotenv
from tqdm import tqdm

logger = logging.getLogger(__name__)

SCOPES = [
    "user-library-read",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-read-playback-state",
    "user-modify-playback-state",
]


def _load_credentials() -> tuple[str, str]:
    load_dotenv()
    cid = os.getenv("SPOTIFY_CLIENT_ID")
    sec = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not cid or not sec:
        raise RuntimeError("Faltan SPOTIFY_CLIENT_ID o SPOTIFY_CLIENT_SECRET en .env")
    return cid, sec


def get_user_client() -> spotipy.Spotify:
    cid, sec = _load_credentials()
    redir = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:9090/callback")
    username = os.getenv("SPOTIFY_USERNAME", "default")
    auth = SpotifyOAuth(
        client_id=cid, client_secret=sec, redirect_uri=redir,
        scope=" ".join(SCOPES), cache_path=".cache-" + username,
        show_dialog=False, requests_timeout=20,
    )
    return spotipy.Spotify(
        auth_manager=auth, requests_timeout=20, retries=10,
        status_forcelist=(429, 500, 502, 503, 504), backoff_factor=0.4,
    )


def get_app_client() -> spotipy.Spotify:
    cid, sec = _load_credentials()
    creds = SpotifyClientCredentials(client_id=cid, client_secret=sec)
    return spotipy.Spotify(
        auth_manager=creds, requests_timeout=20, retries=10,
        status_forcelist=(429, 500, 502, 503, 504), backoff_factor=0.4,
    )


def batched(iterable, n: int = 100):
    buf = []
    for x in iterable:
        buf.append(x)
        if len(buf) == n:
            yield buf
            buf = []
    if buf:
        yield buf


def fetch_all_liked(sp: spotipy.Spotify, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    offset = 0
    batch = 50
    pbar = tqdm(total=limit, desc="Descargando Me Gusta", unit="tracks")
    while True:
        need = batch if limit is None else max(0, min(batch, limit - len(results)))
        if need == 0:
            break
        try:
            resp = sp.current_user_saved_tracks(limit=need, offset=offset)
            items = resp.get("items", [])
            if not items:
                break
            results.extend(items)
            offset += len(items)
            pbar.update(len(items))
        except SpotifyException as e:
            logger.error(f"Error al obtener Me Gusta: {e}")
            break
    pbar.close()
    return results


def get_audio_features_resilient(
    sp: spotipy.Spotify,
    track_ids: List[str],
    max_retries: int = 3,
) -> Dict[str, Dict[str, Any]]:
    if not track_ids:
        return {}

    remaining = list(dict.fromkeys(track_ids))
    result: Dict[str, Dict[str, Any]] = {}
    omitted: set[str] = set()
    queue = [remaining[i:i + 50] for i in range(0, len(remaining), 50)]
    pbar = tqdm(total=len(queue), desc="Audio features", unit="batch")

    while queue:
        chunk = queue.pop(0)
        tries = 0
        while tries <= max_retries:
            try:
                af_list = sp.audio_features(chunk)
                for f in af_list or []:
                    if f and f.get("id"):
                        result[f["id"]] = f
                pbar.update(1)
                break
            except SpotifyException as e:
                status = getattr(e, "http_status", None)
                if status == 429:
                    wait = float(getattr(e, "headers", {}).get("Retry-After", 1))
                    logger.warning(f"Rate limit 429, esperando {wait}s...")
                    time.sleep(wait + 0.5)
                    tries += 1
                elif status in (403, 500, 502, 503, 504):
                    if len(chunk) > 1:
                        mid = len(chunk) // 2
                        queue.insert(0, chunk[mid:])
                        queue.insert(0, chunk[:mid])
                        pbar.update(1)
                    else:
                        if chunk[0] not in omitted:
                            logger.warning(f"Omitiendo track {chunk[0]} (HTTP {status})")
                            omitted.add(chunk[0])
                        pbar.update(1)
                    break
                else:
                    tries += 1
                    time.sleep(0.5 * tries)
            except Exception as e:
                tries += 1
                time.sleep(0.5 * tries)
        else:
            if chunk[0] not in omitted:
                omitted.add(chunk[0])
            pbar.update(1)

    pbar.close()
    if omitted:
        logger.warning(f"Se omitieron {len(omitted)} tracks sin audio_features.")
    return result


def get_artists_info(sp: spotipy.Spotify, artist_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    uniq = list(dict.fromkeys(a for a in artist_ids if a))
    for chunk in tqdm(list(batched(uniq, 50)), desc="Generos (artistas)", unit="batch"):
        try:
            arts = sp.artists(chunk).get("artists", [])
            for a in arts:
                out[a["id"]] = a
        except SpotifyException as e:
            logger.error(f"Error al obtener artistas: {e}")
    return out


def ensure_playlist(sp: spotipy.Spotify, user_id: str, name: str, public: bool) -> str:
    playlists = []
    results = sp.current_user_playlists(limit=50)
    while results:
        playlists.extend(results["items"])
        results = sp.next(results) if results.get("next") else None
    for p in playlists:
        if p.get("name") == name:
            return p["id"]
    pl = sp.user_playlist_create(user=user_id, name=name, public=public, description="Autogenerada")
    return pl["id"]


def get_playlist_track_uris(sp: spotipy.Spotify, playlist_id: str) -> set[str]:
    uris = set()
    results = sp.playlist_items(playlist_id, fields="items.track.uri,next", additional_types=("track",))
    while results:
        for it in results.get("items", []):
            tr = (it or {}).get("track") or {}
            uri = tr.get("uri")
            if uri:
                uris.add(uri)
        results = sp.next(results) if results.get("next") else None
    return uris


def add_tracks_in_chunks(sp: spotipy.Spotify, playlist_id: str, track_uris: List[str]):
    for chunk in batched(track_uris, 100):
        sp.playlist_add_items(playlist_id, chunk)

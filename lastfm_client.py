# lastfm_client.py - Cliente Last.fm para obtener tags, mood y similitud entre canciones
"""
Last.fm da gratis:
- Tags de una cancion (mood, genero detallado, instrumentos, etc.)
- Canciones similares a una cancion dada
- Tags de un artista
- Canciones similares a un artista

API key gratuita en: https://www.last.fm/api/account/create
"""
from __future__ import annotations
import os
import time
import logging
import requests
from typing import Dict, List, Any, Optional, Set
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

LASTFM_BASE = "https://ws.audioscrobbler.com/2.0/"

# Tags que indican mood/energia - usados para construir vector de similitud
MOOD_TAGS = {
    # energia
    "energetic": ("energy", 1.0), "aggressive": ("energy", 0.9),
    "intense": ("energy", 0.85), "upbeat": ("energy", 0.75),
    "calm": ("energy", 0.2), "relaxing": ("energy", 0.15),
    "chill": ("energy", 0.2), "mellow": ("energy", 0.25),
    "ambient": ("energy", 0.1),
    # positividad
    "happy": ("valence", 1.0), "feel good": ("valence", 0.9),
    "fun": ("valence", 0.85), "sad": ("valence", 0.1),
    "melancholic": ("valence", 0.15), "dark": ("valence", 0.2),
    "depressing": ("valence", 0.05), "romantic": ("valence", 0.7),
    # bailabilidad
    "dance": ("danceability", 1.0), "danceable": ("danceability", 1.0),
    "party": ("danceability", 0.9), "club": ("danceability", 0.85),
    # acustico
    "acoustic": ("acousticness", 1.0), "unplugged": ("acousticness", 0.9),
    "folk": ("acousticness", 0.7), "piano": ("acousticness", 0.6),
    # instrumental
    "instrumental": ("instrumentalness", 1.0), "classical": ("instrumentalness", 0.8),
    "jazz": ("instrumentalness", 0.5),
}


class LastFMClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "SpotifyAIPlaylist/1.0"})
        self._cache: Dict[str, Any] = {}

    def _get(self, method: str, params: Dict[str, str], retries: int = 3) -> Optional[Dict]:
        params = {**params, "method": method, "api_key": self.api_key, "format": "json"}
        for attempt in range(retries):
            try:
                r = self.session.get(LASTFM_BASE, params=params, timeout=10)
                if r.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                if r.status_code != 200:
                    return None
                data = r.json()
                if "error" in data:
                    logger.debug(f"Last.fm error {data['error']}: {data.get('message')}")
                    return None
                return data
            except Exception as e:
                logger.debug(f"Last.fm request error: {e}")
                time.sleep(1)
        return None

    def get_track_tags(self, artist: str, track: str) -> List[str]:
        """Obtiene top tags de una cancion."""
        key = f"tags:{artist}:{track}"
        if key in self._cache:
            return self._cache[key]

        data = self._get("track.getTopTags", {"artist": artist, "track": track})
        tags = []
        if data and "toptags" in data:
            for t in (data["toptags"].get("tag") or [])[:15]:
                name = t.get("name", "").lower().strip()
                if name and int(t.get("count", 0)) > 10:
                    tags.append(name)
        self._cache[key] = tags
        return tags

    def get_similar_tracks(self, artist: str, track: str, limit: int = 30) -> List[Dict[str, str]]:
        """Obtiene canciones similares segun Last.fm."""
        key = f"similar:{artist}:{track}"
        if key in self._cache:
            return self._cache[key]

        data = self._get("track.getSimilar", {"artist": artist, "track": track, "limit": str(limit)})
        results = []
        if data and "similartracks" in data:
            for t in (data["similartracks"].get("track") or []):
                results.append({
                    "name": t.get("name", ""),
                    "artist": t.get("artist", {}).get("name", "") if isinstance(t.get("artist"), dict) else t.get("artist", ""),
                    "match": float(t.get("match", 0)),
                })
        self._cache[key] = results
        return results

    def get_artist_tags(self, artist: str) -> List[str]:
        """Obtiene top tags de un artista."""
        key = f"artist_tags:{artist}"
        if key in self._cache:
            return self._cache[key]

        data = self._get("artist.getTopTags", {"artist": artist})
        tags = []
        if data and "toptags" in data:
            for t in (data["toptags"].get("tag") or [])[:10]:
                name = t.get("name", "").lower().strip()
                if name:
                    tags.append(name)
        self._cache[key] = tags
        return tags

    def tags_to_feature_vector(self, tags: List[str]) -> Dict[str, float]:
        """Convierte lista de tags en un vector de features aproximado."""
        vector: Dict[str, List[float]] = {}
        for tag in tags:
            tag_lower = tag.lower()
            for mood_tag, (feature, value) in MOOD_TAGS.items():
                if mood_tag in tag_lower:
                    vector.setdefault(feature, []).append(value)
        return {k: sum(v) / len(v) for k, v in vector.items()}


def get_lastfm_client() -> Optional[LastFMClient]:
    load_dotenv()
    api_key = os.getenv("LASTFM_API_KEY")
    if not api_key:
        logger.warning("LASTFM_API_KEY no configurada en .env - funcionando sin Last.fm")
        return None
    return LastFMClient(api_key)


def enrich_tracks_with_lastfm(
    track_meta: Dict[str, Dict[str, Any]],
    track_ids: List[str],
    lfm: LastFMClient,
    max_tracks: int = 500,
) -> Dict[str, Dict[str, Any]]:
    """
    Para cada track, obtiene tags de Last.fm y los agrega al meta.
    Retorna {track_id -> {tags: [...], lfm_vector: {...}, similar_names: set}}
    Limita a max_tracks para no exceder rate limit.
    """
    from tqdm import tqdm

    enriched: Dict[str, Dict[str, Any]] = {}
    sample = track_ids[:max_tracks]

    logger.info(f"Enriqueciendo {len(sample)} canciones con Last.fm...")
    for tid in tqdm(sample, desc="Last.fm tags", unit="track"):
        meta = track_meta.get(tid, {})
        name = meta.get("name", "")
        artists_str = meta.get("artists", "")
        artist = artists_str.split(";")[0].strip() if artists_str else ""

        if not name or not artist:
            continue

        tags = lfm.get_track_tags(artist, name)
        vector = lfm.tags_to_feature_vector(tags)

        enriched[tid] = {
            "tags": tags,
            "lfm_vector": vector,
        }
        time.sleep(0.25)  # respetar rate limit ~4 req/s

    logger.info(f"Last.fm: {len(enriched)} canciones enriquecidas.")
    return enriched


def get_lastfm_similar_ids(
    seed_ids: List[str],
    track_meta: Dict[str, Dict[str, Any]],
    all_track_names: Dict[str, str],  # nombre_lower -> track_id
    lfm: LastFMClient,
    top_n: int = 100,
) -> Dict[str, float]:
    """
    Busca canciones similares en Last.fm para cada semilla,
    y devuelve {track_id -> score} de las que estan en los Me Gusta.
    """
    matches = get_lastfm_similar_matches(seed_ids, track_meta, all_track_names, lfm, top_n=top_n)
    return {tid: data["score"] for tid, data in matches.items()}


def get_lastfm_similar_matches(
    seed_ids: List[str],
    track_meta: Dict[str, Dict[str, Any]],
    all_track_names: Dict[str, str],  # nombre_lower -> track_id
    lfm: LastFMClient,
    top_n: int = 100,
) -> Dict[str, Dict[str, Any]]:
    """
    Busca canciones similares en Last.fm para cada semilla.
    Retorna {track_id -> {score, seed_ids}} para poder balancear el ranking
    por semilla y evitar que un artista popular domine toda la lista.
    """
    similar_matches: Dict[str, Dict[str, Any]] = {}

    for tid in seed_ids:
        meta = track_meta.get(tid, {})
        name = meta.get("name", "")
        artists_str = meta.get("artists", "")
        artist = artists_str.split(";")[0].strip() if artists_str else ""
        if not name or not artist:
            continue

        similars = lfm.get_similar_tracks(artist, name, limit=50)
        for s in similars:
            s_name = s["name"].lower().strip()
            s_artist = s["artist"].lower().strip()
            match_score = s["match"]

            # Busca en los Me Gusta por nombre+artista
            for candidate_id, candidate_meta in track_meta.items():
                if candidate_id in seed_ids:
                    continue
                c_name = candidate_meta.get("name", "").lower().strip()
                c_artists = candidate_meta.get("artists", "").lower()
                if s_name == c_name and s_artist in c_artists:
                    current = similar_matches.setdefault(
                        candidate_id,
                        {"score": 0.0, "seed_ids": set()},
                    )
                    current["score"] = max(current["score"], match_score)
                    current["seed_ids"].add(tid)

        time.sleep(0.25)

    return similar_matches

# genius_client.py - Analisis de letras con Genius + Claude AI
"""
Usa la API de Genius para obtener letras de canciones semilla,
luego analiza el contenido emocional para afinar las sugerencias.
"""
from __future__ import annotations
import os
import re
import time
import logging
import requests
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

GENIUS_BASE = "https://api.genius.com"

# Temas emocionales y sus palabras clave en letras
LYRIC_THEMES = {
    "desamor":      ["ex", "olvidar", "perdiste", "extrano", "corazon roto", "llorar", "heartbreak",
                     "miss you", "moved on", "goodbye", "tears", "hurt", "pain", "leaving"],
    "nostalgia":    ["recuerdo", "antes", "aquellos tiempos", "de vuelta", "memories", "used to",
                     "back then", "those days", "remember when", "throwback"],
    "motivacion":   ["poder", "fuerza", "arriba", "ganar", "-xito", "hustle", "grind", "rise",
                     "success", "winning", "never give up", "stronger", "achieve"],
    "fiesta":       ["baile", "noche", "club", "party", "celebrar", "alcohol", "drinks", "dance",
                     "tonight", "turn up", "lit", "vibes", "moves"],
    "oscuro":       ["muerte", "sangre", "dolor", "destruir", "odio", "dark", "death", "blood",
                     "hate", "destroy", "evil", "demons", "suffer"],
    "amor_feliz":   ["amor", "feliz", "contigo", "forever", "love", "happy", "together", "smile",
                     "beautiful", "heart", "sunshine", "paradise"],
    "introspectivo":["pensar", "solo", "reflexionar", "mente", "alma", "thinking", "alone",
                     "mind", "soul", "wonder", "question", "reflect", "lost"],
    "calle":        ["barrio", "calle", "real", "trucho", "hood", "street", "real talk", "hustle",
                     "block", "trap", "money", "grind", "plug"],
}


class GeniusClient:
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "User-Agent": "SpotifyAIPlaylist/1.0",
        })
        self._cache: Dict[str, Any] = {}

    def search_song(self, title: str, artist: str) -> Optional[Dict]:
        """Busca una cancion en Genius y retorna el resultado mas relevante."""
        query = f"{title} {artist}"
        key = f"search:{query}"
        if key in self._cache:
            return self._cache[key]

        try:
            r = self.session.get(
                f"{GENIUS_BASE}/search",
                params={"q": query},
                timeout=10,
            )
            if r.status_code != 200:
                return None
            hits = r.json().get("response", {}).get("hits", [])
            for hit in hits:
                result = hit.get("result", {})
                # Verificar que el artista coincide aproximadamente
                primary = result.get("primary_artist", {}).get("name", "").lower()
                if artist.lower()[:6] in primary or primary[:6] in artist.lower():
                    self._cache[key] = result
                    return result
            # Si no hay coincidencia exacta, retorna el primero
            if hits:
                result = hits[0].get("result", {})
                self._cache[key] = result
                return result
        except Exception as e:
            logger.debug(f"Genius search error: {e}")
        return None

    def get_lyrics_url(self, title: str, artist: str) -> Optional[str]:
        """Obtiene la URL de la letra en Genius."""
        song = self.search_song(title, artist)
        if song:
            return song.get("url")
        return None

    def get_lyrics_text(self, title: str, artist: str) -> Optional[str]:
        """
        Obtiene el texto de la letra scrapeando Genius.
        Nota: Genius no da letras via API, requiere scraping ligero.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("beautifulsoup4 no instalado. Instala con: pip install beautifulsoup4")
            return None

        url = self.get_lyrics_url(title, artist)
        if not url:
            return None

        key = f"lyrics:{url}"
        if key in self._cache:
            return self._cache[key]

        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, "html.parser")
            # Genius usa data-lyrics-container
            containers = soup.find_all("div", attrs={"data-lyrics-container": "true"})
            if not containers:
                return None
            lines = []
            for container in containers:
                for br in container.find_all("br"):
                    br.replace_with("\n")
                text = container.get_text(separator="\n")
                lines.append(text)
            lyrics = "\n".join(lines)
            # Limpiar anotaciones y texto extra
            lyrics = re.sub(r'\[.*?\]', '', lyrics)
            lyrics = re.sub(r'\n{3,}', '\n\n', lyrics).strip()
            self._cache[key] = lyrics
            return lyrics
        except Exception as e:
            logger.debug(f"Genius lyrics error: {e}")
        return None


def detect_themes(lyrics: str) -> Dict[str, float]:
    """
    Detecta temas emocionales en una letra.
    Retorna {tema: score} donde score es la densidad de palabras clave.
    """
    if not lyrics:
        return {}

    lyrics_lower = lyrics.lower()
    word_count = max(len(lyrics_lower.split()), 1)
    scores = {}

    for theme, keywords in LYRIC_THEMES.items():
        matches = sum(1 for kw in keywords if kw in lyrics_lower)
        if matches > 0:
            scores[theme] = round(matches / len(keywords), 3)

    return scores


def analyze_seeds_with_genius(
    seed_ids: List[str],
    track_meta: Dict[str, Dict[str, Any]],
    genius: GeniusClient,
) -> Dict[str, Any]:
    """
    Analiza las letras de las canciones semilla.
    Retorna el perfil tematico promedio.
    """
    all_themes: Dict[str, List[float]] = {}
    lyrics_found = 0

    for tid in seed_ids:
        meta = track_meta.get(tid, {})
        name = meta.get("name", "")
        artists_str = meta.get("artists", "")
        artist = artists_str.split(";")[0].strip() if artists_str else ""

        if not name or not artist:
            continue

        logger.info(f"  Buscando letra: {name} - {artist}")
        lyrics = genius.get_lyrics_text(name, artist)

        if not lyrics:
            logger.debug(f"  Sin letra para: {name}")
            time.sleep(0.5)
            continue

        lyrics_found += 1
        themes = detect_themes(lyrics)
        for theme, score in themes.items():
            all_themes.setdefault(theme, []).append(score)

        time.sleep(0.8)  # respetar rate limit

    if not all_themes:
        return {"themes": {}, "lyrics_found": 0, "dominant_themes": []}

    # Promediar temas
    avg_themes = {t: sum(v) / len(v) for t, v in all_themes.items()}
    # Top temas dominantes
    dominant = sorted(avg_themes.items(), key=lambda x: -x[1])[:4]

    return {
        "themes": avg_themes,
        "lyrics_found": lyrics_found,
        "dominant_themes": [t for t, _ in dominant],
    }


def score_candidate_by_themes(
    tid: str,
    track_meta: Dict[str, Dict[str, Any]],
    seed_themes: Dict[str, float],
    genius: GeniusClient,
) -> float:
    """
    Puntua un candidato basandose en similitud tematica de letras.
    Retorna score entre 0 y 1, o -1 si no se pudo obtener letra.
    """
    meta = track_meta.get(tid, {})
    name = meta.get("name", "")
    artists_str = meta.get("artists", "")
    artist = artists_str.split(";")[0].strip() if artists_str else ""

    if not name or not artist:
        return -1

    lyrics = genius.get_lyrics_text(name, artist)
    if not lyrics:
        return -1

    themes = detect_themes(lyrics)
    if not themes or not seed_themes:
        return -1

    # Similitud coseno entre vectores de temas
    all_keys = set(seed_themes.keys()) | set(themes.keys())
    dot = sum(seed_themes.get(k, 0) * themes.get(k, 0) for k in all_keys)
    mag_a = sum(v ** 2 for v in seed_themes.values()) ** 0.5 or 1e-9
    mag_b = sum(v ** 2 for v in themes.values()) ** 0.5 or 1e-9

    return round(dot / (mag_a * mag_b), 4)


def get_genius_client() -> Optional[GeniusClient]:
    load_dotenv()
    token = os.getenv("GENIUS_TOKEN")
    if not token:
        logger.warning("GENIUS_TOKEN no configurado en .env")
        return None
    return GeniusClient(token)

# ai_playlist.py - Motor IA para sugerir canciones basado en gustos del usuario
"""
Flujo:
1. El usuario elige canciones semilla de sus Me Gusta.
2. Se buscan canciones similares en Last.fm (gratis, sin restricciones).
3. Se complementa con similitud por generos de Spotify y artistas compartidos.
4. Opcionalmente Claude AI describe el perfil musical detectado.
5. Se crean las playlists directamente en Spotify.
"""
from __future__ import annotations
import os
import math
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

FEATURE_KEYS = ["energy", "valence", "danceability", "acousticness", "instrumentalness"]

GENRE_FAMILY_KEYWORDS = {
    "rock": ("rock", "grunge", "alternative", "punk", "emo", "shoegaze", "new wave"),
    "metal": ("metal", "hardcore", "nu metal", "heavy"),
    "latin_urban": ("reggaeton", "urbano", "latin trap", "trap latino", "dembow", "perreo"),
    "hiphop": ("hip hop", "rap", "trap", "drill", "r&b", "rnb"),
    "pop": ("pop", "synthpop", "dance pop", "indie pop"),
    "electronic": ("house", "techno", "edm", "electronic", "electronica", "dance", "trance", "dubstep"),
    "folk": ("folk", "singer-songwriter", "country", "americana"),
    "jazz": ("jazz", "soul", "blues", "funk"),
    "classical": ("classical", "orchestra", "piano", "instrumental"),
}

GENERIC_LASTFM_TAGS = {
    "seen live", "favorite", "favorites", "favourite", "favourites", "spotify",
    "male vocalists", "female vocalists", "beautiful", "awesome", "catchy",
}


# -----------------------------------------
# Utilidades de similitud
# -----------------------------------------

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x ** 2 for x in a)) or 1e-9
    mag_b = math.sqrt(sum(x ** 2 for x in b)) or 1e-9
    return dot / (mag_a * mag_b)


def _genre_overlap(seed_genres: set, candidate_genres: set) -> float:
    if not seed_genres and not candidate_genres:
        return 0.0
    intersection = len(seed_genres & candidate_genres)
    union = len(seed_genres | candidate_genres)
    return intersection / union if union else 0.0


def _families_for_terms(terms: List[str] | set[str]) -> set[str]:
    families: set[str] = set()
    for term in terms:
        tl = (term or "").lower()
        for family, keywords in GENRE_FAMILY_KEYWORDS.items():
            if any(keyword in tl for keyword in keywords):
                families.add(family)
    return families


def _tag_overlap(seed_tags: set[str], candidate_tags: set[str]) -> float:
    seed_clean = {t for t in seed_tags if t and t not in GENERIC_LASTFM_TAGS}
    cand_clean = {t for t in candidate_tags if t and t not in GENERIC_LASTFM_TAGS}
    if not seed_clean or not cand_clean:
        return 0.0
    return len(seed_clean & cand_clean) / max(len(seed_clean), 1)


def _tags_to_vector(tags: List[str]) -> List[float]:
    """Convierte tags de Last.fm en vector numerico [energy, valence, dance, acoustic, instrumental]."""
    from lastfm_client import MOOD_TAGS
    buckets: Dict[str, List[float]] = {}
    for tag in tags:
        tl = tag.lower()
        for mood_tag, (feat, val) in MOOD_TAGS.items():
            if mood_tag in tl:
                buckets.setdefault(feat, []).append(val)
    result = []
    for key in FEATURE_KEYS:
        vals = buckets.get(key, [])
        result.append(sum(vals) / len(vals) if vals else 0.5)
    return result


# -----------------------------------------
# Perfil del conjunto semilla
# -----------------------------------------

def build_seed_profile(
    seed_ids: List[str],
    track_meta: Dict[str, Dict[str, Any]],
    artists_by_id: Dict[str, Dict[str, Any]],
    lfm_data: Dict[str, Dict[str, Any]],  # tid -> {tags, lfm_vector}
) -> Dict[str, Any]:
    """Construye perfil musical promedio de las semillas."""
    vectors = []
    all_tags: List[str] = []
    all_genres: List[str] = []
    all_artists: List[str] = []
    genre_count: Dict[str, int] = {}

    for tid in seed_ids:
        meta = track_meta.get(tid, {})

        # Tags de Last.fm a vector
        lfm = lfm_data.get(tid, {})
        tags = lfm.get("tags", [])
        all_tags.extend(tags)
        if tags:
            v = _tags_to_vector(tags)
            vectors.append(v)

        # Generos de Spotify
        for aid in meta.get("artist_ids", []):
            art = artists_by_id.get(aid, {})
            for g in art.get("genres", []):
                all_genres.append(g)
                genre_count[g] = genre_count.get(g, 0) + 1
            name = art.get("name", "")
            if name:
                all_artists.append(name.lower())

    avg_vector = (
        [sum(v[i] for v in vectors) / len(vectors) for i in range(len(FEATURE_KEYS))]
        if vectors else [0.5] * len(FEATURE_KEYS)
    )

    # Tags mas frecuentes
    tag_count: Dict[str, int] = {}
    for t in all_tags:
        tag_count[t] = tag_count.get(t, 0) + 1
    top_tags = [t for t, _ in sorted(tag_count.items(), key=lambda x: -x[1])[:15]]

    top_genres = set(g for g, _ in sorted(genre_count.items(), key=lambda x: -x[1])[:20])
    family_terms = all_genres + top_tags
    family_count: Dict[str, int] = {}
    for family in _families_for_terms(family_terms):
        family_count[family] = sum(1 for term in family_terms if family in _families_for_terms({term}))

    return {
        "vector": avg_vector,
        "tags": top_tags,
        "genres": top_genres,
        "families": set(family_count.keys()),
        "family_count": family_count,
        "artists": list(set(all_artists)),
        "genre_count": genre_count,
        "has_lfm": len(vectors) > 0,
        "seed_count": len(vectors),
    }


# -----------------------------------------
# Scoring de candidatos
# -----------------------------------------

def score_candidates(
    seed_profile: Dict[str, Any],
    candidate_ids: List[str],
    track_meta: Dict[str, Dict[str, Any]],
    artists_by_id: Dict[str, Dict[str, Any]],
    lfm_data: Dict[str, Dict[str, Any]],
    lastfm_similar: Dict[str, float],  # tid -> score directo de Last.fm
    exclude_ids: set,
    top_n: int = 50,
) -> List[Tuple[str, float, Dict[str, Any]]]:

    seed_vec = seed_profile["vector"]
    seed_genres = seed_profile["genres"]
    seed_genre_count = seed_profile.get("genre_count", {})
    seed_tags = set(seed_profile.get("tags", []))
    seed_families = set(seed_profile.get("families", set()))
    seed_artists = set(seed_profile["artists"])
    total_genre_weight = sum(seed_genre_count.values()) or 1
    has_lfm = seed_profile["has_lfm"]

    results = []

    for tid in candidate_ids:
        if tid in exclude_ids:
            continue

        meta = track_meta.get(tid, {})
        cand_genres: set = set()
        cand_artists: set = set()
        for aid in meta.get("artist_ids", []):
            art = artists_by_id.get(aid, {})
            cand_genres.update(art.get("genres", []))
            name = art.get("name", "")
            if name:
                cand_artists.add(name.lower())

        # 1. Score Last.fm directo (cancion marcada como similar por Last.fm)
        lfm_direct = lastfm_similar.get(tid, 0.0)
        cand_tags = set((lfm_data.get(tid, {}) or {}).get("tags", []))
        candidate_families = _families_for_terms(cand_genres | cand_tags)
        family_overlap = bool(seed_families & candidate_families)
        tags_score = _tag_overlap(seed_tags, cand_tags)

        # 2. Score por similitud de vector de tags Last.fm
        lfm_vec_score = 0.0
        if has_lfm:
            cand_lfm = lfm_data.get(tid, {})
            candidate_tags = cand_lfm.get("tags", [])
            if candidate_tags and (tags_score > 0 or family_overlap):
                cand_vec = _tags_to_vector(candidate_tags)
                lfm_vec_score = _cosine_similarity(seed_vec, cand_vec)

        # 3. Score por generos de Spotify (ponderado por frecuencia)
        weighted_genre = sum(seed_genre_count.get(g, 0) for g in cand_genres if g in seed_genres)
        genre_score = min(1.0, weighted_genre / total_genre_weight)

        # 4. Bonus por artista compartido
        artist_bonus = 0.20 if cand_artists & seed_artists else 0.0

        has_hard_match = bool(lfm_direct > 0 or genre_score > 0 or tags_score > 0 or artist_bonus > 0)
        if seed_families and candidate_families and not family_overlap and not lfm_direct and not artist_bonus:
            continue
        if not has_hard_match:
            continue

        # Combinar scores segun disponibilidad
        if lfm_direct > 0:
            # Last.fm dijo explicitamente que es similar: maxima prioridad
            score = lfm_direct * 0.45 + genre_score * 0.30 + tags_score * 0.15 + lfm_vec_score * 0.05 + artist_bonus * 0.05
        elif lfm_vec_score > 0:
            score = lfm_vec_score * 0.20 + genre_score * 0.50 + tags_score * 0.20 + artist_bonus * 0.10
        else:
            # Solo generos y artistas
            score = genre_score * 0.75 + tags_score * 0.15 + artist_bonus * 0.10

        if score > 0:
            results.append((tid, score))

    results.sort(key=lambda x: -x[1])

    out = []
    for tid, score in results[:top_n]:
        out.append((tid, round(score, 4), track_meta.get(tid, {})))
    return out


def balance_suggestions_by_seed(
    suggestions: List[Tuple[str, float, Dict[str, Any]]],
    lastfm_matches: Dict[str, Dict[str, Any]],
    seed_ids: List[str],
    top_n: int,
) -> List[Tuple[str, float, Dict[str, Any]]]:
    """Intercala matches directos por semilla para que ninguna semilla domine toda la lista."""
    if not suggestions or not lastfm_matches or not seed_ids:
        return suggestions[:top_n]

    by_id = {tid: (tid, score, meta) for tid, score, meta in suggestions}
    buckets: Dict[str, List[Tuple[str, float, Dict[str, Any]]]] = {sid: [] for sid in seed_ids}
    direct_ids: set[str] = set()

    for tid, _score, _meta in suggestions:
        match = lastfm_matches.get(tid)
        if not match:
            continue
        seed_match_ids = [sid for sid in seed_ids if sid in match.get("seed_ids", set())]
        if not seed_match_ids:
            continue
        best_seed = min(seed_match_ids, key=lambda sid: len(buckets[sid]))
        buckets[best_seed].append(by_id[tid])
        direct_ids.add(tid)

    balanced: List[Tuple[str, float, Dict[str, Any]]] = []
    used: set[str] = set()
    while len(balanced) < top_n:
        added = False
        for seed_id in seed_ids:
            bucket = buckets.get(seed_id, [])
            while bucket and bucket[0][0] in used:
                bucket.pop(0)
            if not bucket:
                continue
            item = bucket.pop(0)
            balanced.append(item)
            used.add(item[0])
            added = True
            if len(balanced) >= top_n:
                break
        if not added:
            break

    for item in suggestions:
        if len(balanced) >= top_n:
            break
        if item[0] in used:
            continue
        balanced.append(item)
        used.add(item[0])

    return balanced[:top_n]


# -----------------------------------------
# Descripcion IA con Claude
# -----------------------------------------

def describe_profile_with_ai(
    seed_profile: Dict[str, Any],
    seed_tracks: List[Dict[str, Any]],
    suggested_tracks: List[Tuple[str, float, Dict[str, Any]]],
) -> str:
    try:
        import anthropic
    except ImportError:
        return "[anthropic no instalado]"

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "[ANTHROPIC_API_KEY no configurada]"

    top_tags = seed_profile.get("tags", [])[:10]
    genres_sample = list(seed_profile.get("genres", set()))[:8]
    seed_names = [f"- {t.get('name','?')} - {t.get('artists','?')}" for t in seed_tracks[:10]]
    suggested_names = [
        f"- {m.get('name','?')} - {m.get('artists','?')} (similitud: {s:.0%})"
        for _, s, m in suggested_tracks[:10]
    ]

    prompt = f"""Eres un experto en musica y analisis de gustos musicales.

El usuario creo una playlist con estas canciones semilla:
{chr(10).join(seed_names)}

Tags musicales detectados (via Last.fm): {', '.join(top_tags) if top_tags else 'sin datos'}
Generos detectados (via Spotify): {', '.join(genres_sample) if genres_sample else 'sin datos'}

Canciones sugeridas automaticamente de sus Me Gusta:
{chr(10).join(suggested_names)}

Responde en espanol con:
1. **Perfil musical** (2-3 oraciones describiendo el vibe/mood)
2. **Por que estas sugerencias encajan** (1-2 oraciones)
3. **Nombre creativo sugerido para la playlist**

Se conciso y natural, como un DJ amigo."""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# -----------------------------------------
# Funcion principal
# -----------------------------------------

def suggest_from_seeds(
    seed_track_ids: List[str],
    all_liked_ids: List[str],
    features_by_id: Dict[str, Dict[str, Any]],  # mantenido por compatibilidad
    artists_by_id: Dict[str, Dict[str, Any]],
    track_meta: Dict[str, Dict[str, Any]],
    top_n: int = 30,
    use_ai_description: bool = True,
) -> Dict[str, Any]:
    if not seed_track_ids:
        return {"profile": {}, "suggestions": [], "ai_description": "Sin canciones semilla."}

    # Intentar usar Last.fm
    lfm_client = None
    lfm_data: Dict[str, Dict[str, Any]] = {}
    lastfm_similar: Dict[str, float] = {}
    lastfm_matches: Dict[str, Dict[str, Any]] = {}

    try:
        from lastfm_client import get_lastfm_client, enrich_tracks_with_lastfm, get_lastfm_similar_matches
        lfm_client = get_lastfm_client()
    except ImportError:
        pass

    if lfm_client:
        logger.info("Last.fm disponible - enriqueciendo canciones con tags y similitud...")

        # Enriquecer semillas + sample de candidatos con tags
        ids_to_enrich = list(seed_track_ids) + [
            tid for tid in all_liked_ids if tid not in seed_track_ids
        ][:400]
        lfm_data = enrich_tracks_with_lastfm(track_meta, ids_to_enrich, lfm_client, max_tracks=400)

        # Buscar similares directas en Last.fm para cada semilla
        logger.info("Buscando canciones similares en Last.fm...")
        lastfm_matches = get_lastfm_similar_matches(
            seed_track_ids, track_meta, {}, lfm_client, top_n=100
        )
        lastfm_similar = {tid: data["score"] for tid, data in lastfm_matches.items()}
        logger.info(f"Last.fm encontro {len(lastfm_similar)} coincidencias en tus Me Gusta.")
    else:
        logger.warning("Sin Last.fm: la similitud queda limitada a generos y artistas de Spotify.")

    # -- Genius: analizar letras de semillas --
    genius_profile = {}
    try:
        from genius_client import get_genius_client, analyze_seeds_with_genius
        genius = get_genius_client()
        if genius:
            logger.info("Genius disponible - analizando letras de canciones semilla...")
            genius_profile = analyze_seeds_with_genius(seed_track_ids, track_meta, genius)
            found = genius_profile.get("lyrics_found", 0)
            themes = genius_profile.get("dominant_themes", [])
            if themes:
                logger.info(f"Temas detectados en letras: {', '.join(themes)} ({found} canciones)")
    except ImportError:
        pass

    # Construir perfil
    profile = build_seed_profile(seed_track_ids, track_meta, artists_by_id, lfm_data)
    profile["genius_themes"] = genius_profile.get("themes", {})
    profile["dominant_themes"] = genius_profile.get("dominant_themes", [])

    genres_str = ", ".join(list(profile["genres"])[:8])
    tags_str = ", ".join(profile["tags"][:6])
    themes_str = ", ".join(profile.get("dominant_themes", []))
    logger.info(f"Generos: {genres_str or 'ninguno'}")
    if tags_str:
        logger.info(f"Tags Last.fm: {tags_str}")
    if themes_str:
        logger.info(f"Temas (letras): {themes_str}")

    # Puntuar candidatos
    candidates = [tid for tid in all_liked_ids if tid not in seed_track_ids]
    suggestions = score_candidates(
        profile, candidates, track_meta, artists_by_id,
        lfm_data, lastfm_similar,
        exclude_ids=set(seed_track_ids),
        top_n=top_n,
    )
    suggestions = balance_suggestions_by_seed(
        suggestions, lastfm_matches, seed_track_ids, top_n=top_n
    )

    # -- Reordenar con similitud de letras (top 30) --
    seed_themes = profile.get("genius_themes", {})
    if seed_themes:
        try:
            from genius_client import get_genius_client, score_candidate_by_themes
            import time as _time
            genius2 = get_genius_client()
            if genius2:
                logger.info("Ajustando sugerencias por similitud de letras (top 30)...")
                rescored = []
                for tid, base_score, meta in suggestions[:30]:
                    lyric_score = score_candidate_by_themes(tid, track_meta, seed_themes, genius2)
                    if lyric_score >= 0:
                        combined = base_score * 0.6 + lyric_score * 0.4
                    else:
                        combined = base_score * 0.9
                    rescored.append((tid, round(combined, 4), meta))
                    _time.sleep(0.5)
                rescored.sort(key=lambda x: -x[1])
                suggestions = rescored + suggestions[30:]
                logger.info("Reordenamiento por letras completado.")
        except ImportError:
            pass

    logger.info(f"Sugerencias generadas: {len(suggestions)}")

    # Descripcion con Claude AI
    ai_desc = ""
    if use_ai_description:
        seed_metas = [track_meta.get(tid, {}) for tid in seed_track_ids]
        ai_desc = describe_profile_with_ai(profile, seed_metas, suggestions)

    return {
        "profile": profile,
        "suggestions": suggestions,
        "ai_description": ai_desc,
    }

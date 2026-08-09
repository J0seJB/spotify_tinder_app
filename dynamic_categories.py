from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

LFM_FEATURE_COLUMNS = [
    "lfm_energy",
    "lfm_valence",
    "lfm_danceability",
    "lfm_acousticness",
    "lfm_instrumentalness",
]

LYRIC_THEME_COLUMNS = [
    "lyric_desamor",
    "lyric_nostalgia",
    "lyric_motivacion",
    "lyric_fiesta",
    "lyric_oscuro",
    "lyric_amor_feliz",
    "lyric_introspectivo",
    "lyric_calle",
]


def _clean_token(value: str) -> str:
    value = (value or "").lower().strip()
    value = re.sub(r"[^a-z0-9áéíóúñü&+ -]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _artist_genres(meta: Dict[str, Any], artists_by_id: Dict[str, Dict[str, Any]]) -> List[str]:
    genres: List[str] = []
    for artist_id in meta.get("artist_ids", []) or []:
        genres.extend(artists_by_id.get(artist_id, {}).get("genres", []) or [])
    return [_clean_token(g) for g in genres if _clean_token(g)]


def _main_artists(meta: Dict[str, Any]) -> List[str]:
    artists = meta.get("artists", "") or ""
    return [_clean_token(a) for a in artists.split(";") if _clean_token(a)]


def _tags_to_lfm_features(tags: List[str]) -> Dict[str, float]:
    from lastfm_client import MOOD_TAGS

    buckets: Dict[str, List[float]] = defaultdict(list)
    for tag in tags:
        tag_lower = _clean_token(tag)
        for mood_tag, (feature, value) in MOOD_TAGS.items():
            if mood_tag in tag_lower:
                buckets[feature].append(float(value))

    return {
        "lfm_energy": _average_or_default(buckets.get("energy"), 0.5),
        "lfm_valence": _average_or_default(buckets.get("valence"), 0.5),
        "lfm_danceability": _average_or_default(buckets.get("danceability"), 0.5),
        "lfm_acousticness": _average_or_default(buckets.get("acousticness"), 0.5),
        "lfm_instrumentalness": _average_or_default(buckets.get("instrumentalness"), 0.5),
    }


def _average_or_default(values: Optional[List[float]], default: float) -> float:
    if not values:
        return default
    return round(sum(values) / len(values), 4)


def _dedupe_keep_order(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        cleaned = _clean_token(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def collect_lastfm_data(
    track_meta: Dict[str, Dict[str, Any]],
    track_ids: List[str],
    max_tracks: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    from lastfm_client import enrich_tracks_with_lastfm, get_lastfm_client

    lfm = get_lastfm_client()
    if not lfm:
        raise RuntimeError("LASTFM_API_KEY no configurada. El descubrimiento dinamico requiere Last.fm.")

    limit = max_tracks if max_tracks is not None else len(track_ids)
    return enrich_tracks_with_lastfm(track_meta, track_ids, lfm, max_tracks=limit)


def build_lfm_rows(
    liked_items: List[Dict[str, Any]],
    track_meta: Dict[str, Dict[str, Any]],
    artists_by_id: Dict[str, Dict[str, Any]],
    lfm_data: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for item in liked_items:
        track = (item or {}).get("track") or {}
        track_id = track.get("id")
        if not track_id:
            continue

        meta = track_meta.get(track_id, {})
        if not meta.get("uri"):
            continue

        tags = _dedupe_keep_order(lfm_data.get(track_id, {}).get("tags", []) or [])
        genres = _dedupe_keep_order(meta.get("genres", []) or _artist_genres(meta, artists_by_id))
        artists = _main_artists(meta)
        signal_terms = _dedupe_keep_order(tags + genres + artists[:2])
        lfm_features = _tags_to_lfm_features(tags)

        rows.append({
            "track_id": track_id,
            "uri": meta.get("uri", ""),
            "name": meta.get("name", ""),
            "artists": meta.get("artists", ""),
            "artist_ids": "; ".join(meta.get("artist_ids", []) or []),
            "genres": "; ".join(genres),
            "lfm_tags": "; ".join(tags),
            "signal_terms": " ".join(signal_terms),
            **lfm_features,
        })

    return rows


def enrich_rows_with_genius(
    rows: List[Dict[str, Any]],
    max_tracks: Optional[int] = None,
) -> List[Dict[str, Any]]:
    from genius_client import LYRIC_THEMES, detect_themes, get_genius_client

    genius = get_genius_client()
    if not genius:
        raise RuntimeError("GENIUS_TOKEN no configurado. No se pueden analizar letras.")

    limit = max_tracks if max_tracks is not None else len(rows)
    limit = max(0, min(limit, len(rows)))
    theme_names = list(LYRIC_THEMES.keys())

    for row in rows:
        for theme in theme_names:
            row[f"lyric_{theme}"] = 0.0
        row["lyric_themes"] = ""

    logger.info("Analizando letras con Genius para %s canciones...", limit)
    for row in rows[:limit]:
        title = row.get("name", "")
        artist = str(row.get("artists", "")).split(";")[0].strip()
        if not title or not artist:
            continue

        lyrics = genius.get_lyrics_text(title, artist)
        if not lyrics:
            time.sleep(0.5)
            continue

        themes = detect_themes(lyrics)
        if not themes:
            time.sleep(0.8)
            continue

        dominant = [theme for theme, score in sorted(themes.items(), key=lambda item: -item[1]) if score > 0]
        row["lyric_themes"] = "; ".join(dominant)
        row["signal_terms"] = " ".join(_dedupe_keep_order(
            str(row.get("signal_terms", "")).split() + dominant + [f"letra {theme}" for theme in dominant]
        ))
        for theme, score in themes.items():
            row[f"lyric_{theme}"] = round(float(score), 4)

        time.sleep(0.8)

    return rows


def _name_from_terms(terms: List[str], artists: List[str]) -> str:
    preferred = [
        t for t in terms
        if len(t) > 2 and t not in {"seen live", "favorites", "spotify", "streamable"}
    ][:4]
    if not preferred and artists:
        preferred = artists[:3]
    if not preferred:
        return "Categoria descubierta"
    return " / ".join(t.title() for t in preferred[:3])


def _name_categories_with_ai(categories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return categories

    try:
        import anthropic
    except ImportError:
        return categories

    compact = [
        {
            "id": cat["id"],
            "current_name": cat["name"],
            "top_terms": cat["top_terms"][:10],
            "top_artists": cat["top_artists"][:6],
            "track_count": cat["track_count"],
        }
        for cat in categories
    ]
    prompt = (
        "Nombra estas categorias musicales en espanol de forma corta y natural. "
        "Devuelve solo JSON: una lista de objetos con id y name. "
        f"Categorias: {json.dumps(compact, ensure_ascii=False)}"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        start = raw.find("[")
        end = raw.rfind("]")
        if start < 0 or end < 0:
            return categories
        generated = json.loads(raw[start:end + 1])
        names = {int(item["id"]): str(item["name"]) for item in generated if "id" in item and "name" in item}
        for cat in categories:
            if cat["id"] in names:
                cat["name"] = names[cat["id"]][:80]
    except Exception as exc:
        logger.warning("No se pudieron nombrar categorias con IA: %s", exc)

    return categories


def discover_categories(
    rows: List[Dict[str, Any]],
    target_categories: int = 12,
    use_ai_names: bool = True,
) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    if not rows:
        return [], pd.DataFrame()

    df = pd.DataFrame(rows)
    usable = df["signal_terms"].fillna("").str.strip()
    non_empty = usable[usable != ""]
    if non_empty.empty:
        df["generated_category"] = "Sin senales suficientes"
        df["generated_category_id"] = 0
        return [{
            "id": 0,
            "name": "Sin senales suficientes",
            "track_count": len(df),
            "top_terms": [],
            "top_artists": [],
            "track_ids": df["track_id"].tolist(),
        }], df

    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    n_clusters = max(1, min(int(target_categories), len(non_empty)))
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=2500)
    matrix = vectorizer.fit_transform(df["signal_terms"].fillna(""))

    if n_clusters == 1:
        labels = [0] * len(df)
    else:
        km = KMeans(n_clusters=n_clusters, n_init=20, random_state=42)
        labels = km.fit_predict(matrix)

    df["generated_category_id"] = labels

    categories: List[Dict[str, Any]] = []
    for label in sorted(set(labels)):
        sub = df[df["generated_category_id"] == label]
        term_counter: Counter[str] = Counter()
        artist_counter: Counter[str] = Counter()
        for _, row in sub.iterrows():
            term_counter.update(_dedupe_keep_order(str(row.get("lfm_tags", "")).split(";")))
            term_counter.update(_dedupe_keep_order(str(row.get("genres", "")).split(";")))
            artist_counter.update(_dedupe_keep_order(str(row.get("artists", "")).split(";")))

        top_terms = [term for term, _ in term_counter.most_common(12)]
        top_artists = [artist for artist, _ in artist_counter.most_common(8)]
        categories.append({
            "id": int(label),
            "name": _name_from_terms(top_terms, top_artists),
            "track_count": int(len(sub)),
            "top_terms": top_terms,
            "top_artists": top_artists,
            "track_ids": sub["track_id"].tolist(),
        })

    categories.sort(key=lambda item: (-item["track_count"], item["name"]))
    if use_ai_names:
        categories = _name_categories_with_ai(categories)

    id_to_name = {cat["id"]: cat["name"] for cat in categories}
    df["generated_category"] = df["generated_category_id"].map(id_to_name)
    df["best_category"] = df["generated_category"]
    df["best_score"] = 1.0

    return categories, df


def export_discovery(categories: List[Dict[str, Any]], df: pd.DataFrame, export_dir: str = "export") -> None:
    os.makedirs(export_dir, exist_ok=True)
    df.to_csv(os.path.join(export_dir, "tracks_with_lfm.csv"), index=False, encoding="utf-8")
    df.to_csv(os.path.join(export_dir, "tracks_with_features.csv"), index=False, encoding="utf-8")
    with open(os.path.join(export_dir, "generated_categories.json"), "w", encoding="utf-8") as f:
        json.dump({"categories": categories}, f, ensure_ascii=False, indent=2)

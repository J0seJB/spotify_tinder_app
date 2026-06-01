# views.py - Playlists dinamicas por reglas (version corregida)
from __future__ import annotations
import json
import argparse
import logging
from typing import Dict, Any, Optional

import pandas as pd
from dotenv import load_dotenv

from spotify_client import get_user_client, ensure_playlist, add_tracks_in_chunks

logger = logging.getLogger(__name__)


def filter_df(df: pd.DataFrame, flt: Dict[str, Any]) -> pd.DataFrame:
    d = df.copy()

    def rng(cols: str | list[str], lo: Optional[float], hi: Optional[float]) -> pd.DataFrame:
        """Aplica rango usando la primera columna disponible."""
        result = d
        if isinstance(cols, str):
            candidates = [cols]
        else:
            candidates = cols
        col = next((c for c in candidates if c in result.columns), "")
        if col in result.columns:
            if lo is not None:
                result = result[result[col] >= lo]
            if hi is not None:
                result = result[result[col] <= hi]
        return result

    # Senales musicales. Prefiere columnas Last.fm y conserva fallback legacy.
    feature_map = {
        ("tempo_min", "tempo_max"): ["feat_tempo"],
        ("energy_min", "energy_max"): ["lfm_energy", "feat_energy"],
        ("valence_min", "valence_max"): ["lfm_valence", "feat_valence"],
        ("dance_min", "dance_max"): ["lfm_danceability", "feat_danceability"],
        ("instrumentalness_min", "instrumentalness_max"): ["lfm_instrumentalness", "feat_instrumentalness"],
        ("speechiness_min", "speechiness_max"): ["lfm_speechiness", "feat_speechiness"],
        ("acousticness_min", "acousticness_max"): ["lfm_acousticness", "feat_acousticness"],
    }
    for (k_min, k_max), col in feature_map.items():
        if k_min in flt or k_max in flt:
            d = rng(col, flt.get(k_min), flt.get(k_max))

    # Emociones
    for emo in ("joy", "sadness", "anger", "fear", "surprise", "disgust"):
        k_min, k_max = f"emo_{emo}_min", f"emo_{emo}_max"
        if k_min in flt or k_max in flt:
            d = rng(f"emo_{emo}", flt.get(k_min), flt.get(k_max))

    # Generos obligatorios
    if "must_genres" in flt:
        gids = [g.lower() for g in flt["must_genres"]]
        d = d[d["genres"].fillna("").str.lower().apply(lambda s: any(g in s for g in gids))]

    # Filtro de idioma por heuristica de generos
    lang = flt.get("lang", "").upper()
    latin_pattern = "latin|espanol|espanol|mexican|argentine|spanish|colombian|reggaeton|cumbia|salsa|bachata"
    if lang == "ES":
        d = d[d["genres"].fillna("").str.contains(latin_pattern, case=False, regex=True)]
    elif lang == "EN":
        d = d[~d["genres"].fillna("").str.contains(latin_pattern, case=False, regex=True)]

    # Categorias
    if "categories" in flt:
        cats = [c.lower() for c in flt["categories"]]
        d = d[d["best_category"].fillna("").str.lower().apply(lambda s: any(c in s for c in cats))]

    return d


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="Genera playlists dinamicas desde views.json")
    ap.add_argument("--views", default="config/views.json")
    ap.add_argument("--csv", default="export/tracks_with_features.csv")
    ap.add_argument("--public", action="store_true")
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--prefix", default=None)
    args = ap.parse_args()

    try:
        df = pd.read_csv(args.csv)
    except FileNotFoundError:
        print(f"CSV no encontrado: {args.csv}")
        print("   Ejecuta primero: python main.py --discover-categories")
        return

    with open(args.views, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    views = cfg.get("views", [])

    sp = None
    uid = None
    if args.create:
        sp = get_user_client()
        me = sp.current_user()
        uid = me["id"]
        logger.info(f"Autenticado como: {me.get('display_name')}")

    print(f"\n{'Vista':<40} {'Canciones':>10}")
    print("-" * 52)
    for v in views:
        name = v.get("name", "Vista sin nombre")
        flt = v.get("filters", {})
        sub = filter_df(df, flt)
        print(f"{name:<40} {len(sub):>10}")

        if args.create and sp and uid and len(sub) > 0:
            pl_name = f"{args.prefix + ' - ' if args.prefix else ''}{name}"
            pid = ensure_playlist(sp, uid, pl_name, args.public)
            uris = [u for u in sub["uri"].dropna().tolist() if u]
            sp.playlist_replace_items(pid, [])
            add_tracks_in_chunks(sp, pid, uris)
            print(f"  OK Creada: {pl_name} ({len(uris)} canciones)")

    print()


if __name__ == "__main__":
    main()

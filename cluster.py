from __future__ import annotations
import argparse, os, time
from typing import List, Dict, Any
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
try:
    import hdbscan  # optional
    HAS_HDBSCAN = True
except Exception:
    HAS_HDBSCAN = False

import spotipy
from spotify_client import get_user_client, ensure_playlist, add_tracks_in_chunks, clear_playlist
from dotenv import load_dotenv

SCOPES = ["playlist-modify-public","playlist-modify-private","user-library-read"]

def main():
    ap = argparse.ArgumentParser(description="Clustering de canciones para formar playlists por cluster")
    ap.add_argument("--csv", default="export/tracks_with_features.csv")
    ap.add_argument("--algo", choices=["hdbscan","kmeans"], default="hdbscan")
    ap.add_argument("--k", type=int, default=20, help="k clusters si usas kmeans")
    ap.add_argument("--min-cluster-size", type=int, default=50, help="hdbscan min_cluster_size")
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--public", action="store_true")
    ap.add_argument("--prefix", default="Cluster")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    if args.limit:
        df = df.head(args.limit)

    feat_cols = [
        "lfm_energy",
        "lfm_valence",
        "lfm_danceability",
        "lfm_acousticness",
        "lfm_instrumentalness",
    ]
    legacy_cols = ["feat_energy","feat_valence","feat_danceability","feat_tempo","feat_acousticness","feat_mode"]
    if not any(c in df.columns for c in feat_cols):
        feat_cols = legacy_cols
    for c in feat_cols:
        if c not in df.columns: df[c] = 0.0
    emo_cols = [c for c in df.columns if c.startswith("emo_")]
    lyric_cols = [c for c in df.columns if c.startswith("lyric_") and c != "lyric_themes"]
    use_cols = feat_cols + emo_cols + lyric_cols

    X = df[use_cols].fillna(0.0).astype(float).values
    X = StandardScaler().fit_transform(X)

    if args.algo == "hdbscan":
        if not HAS_HDBSCAN:
            print("HDBSCAN no disponible, usa --algo kmeans")
            return
        clusterer = hdbscan.HDBSCAN(min_cluster_size=args.min_cluster_size)
        labels = clusterer.fit_predict(X)
    else:
        km = KMeans(n_clusters=args.k, n_init=10, random_state=42)
        labels = km.fit_predict(X)

    df["cluster"] = labels
    os.makedirs("export", exist_ok=True)
    df.to_csv("export/clusters.csv", index=False, encoding="utf-8")
    print(f"Exportado export/clusters.csv con {len(df)} filas, clusters: {len(set(labels))}")

    if args.dry_run or not args.create:
        return

    sp = get_user_client()
    me = sp.current_user(); uid = me["id"]

    for cl in sorted(df["cluster"].dropna().unique().tolist()):
        sub = df[df["cluster"] == cl]
        if len(sub) < 10:
            continue
        name = f"{args.prefix} - #{int(cl)}"
        pid = ensure_playlist(sp, uid, name, args.public)
        uris = [u for u in sub["uri"].dropna().tolist() if u]
        clear_playlist(sp, pid)
        add_tracks_in_chunks(sp, pid, uris)
        print(f"OK Playlist cluster creada: {name} ({len(uris)} temas)")

if __name__ == "__main__":
    main()

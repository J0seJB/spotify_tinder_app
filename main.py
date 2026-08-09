#!/usr/bin/env python3
# main.py — Spotify AI Playlist Builder
from __future__ import annotations
import os
import time
import argparse
import logging
from typing import List, Dict, Any, Optional

import pandas as pd
from dotenv import load_dotenv

from spotify_client import (
    get_user_client, get_app_client,
    fetch_all_liked,
    get_artists_info, ensure_playlist,
    get_playlist_track_uris, add_tracks_in_chunks,
)
from utils import CATEGORY_PROFILES, score_categories, pick_categories_multi
from dynamic_categories import (
    build_lfm_rows,
    collect_lastfm_data,
    discover_categories,
    enrich_rows_with_genius,
    export_discovery,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def build_track_meta(liked_items, artists_by_id):
    meta = {}
    for it in liked_items:
        tr = (it or {}).get("track") or {}
        if not tr.get("id"):
            continue
        tid = tr["id"]
        artist_objs = tr.get("artists", []) or []
        artist_names = [a.get("name", "") for a in artist_objs if a.get("name")]
        artist_ids = [a.get("id", "") for a in artist_objs if a.get("id")]
        genres = []
        for aid in artist_ids:
            a = artists_by_id.get(aid, {})
            genres.extend(a.get("genres", []) or [])
        meta[tid] = {
            "name": tr.get("name", ""),
            "uri": tr.get("uri", ""),
            "artists": "; ".join(artist_names),
            "artist_ids": artist_ids,
            "genres": genres,
        }
    return meta


def classify_and_bucket(liked_items, feats_by_id, artists_by_id, track_meta, min_conf, categories):
    buckets = {c: [] for c in categories}
    for it in liked_items:
        tr = (it or {}).get("track") or {}
        if not tr or not tr.get("id"):
            continue
        tid = tr["id"]
        meta = track_meta.get(tid, {})
        if not meta.get("uri"):
            continue
        feats = feats_by_id.get(tid, {})
        scores = score_categories(feats, meta.get("genres", []), meta.get("artists", "").split("; "))
        row_base = {
            "track_id": tid, "uri": meta["uri"], "name": meta["name"],
            "artists": meta["artists"], "artist_ids": "; ".join(meta["artist_ids"]),
            "genres": "; ".join(meta["genres"]),
        }
        for k in ("tempo", "energy", "valence", "danceability", "acousticness", "mode"):
            if k in feats:
                row_base[f"feat_{k}"] = feats[k]
        multi = pick_categories_multi(scores, default_min_conf=min_conf, max_categories=3)
        for cat, sc in multi:
            buckets.setdefault(cat, []).append({**row_base, "best_category": cat, "best_score": sc})
    return buckets


# ─────────────────────────────────────────
# Sistema de aprendizaje por rondas
# ─────────────────────────────────────────

def _extract_signals(tid, track_meta, artists_by_id):
    meta = track_meta.get(tid, {})
    genres = []
    artist_names = []
    for aid in meta.get("artist_ids", []):
        art = artists_by_id.get(aid, {})
        genres.extend(art.get("genres", []))
        name = art.get("name", "")
        if name:
            artist_names.append(name.lower())
    return {"genres": genres, "artists": artist_names}


def _update_signals(tids, weight, signal_dict, track_meta, artists_by_id):
    for tid in tids:
        signals = _extract_signals(tid, track_meta, artists_by_id)
        for s in signals["genres"] + signals["artists"]:
            signal_dict[s] = signal_dict.get(s, 0.0) + weight


def _rescore_with_feedback(suggestions, approved_signals, rejected_signals,
                           track_meta, artists_by_id, approved_ids, already_shown):
    rescored = []
    for tid, base_score, meta in suggestions:
        if tid in approved_ids or tid in already_shown:
            continue
        signals = _extract_signals(tid, track_meta, artists_by_id)
        all_signals = signals["genres"] + signals["artists"]
        bonus = sum(approved_signals.get(s, 0.0) for s in all_signals)
        penalty = sum(rejected_signals.get(s, 0.0) for s in all_signals)
        max_possible = max(len(all_signals), 1)
        final_score = base_score + (bonus / max_possible) * 0.4 - (penalty / max_possible) * 0.5
        final_score = max(0.0, min(1.0, final_score))
        rescored.append((tid, round(final_score, 4), meta))
    rescored.sort(key=lambda x: -x[1])
    return rescored


# ─────────────────────────────────────────
# Playlist inteligente con aprendizaje
# ─────────────────────────────────────────

def smart_playlist_mode(sp_user, sp_app, user_id, playlist_name, liked_items,
                        feats_by_id, artists_by_id, track_meta, public,
                        top_n=50, use_ai=True, dry_run=False):
    from ai_playlist import suggest_from_seeds

    all_liked_ids = list(track_meta.keys())

    print("\n" + "═" * 60)
    print(f"🎵  PLAYLIST INTELIGENTE: «{playlist_name}»")
    print("═" * 60)
    print("\nBusca canciones semilla. Escribe nombre o artista (vacío para terminar):\n")

    seed_ids = []
    while True:
        query = input("  Buscar → ").strip().lower()
        if not query:
            if not seed_ids:
                print("  ⚠  Añade al menos 1 canción semilla.")
                continue
            break
        matches = [
            (tid, meta) for tid, meta in track_meta.items()
            if query in meta.get("name", "").lower() or query in meta.get("artists", "").lower()
        ][:10]
        if not matches:
            print("  Sin resultados.\n")
            continue
        for i, (tid, meta) in enumerate(matches):
            marker = " ✓" if tid in seed_ids else ""
            print(f"  [{i+1}] {meta['name']} — {meta['artists']}{marker}")
        sel = input("  Número(s) separados por coma: ").strip()
        for token in sel.split(","):
            token = token.strip()
            if token.isdigit():
                idx = int(token) - 1
                if 0 <= idx < len(matches):
                    tid, meta = matches[idx]
                    if tid not in seed_ids:
                        seed_ids.append(tid)
                        print(f"  ✅  {meta['name']} — {meta['artists']}")
        print()

    print(f"\n🔍 Analizando perfil de {len(seed_ids)} canción(es) semilla...")
    result = suggest_from_seeds(
        seed_track_ids=seed_ids,
        all_liked_ids=all_liked_ids,
        features_by_id=feats_by_id,
        artists_by_id=artists_by_id,
        track_meta=track_meta,
        top_n=top_n,
        use_ai_description=use_ai,
    )

    profile = result["profile"]
    all_suggestions = result["suggestions"]
    ai_desc = result.get("ai_description", "")

    genres_sample = list(profile.get("genres", set()))[:6]
    if genres_sample:
        print(f"   Géneros: {', '.join(genres_sample)}")
    if ai_desc:
        print("\n🤖 Claude AI:")
        print("─" * 50)
        print(ai_desc)
        print("─" * 50)

    # ── Rondas de aprendizaje ──
    approved_signals: Dict[str, float] = {}
    rejected_signals: Dict[str, float] = {}
    approved_ids: set = set(seed_ids)
    already_shown: set = set()
    final_approved: List[str] = list(seed_ids)
    round_num = 0

    # Las semillas inicializan señales positivas
    _update_signals(seed_ids, 1.0, approved_signals, track_meta, artists_by_id)

    while True:
        round_num += 1
        print(f"\n{'═' * 60}")
        print(f"  🎯  RONDA {round_num}  —  {len(final_approved)} canciones aprobadas")
        print(f"{'═' * 60}")

        pool = _rescore_with_feedback(
            all_suggestions, approved_signals, rejected_signals,
            track_meta, artists_by_id, approved_ids, already_shown,
        )

        if not pool:
            print("\n⚠  No hay más canciones para sugerir.")
            break

        batch = pool[:10]
        for tid, _, _ in batch:
            already_shown.add(tid)

        print("\n  Selecciona las canciones que quieres en tu playlist.")
        print("  Números separados por coma — ENTER si no quieres ninguna:\n")
        for i, (tid, score, meta) in enumerate(batch, 1):
            print(f"  [{i:2d}] {meta.get('name', '?')} — {meta.get('artists', '?')}  [{score:.0%}]")

        print("\n  [0]  Terminar y crear playlist")
        print("  [s]  Saltar estas 10 y ver más")

        sel = input("\n  Tu selección → ").strip().lower()

        if sel == "0":
            break

        if sel in ("s", "skip", ""):
            # Señal de rechazo leve por saltar
            _update_signals(
                [tid for tid, _, _ in batch], 0.3,
                rejected_signals, track_meta, artists_by_id
            )
            print("  ↩  Mostrando siguientes...\n")
            continue

        # Procesar selección numérica
        selected = set()
        for token in sel.split(","):
            token = token.strip()
            if token.isdigit():
                idx = int(token) - 1
                if 0 <= idx < len(batch):
                    selected.add(idx)

        approved_this = []
        rejected_this = []
        for i, (tid, score, meta) in enumerate(batch):
            if i in selected:
                approved_this.append(tid)
                approved_ids.add(tid)
                final_approved.append(tid)
                print(f"  ✅  {meta.get('name')} — {meta.get('artists')}")
            else:
                rejected_this.append(tid)

        # Actualizar señales
        if approved_this:
            _update_signals(approved_this, 1.0, approved_signals, track_meta, artists_by_id)
        if rejected_this:
            _update_signals(rejected_this, 0.6, rejected_signals, track_meta, artists_by_id)

        # Mostrar qué aprendió
        top_liked = sorted(approved_signals.items(), key=lambda x: -x[1])[:4]
        top_avoid = sorted(rejected_signals.items(), key=lambda x: -x[1])[:3]
        if top_liked:
            print(f"\n  📈 Le gusta: {', '.join(s for s, _ in top_liked)}")
        if top_avoid:
            print(f"  📉 Evitando: {', '.join(s for s, _ in top_avoid)}")

        cont = input("\n  ¿Ver más opciones? (s/n): ").strip().lower()
        if cont not in ("s", "si", "sí", "yes", "y", ""):
            break

    # ── Crear playlist ──
    print(f"\n{'═' * 60}")
    print(f"  Total: {len(final_approved)} canciones  |  {round_num} ronda(s)")
    print(f"{'═' * 60}")

    if dry_run:
        print("\n[DRY-RUN] No se creará la playlist.")
        return

    confirm = input(f"\n¿Crear playlist «{playlist_name}» con {len(final_approved)} canciones? (s/n): ").strip().lower()
    if confirm not in ("s", "si", "sí", "yes", "y"):
        print("Cancelado.")
        return

    all_uris = []
    for tid in final_approved:
        uri = track_meta.get(tid, {}).get("uri", "")
        if uri and uri not in all_uris:
            all_uris.append(uri)

    pid = ensure_playlist(sp_user, user_id, playlist_name, public)
    existing = get_playlist_track_uris(sp_user, pid)
    to_add = [u for u in all_uris if u not in existing]

    if to_add:
        add_tracks_in_chunks(sp_user, pid, to_add)
        print(f"\n✅  «{playlist_name}» creada con {len(to_add)} canciones en Spotify")
    else:
        print("\nℹ  La playlist ya tenía todas esas canciones.")


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def build_arg_parser():
    p = argparse.ArgumentParser(description="Spotify AI Playlist Builder")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--no-features", action="store_true")
    p.add_argument("--create", action="store_true")
    p.add_argument("--public", action="store_true")
    p.add_argument("--prefix", type=str, default=None)
    p.add_argument("--force-replace", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--min-conf", type=float, default=0.45)
    p.add_argument("--smart-playlist", type=str, default=None, metavar="NOMBRE")
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--no-ai", action="store_true")
    p.add_argument("--discover-categories", action="store_true",
                   help="Descubre categorias dinamicas desde tus Me Gusta usando Last.fm")
    p.add_argument("--target-categories", type=int, default=12,
                   help="Numero aproximado de categorias dinamicas")
    p.add_argument("--use-genius", action="store_true",
                   help="Agrega temas de letras de Genius al descubrimiento de categorias")
    p.add_argument("--max-genius-tracks", type=int, default=None,
                   help="Maximo de canciones a analizar con Genius dentro de --discover-categories")
    return p


def main():
    load_dotenv()
    args = build_arg_parser().parse_args()
    public = bool(args.public)
    prefix = args.prefix or time.strftime("%Y-%m-%d")
    min_conf = max(0.0, min(1.0, args.min_conf))
    CATEGORIES = list(CATEGORY_PROFILES.keys())

    try:
        sp_user = get_user_client()
        sp_app = get_app_client()
        me = sp_user.current_user()
        user_id = me["id"]
        logger.info(f"Autenticado como: {me.get('display_name')} ({user_id})")

        liked_items = fetch_all_liked(sp_user, limit=args.limit)
        if not liked_items:
            logger.info("No se encontraron canciones en Me Gusta.")
            return

        track_ids = []
        all_artist_ids = []
        for it in liked_items:
            tr = it.get("track") or {}
            if tr.get("id"):
                track_ids.append(tr["id"])
                for a in tr.get("artists", []) or []:
                    if a.get("id"):
                        all_artist_ids.append(a["id"])

        artists_by_id = get_artists_info(sp_app, all_artist_ids)
        track_meta = build_track_meta(liked_items, artists_by_id)
        feats_by_id = {}

        if args.discover_categories:
            logger.info("Descubriendo categorias dinamicas con Last.fm...")
            lfm_data = collect_lastfm_data(track_meta, track_ids, max_tracks=args.limit)
            rows = build_lfm_rows(liked_items, track_meta, artists_by_id, lfm_data)
            if args.use_genius:
                rows = enrich_rows_with_genius(rows, max_tracks=args.max_genius_tracks)
            categories, df_discovered = discover_categories(
                rows,
                target_categories=args.target_categories,
                use_ai_names=not args.no_ai,
            )
            export_discovery(categories, df_discovered)
            logger.info("CSV exportado: export/tracks_with_lfm.csv")
            logger.info("Categorias generadas: export/generated_categories.json")

            for cat in categories:
                logger.info("  %s: %s canciones", cat["name"], cat["track_count"])

            if args.dry_run:
                logger.info("DRY-RUN: no se crearan playlists.")
                return
            if not args.create:
                logger.info("Usa --create para crear playlists con las categorias descubiertas.")
                return
            if not args.yes:
                confirm = input("Confirmas la creacion de playlists dinamicas? (s/n): ").strip().lower()
                if confirm not in ("s", "si", "sí", "yes", "y"):
                    return

            for cat in categories:
                sub = df_discovered[df_discovered["generated_category_id"] == cat["id"]]
                if sub.empty:
                    continue
                playlist_name = f"{prefix} · {cat['name']}"
                pid = ensure_playlist(sp_user, user_id, playlist_name, public)
                if args.force_replace:
                    sp_user.playlist_replace_items(pid, [])
                existing = get_playlist_track_uris(sp_user, pid) if not args.force_replace else set()
                uris = [u for u in sub["uri"].dropna().tolist() if u]
                to_add = [u for u in uris if u not in existing]
                if to_add:
                    add_tracks_in_chunks(sp_user, pid, to_add)
                    logger.info("✔ %s: +%s", playlist_name, len(to_add))
            return

        if args.smart_playlist:
            smart_playlist_mode(
                sp_user=sp_user, sp_app=sp_app, user_id=user_id,
                playlist_name=args.smart_playlist, liked_items=liked_items,
                feats_by_id=feats_by_id, artists_by_id=artists_by_id,
                track_meta=track_meta, public=public,
                top_n=args.top_n, use_ai=not args.no_ai, dry_run=args.dry_run,
            )
            return

        # Modo clásico
        logger.info("Clasificando…")
        buckets = classify_and_bucket(liked_items, feats_by_id, artists_by_id, track_meta, min_conf, CATEGORIES)

        os.makedirs("export", exist_ok=True)
        rows_for_csv = []
        classified_ids = set()
        for cat, rows in buckets.items():
            rows_for_csv.extend(rows)
            for r in rows:
                classified_ids.add(r["track_id"])
        for it in liked_items:
            tr = it.get("track") or {}
            tid = tr.get("id")
            if tid and tid not in classified_ids:
                meta = track_meta.get(tid, {})
                rows_for_csv.append({
                    "track_id": tid, "uri": meta.get("uri", ""), "name": meta.get("name", ""),
                    "artists": meta.get("artists", ""), "best_category": "", "best_score": 0.0,
                })

        df = pd.DataFrame(rows_for_csv)
        df.to_csv("export/tracks_with_features.csv", index=False, encoding="utf-8")
        logger.info(f"CSV exportado: {len(df)} filas")

        for cat in CATEGORIES:
            n = len(buckets.get(cat, []))
            if n:
                logger.info(f"  {cat}: {n} canciones")

        if args.dry_run:
            logger.info("DRY-RUN: no se crearán playlists.")
            return
        if not args.create:
            logger.info("Usa --create para generar playlists o --smart-playlist 'Nombre' para modo IA.")
            return
        if not args.yes:
            confirm = input("¿Confirmas la creación de playlists? (s/n): ").strip().lower()
            if confirm not in ("s", "si", "sí", "yes", "y"):
                return

        for cat in CATEGORIES:
            rows = buckets.get(cat, [])
            if not rows:
                continue
            playlist_name = f"{prefix} · {cat}"
            pid = ensure_playlist(sp_user, user_id, playlist_name, public)
            if args.force_replace:
                sp_user.playlist_replace_items(pid, [])
            existing = get_playlist_track_uris(sp_user, pid) if not args.force_replace else set()
            uris = [r["uri"] for r in rows if r.get("uri")]
            to_add = [u for u in uris if u and u not in existing]
            if to_add:
                add_tracks_in_chunks(sp_user, pid, to_add)
                logger.info(f"✔ {playlist_name}: +{len(to_add)}")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

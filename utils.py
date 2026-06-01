# utils.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple
import math

# =========================
# Helpers numericos simples
# =========================

def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))

def _gauss(x: float, mu: float, sigma: float) -> float:
    # Kernel gaussiano suave (0..1 aprox) para afinidad a un "mu"
    if sigma <= 0:
        sigma = 1e-6
    return math.exp(-0.5 * ((x - mu) / sigma) ** 2)

def _tri_range(x: float, lo: float, hi: float) -> float:
    # Triangular: 0 fuera del rango; pico en la mitad
    if lo >= hi or x <= lo or x >= hi:
        return 0.0
    mid = (lo + hi) / 2.0
    return 1.0 - abs(x - mid) / ((hi - lo) / 2.0)

def _toward_mu01(x: float, mu: float, sigma: float = 0.18) -> float:
    # Para features 0..1
    return _gauss(_clamp(x), mu, sigma)

def _has_any(genres_set: set[str], needles: List[str]) -> bool:
    # Busqueda flexible (contiene) sobre el join de generos
    g = " ".join(genres_set)
    return any(n in g for n in needles)


# ============================================
# Configuracion de categorias (12 personalizadas)
# Ajusta pesos, rangos y listas sin tocar logica
# ============================================

CATEGORY_PROFILES: Dict[str, Dict[str, Any]] = {
    # 1) Chill con amigos (Feid, Bad Bunny, Alvaro Diaz, Latin Mafia, Rels B)
    "Chill con amigos": {
        "weights": {"tempo": 0.20, "energy": 0.25, "valence": 0.25, "dance": 0.20, "genre_bonus": 0.10},
        "tempo_pref": ("tri", 80, 110),
        "energy_mu": 0.45,
        "valence_mu": 0.55,   # chill pero positivo
        "dance_mu": 0.60,
        "genre_needles": ["reggaeton", "urbano", "latin hip hop", "trap latino", "latin pop", "pop urbano"],
        "artist_whitelist": ["feid", "bad bunny", "alvaro diaz", "alvaro diaz", "latin mafia", "rels b", "saiko", "mora", "rai na", "micro tdh", "sech"],
    },

    # 2) Rock en espanol energetico
    "Rock ES - energetico": {
        "weights": {"tempo": 0.30, "energy": 0.40, "valence": 0.10, "dance": 0.10, "genre_bonus": 0.10},
        "tempo_pref": ("tri", 110, 160),
        "energy_mu": 0.80,
        "valence_mu": 0.55,
        "dance_mu": 0.50,
        "genre_needles": ["rock en espanol", "latin rock", "spanish rock", "argentino rock", "mexican rock"],
        "artist_whitelist": ["enrique bunbury", "hombres g", "mana", "mana", "los enanitos verdes", "la vela puerca", "caramelos de cianuro", "afectica", "los bunkers"],
    },

    # 3) Rock en espanol lento
    "Rock ES - lento": {
        "weights": {"tempo": 0.25, "energy": 0.30, "valence": 0.25, "dance": 0.05, "mode_minor": 0.15},
        "tempo_pref": ("tri", 70, 105),
        "energy_mu": 0.40,
        "valence_mu": 0.40,
        "dance_mu": 0.40,
        "genre_needles": ["rock en espanol", "latin rock", "spanish rock"],
        "artist_whitelist": ["andres calamaro", "andres calamaro", "fito paez", "fito paez", "soda stereo", "caifanes", "los prisioneros", "enrique bunbury"],
    },

    # 4) Rock general / metal alternativo
    "Rock/Alt/Metal": {
        "weights": {"tempo": 0.25, "energy": 0.45, "valence": 0.10, "dance": 0.05, "genre_bonus": 0.15},
        "tempo_pref": ("tri", 95, 170),
        "energy_mu": 0.85,
        "valence_mu": 0.45,
        "dance_mu": 0.45,
        "genre_needles": ["alternative rock", "alt rock", "metal", "nu metal", "post-hardcore", "hard rock", "grunge", "indie rock", "punk"],
        "artist_whitelist": ["linkin park", "deftones", "foo fighters", "nirvana", "queens of the stone age", "bring me the horizon", "metallica", "system of a down"],
    },

    # 5) Balada/Pop en espanol (Andres Cepeda, Fonseca, etc.)
    "Balada/Pop ES (Cepeda/Fonseca)": {
        "weights": {"tempo": 0.15, "energy": 0.20, "valence": 0.35, "dance": 0.05, "acoustic": 0.15, "genre_bonus": 0.10},
        "tempo_pref": ("tri", 65, 105),
        "energy_mu": 0.35,
        "valence_mu": 0.60,
        "dance_mu": 0.40,
        "acoustic_mu": 0.55,
        "genre_needles": ["latin pop", "balada", "balada pop", "cantautor", "tropipop"],
        "artist_whitelist": ["andres cepeda", "andres cepeda", "fonseca", "santiago cruz", "camila", "reik", "morat", "manuel medrano", "ricardo arjona", "pablo alboran", "pablo alboran"],
    },

    # 6) Techno lento
    "Techno - lento": {
        "weights": {"tempo": 0.45, "energy": 0.25, "dance": 0.20, "genre_bonus": 0.10},
        "tempo_pref": ("tri", 115, 125),
        "energy_mu": 0.65,
        "dance_mu": 0.70,
        "genre_needles": ["techno", "deep techno", "melodic techno", "minimal techno", "deep house", "melodic house"],
        "artist_whitelist": ["artbat", "kolsch", "kolsch", "ben bohmer", "ben boehmer", "maceo plex", "stephan bodzin"],
    },

    # 7) Techno energetico
    "Techno - energetico": {
        "weights": {"tempo": 0.45, "energy": 0.35, "dance": 0.15, "genre_bonus": 0.05},
        "tempo_pref": ("tri", 126, 138),
        "energy_mu": 0.80,
        "dance_mu": 0.75,
        "genre_needles": ["techno", "peak time techno", "hard techno", "industrial techno", "rave", "electro house"],
        "artist_whitelist": ["charlotte de witte", "amelie lens", "rebuke", "adam beyer", "umek", "enrico sangiuliano"],
    },

    # 8) Depre en espanol (Kevin Kaarl y similares)
    "Depre ES": {
        "weights": {"tempo": 0.20, "energy": 0.25, "valence": 0.35, "acoustic": 0.10, "mode_minor": 0.10},
        "tempo_pref": ("tri", 60, 95),
        "energy_mu": 0.30,
        "valence_mu": 0.25,
        "acoustic_mu": 0.50,
        "genre_needles": ["indie en espanol", "mexican indie", "latin indie", "cantautor", "folk latino", "sad"],
        "artist_whitelist": ["kevin kaarl", "zorra", "ed maverick", "daniel me estas matando", "este man", "silvestre y la naranja"],
    },

    # 9) Depre en ingles (XXXTentacion y afines)
    "Depre EN": {
        "weights": {"tempo": 0.20, "energy": 0.25, "valence": 0.40, "acoustic": 0.05, "mode_minor": 0.10},
        "tempo_pref": ("tri", 60, 100),
        "energy_mu": 0.30,
        "valence_mu": 0.20,
        "acoustic_mu": 0.45,
        "genre_needles": ["sad rap", "emo rap", "alternative r&b", "bedroom pop", "lo-fi", "indie pop", "indie folk"],
        "artist_whitelist": ["xxxtentacion", "juice wrld", "lil peep", "billie eilish", "the xx", "daughter", "phoebe bridgers"],
    },

    # 10) Musica pa bailar (salsa, bachata, merengue)
    "Pa- bailar (salsa/bachata/merengue)": {
        "weights": {"tempo": 0.20, "energy": 0.25, "valence": 0.25, "dance": 0.25, "genre_bonus": 0.05},
        "tempo_pref": ("tri", 90, 130),  # amplio por subgenero
        "energy_mu": 0.70,
        "valence_mu": 0.65,
        "dance_mu": 0.85,
        "genre_needles": ["salsa", "bachata", "merengue", "tropical", "vallenato"],
        "artist_whitelist": ["grupo niche", "fruko y sus tesos", "aventura", "avventura", "romeo santos", "grupo gale", "los hermanos rosario", "victor manuelle", "jerry rivera"],
    },

    # 11) Rap en espanol
    "Rap ES": {
        "weights": {"tempo": 0.20, "energy": 0.25, "valence": 0.10, "dance": 0.20, "genre_bonus": 0.25},
        "tempo_pref": ("tri", 80, 110),
        "energy_mu": 0.60,
        "valence_mu": 0.40,
        "dance_mu": 0.55,
        "genre_needles": ["rap espanol", "rap espanol", "hip hop latino", "latin hip hop", "trap latino", "boom bap espanol"],
        "artist_whitelist": ["kase.o", "kase o", "canserbero", "sfdk", "natos", "waor", "los aldeanos", "portavoz", "akira"],
    },

    # 12) Rap en ingles
    "Rap EN": {
        "weights": {"tempo": 0.20, "energy": 0.30, "valence": 0.10, "dance": 0.25, "genre_bonus": 0.15},
        "tempo_pref": ("tri", 80, 110),
        "energy_mu": 0.65,
        "valence_mu": 0.45,
        "dance_mu": 0.65,
        "genre_needles": ["hip hop", "rap", "trap", "boom bap", "east coast hip hop", "west coast hip hop", "southern hip hop"],
        "artist_whitelist": ["drake", "kendrick lamar", "j. cole", "j cole", "travis scott", "nas", "jay-z", "jay z", "tyler, the creator", "tyler the creator", "21 savage"],
    },
}


# ==================================================
# Scoring principal (features + generos + artistas)
# ==================================================

def score_categories(features: Dict[str, Any], genres: List[str], artists: List[str] | None = None) -> Dict[str, float]:
    """
    Devuelve {categoria: score 0..1} usando:
      - Audio features: energy, valence, danceability, tempo, acousticness, mode (opcional)
      - Generos agregados de artistas (strings)
      - Coincidencia de artistas (whitelist)
    Si no hay features, usa heuristica con generos/artistas.
    """
    artists = [a.lower() for a in (artists or [])]
    gset = set((g or "").lower() for g in (genres or []))

    # Si NO hay features utiles, usa solo generos/artistas como heuristica sencilla
    has_feats = any(k in features for k in ("energy", "valence", "danceability", "tempo", "acousticness", "mode"))
    if not has_feats:
        scores: Dict[str, float] = {}
        for cat, prof in CATEGORY_PROFILES.items():
            genre_hit = _has_any(gset, prof.get("genre_needles", []))
            artist_hit = any(a in (prof.get("artist_whitelist") or []) for a in artists)
            base = 0.0
            if genre_hit:
                base += 0.6
            if artist_hit:
                base += 0.2
            scores[cat] = _clamp(base)
        return scores

    # Con features
    energy = float(features.get("energy", 0.0) or 0.0)
    valence = float(features.get("valence", 0.0) or 0.0)
    dance = float(features.get("danceability", 0.0) or 0.0)
    tempo = float(features.get("tempo", 0.0) or 0.0)
    acoustic = float(features.get("acousticness", 0.0) or 0.0)
    mode = int(features.get("mode", 1) or 1)  # 1 mayor, 0 menor

    aset = set((a or "").lower() for a in (artists or []))

    scores: Dict[str, float] = {}

    for cat, prof in CATEGORY_PROFILES.items():
        W = prof.get("weights", {})
        s = 0.0

        # Tempo con preferencia triangular
        if "tempo_pref" in prof and isinstance(prof["tempo_pref"], tuple) and len(prof["tempo_pref"]) == 3:
            _, lo, hi = prof["tempo_pref"]
            s += W.get("tempo", 0.0) * _tri_range(tempo, float(lo), float(hi))

        # Kernels gaussianos para features 0..1
        if "energy_mu" in prof:
            s += W.get("energy", 0.0) * _toward_mu01(energy, float(prof["energy_mu"]))
        if "valence_mu" in prof:
            s += W.get("valence", 0.0) * _toward_mu01(valence, float(prof["valence_mu"]))
        if "dance_mu" in prof:
            s += W.get("dance", 0.0) * _toward_mu01(dance, float(prof["dance_mu"]))
        if "acoustic_mu" in prof:
            s += W.get("acoustic", 0.0) * _toward_mu01(acoustic, float(prof["acoustic_mu"]))

        # Bonos por genero/artista y modo menor (cuando aplique)
        if _has_any(gset, prof.get("genre_needles", [])):
            s += W.get("genre_bonus", 0.0)
        if aset and any(a in aset for a in prof.get("artist_whitelist", [])):
            s += 0.08  # pequeno boost adicional por artista
        if "mode_minor" in W and mode == 0:
            s += W["mode_minor"]

        # Normalizar por suma de pesos, para quedar cerca de 0..1
        denom = sum(W.values()) or 1.0
        scores[cat] = _clamp(s / denom)

    return scores


# =======================================
# Seleccion de una o varias categorias
# =======================================

def pick_best_category(scores: Dict[str, float], min_conf: float = 0.45) -> Tuple[str, float]:
    """
    Devuelve (mejor_categoria, score) aplicando un umbral min_conf.
    Si el mejor score < min_conf, devuelve ("", mejor_score).
    """
    if not scores:
        return ("", 0.0)
    cat, sc = max(scores.items(), key=lambda kv: kv[1])
    return (cat if sc >= float(min_conf) else "", float(sc))


def pick_categories_multi(
    scores: Dict[str, float],
    default_min_conf: float = 0.45,
    max_categories: int = 3,
    margin_ratio: float = 0.85,
) -> List[Tuple[str, float]]:
    """
    Multi-etiquetado: devuelve varias categorias ordenadas por score.
      - Filtra por umbral (default_min_conf).
      - Usa 'margin_ratio' para incluir categorias cercanas al mejor score.
      - Limita a 'max_categories'.
    """
    if not scores:
        return []
    items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_score = items[0][1]
    out: List[Tuple[str, float]] = []
    for cat, sc in items:
        if sc < float(default_min_conf):
            continue
        if sc >= top_score * float(margin_ratio) or len(out) == 0:
            out.append((cat, float(sc)))
        if len(out) >= int(max_categories):
            break
    return out


__all__ = [
    "CATEGORY_PROFILES",
    "score_categories",
    "pick_best_category",
    "pick_categories_multi",
]

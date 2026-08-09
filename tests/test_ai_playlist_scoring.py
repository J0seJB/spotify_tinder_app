from ai_playlist import balance_suggestions_by_seed, score_candidates


def test_score_candidates_filters_cross_family_mood_matches():
    seed_profile = {
        "vector": [0.8, 0.3, 0.4, 0.2, 0.1],
        "tags": ["rock", "hard rock", "alternative rock"],
        "genres": {"album rock", "hard rock", "alternative rock"},
        "families": {"rock"},
        "artists": ["stone temple pilots"],
        "genre_count": {"album rock": 2, "hard rock": 2, "alternative rock": 1},
        "has_lfm": True,
    }
    track_meta = {
        "rock-candidate": {
            "name": "Rock Candidate",
            "artists": "Rock Band",
            "artist_ids": ["rock-artist"],
        },
        "urban-candidate": {
            "name": "Urban Candidate",
            "artists": "Bad Bunny",
            "artist_ids": ["urban-artist"],
        },
    }
    artists_by_id = {
        "rock-artist": {"name": "Rock Band", "genres": ["album rock", "hard rock"]},
        "urban-artist": {"name": "Bad Bunny", "genres": ["reggaeton", "trap latino", "urbano latino"]},
    }
    lfm_data = {
        "rock-candidate": {"tags": ["rock", "hard rock", "energetic"]},
        "urban-candidate": {"tags": ["reggaeton", "energetic", "latin"]},
    }

    suggestions = score_candidates(
        seed_profile=seed_profile,
        candidate_ids=["rock-candidate", "urban-candidate"],
        track_meta=track_meta,
        artists_by_id=artists_by_id,
        lfm_data=lfm_data,
        lastfm_similar={},
        exclude_ids=set(),
        top_n=10,
    )

    assert [tid for tid, _, _ in suggestions] == ["rock-candidate"]


def test_score_candidates_ignores_mood_only_matches():
    seed_profile = {
        "vector": [0.8, 0.3, 0.4, 0.2, 0.1],
        "tags": ["rock"],
        "genres": {"rock"},
        "families": {"rock"},
        "artists": [],
        "genre_count": {"rock": 1},
        "has_lfm": True,
    }
    track_meta = {
        "mood-only": {
            "name": "Mood Only",
            "artists": "Unknown",
            "artist_ids": ["unknown"],
        },
    }
    artists_by_id = {
        "unknown": {"name": "Unknown", "genres": []},
    }
    lfm_data = {
        "mood-only": {"tags": ["energetic", "melancholic"]},
    }

    suggestions = score_candidates(
        seed_profile=seed_profile,
        candidate_ids=["mood-only"],
        track_meta=track_meta,
        artists_by_id=artists_by_id,
        lfm_data=lfm_data,
        lastfm_similar={},
        exclude_ids=set(),
        top_n=10,
    )

    assert suggestions == []


def test_balance_suggestions_interleaves_direct_matches_by_seed():
    suggestions = [
        ("drake-1", 0.99, {"name": "Drake 1"}),
        ("drake-2", 0.98, {"name": "Drake 2"}),
        ("drake-3", 0.97, {"name": "Drake 3"}),
        ("feid-1", 0.70, {"name": "Feid 1"}),
        ("feid-2", 0.69, {"name": "Feid 2"}),
        ("other-1", 0.60, {"name": "Other"}),
    ]
    lastfm_matches = {
        "drake-1": {"score": 0.99, "seed_ids": {"seed-drake"}},
        "drake-2": {"score": 0.98, "seed_ids": {"seed-drake"}},
        "drake-3": {"score": 0.97, "seed_ids": {"seed-drake"}},
        "feid-1": {"score": 0.70, "seed_ids": {"seed-feid"}},
        "feid-2": {"score": 0.69, "seed_ids": {"seed-feid"}},
    }

    balanced = balance_suggestions_by_seed(
        suggestions=suggestions,
        lastfm_matches=lastfm_matches,
        seed_ids=["seed-drake", "seed-feid"],
        top_n=6,
    )

    assert [tid for tid, _, _ in balanced[:4]] == ["drake-1", "feid-1", "drake-2", "feid-2"]

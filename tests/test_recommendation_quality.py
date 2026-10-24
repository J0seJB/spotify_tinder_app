from fastapi.testclient import TestClient

from ai_playlist import diversify_suggestions, score_candidates, track_fingerprint
from api import _cache_for_access_token, app


client = TestClient(app)


def _track(name, artist_id, artist_name):
    return {
        "name": name,
        "artists": artist_name,
        "artist_ids": [artist_id],
        "genres": [],
        "uri": f"spotify:track:{artist_id}-{name}",
        "album_name": "",
        "image_url": None,
        "preview_url": None,
    }


def test_score_candidates_prioritizes_related_tracks_by_other_artists():
    metadata = {
        "same-artist": _track("Another song", "seed-artist", "Seed Artist"),
        "new-artist": _track("Related song", "new-artist", "New Artist"),
    }
    profile = {
        "vector": [0.5] * 5,
        "genres": set(),
        "genre_count": {},
        "artists": ["seed artist"],
        "has_lfm": False,
    }

    recommendations = score_candidates(
        profile,
        ["same-artist", "new-artist"],
        metadata,
        {
            "seed-artist": {"name": "Seed Artist", "genres": []},
            "new-artist": {"name": "New Artist", "genres": []},
        },
        {},
        {},
        exclude_ids=set(),
        top_n=10,
    )

    assert [track_id for track_id, _, _ in recommendations] == ["new-artist", "same-artist"]


def test_fingerprint_ignores_common_release_suffixes_for_duplicate_tracks():
    original = _track("Song (2011 Remastered)", "artist-1", "Artist")
    reissue = _track("Song", "artist-1", "Artist")

    assert track_fingerprint(original) == track_fingerprint(reissue)


def test_diversifier_uses_other_artists_before_repeating_one():
    recommendations = [
        ("a1", 0.9, _track("A one", "artist-a", "Artist A")),
        ("a2", 0.8, _track("A two", "artist-a", "Artist A")),
        ("b1", 0.7, _track("B one", "artist-b", "Artist B")),
        ("c1", 0.6, _track("C one", "artist-c", "Artist C")),
    ]

    ordered = diversify_suggestions(recommendations, artist_gap=2)

    assert [track_id for track_id, _, _ in ordered] == ["a1", "b1", "c1", "a2"]


def test_next_excludes_seed_and_duplicate_tracks_and_spaces_same_artist():
    token = "recommendation-quality-session"
    cache = _cache_for_access_token(token)
    cache.clear()
    seed = _track("Seed song", "seed-artist", "Seed Artist")
    seed_reissue = _track("Seed song (Remastered)", "seed-artist", "Seed Artist")
    artist_a_first = _track("A first", "artist-a", "Artist A")
    artist_a_second = _track("A second", "artist-a", "Artist A")
    artist_a_duplicate = _track("A second (2015 Remaster)", "artist-a", "Artist A")
    artist_b = _track("B song", "artist-b", "Artist B")
    artist_c = _track("C song", "artist-c", "Artist C")
    cache.update({
        "sp_user": None,
        "track_meta": {
            "seed": seed,
            "seed-reissue": seed_reissue,
            "a1": artist_a_first,
            "a2": artist_a_second,
            "a2-duplicate": artist_a_duplicate,
            "b1": artist_b,
            "c1": artist_c,
        },
        "artists_by_id": {},
        "all_liked_ids": ["seed", "a1", "a2", "b1", "c1"],
        "suggestions": [
            ("seed-reissue", 1.0, seed_reissue),
            ("a1", 0.95, artist_a_first),
            ("a2", 0.90, artist_a_second),
            ("a2-duplicate", 0.85, artist_a_duplicate),
            ("b1", 0.80, artist_b),
            ("c1", 0.70, artist_c),
        ],
        "shown_ids": {"seed"},
        "approved_ids": {"seed"},
        "approved_signals": {},
        "rejected_signals": {},
        "final_approved": ["seed"],
        "seed_ids": ["seed"],
        "recent_artist_ids": ["id:seed-artist"],
        "loaded": True,
    })

    responses = [
        client.get("/next", headers={"Authorization": f"Bearer {token}"})
        for _ in range(4)
    ]
    track_ids = [response.json()["cards"][0]["id"] for response in responses]
    primary_artist_ids = [
        cache["track_meta"][track_id]["artist_ids"][0]
        for track_id in track_ids
    ]

    assert track_ids == ["a1", "b1", "c1", "a2"]
    assert "seed-reissue" not in track_ids
    assert "a2-duplicate" not in track_ids
    assert all(left != right for left, right in zip(primary_artist_ids, primary_artist_ids[1:]))

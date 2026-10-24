import spotipy
from fastapi.testclient import TestClient

from api import _cache, _cache_for_access_token, app


client = TestClient(app)


def _with_cache_state():
    original = _cache.copy()
    _cache.update({
        "track_meta": {},
        "artists_by_id": {},
        "all_liked_ids": [],
        "loaded": True,
    })
    return original


def test_library_endpoint_returns_paginated_saved_tracks():
    original = _with_cache_state()
    try:
        _cache["all_liked_ids"] = ["one", "two", "three"]
        _cache["track_meta"] = {
            "one": {"name": "One", "artists": "Artist A"},
            "two": {"name": "Two", "artists": "Artist B"},
            "three": {"name": "Three", "artists": "Artist C"},
        }

        response = client.get("/library?offset=1&limit=1")

        assert response.status_code == 200
        assert response.json() == {
            "results": [{
                "id": "two",
                "name": "Two",
                "artists": "Artist B",
                "image_url": None,
                "preview_url": None,
                "in_library": True,
            }],
            "offset": 1,
            "limit": 1,
            "total": 3,
        }
    finally:
        _cache.clear()
        _cache.update(original)


def test_library_search_matches_saved_track_names_and_artists():
    original = _with_cache_state()
    try:
        _cache["all_liked_ids"] = ["one", "two"]
        _cache["track_meta"] = {
            "one": {"name": "Song One", "artists": "Artist A"},
            "two": {"name": "Different", "artists": "Artist B"},
        }

        response = client.get("/search?q=artist+a&source=library")

        assert response.status_code == 200
        assert [track["id"] for track in response.json()["results"]] == ["one"]
    finally:
        _cache.clear()
        _cache.update(original)


def test_spotify_catalog_search_caches_tracks_as_possible_seeds(monkeypatch):
    original = _with_cache_state()
    try:
        cache = _cache_for_access_token("user-token")
        cache.clear()
        cache.update({
            "sp_user": None,
            "track_meta": {},
            "artists_by_id": {},
            "all_liked_ids": [],
            "suggestions": [],
            "shown_ids": set(),
            "approved_ids": set(),
            "approved_signals": {},
            "rejected_signals": {},
            "final_approved": [],
            "seed_ids": [],
            "loaded": True,
        })
        class FakeSpotify:
            def __init__(self, **kwargs):
                assert kwargs["auth"] == "user-token"

            def search(self, **kwargs):
                assert kwargs == {"q": "test song", "type": "track", "limit": 20}
                return {"tracks": {"items": [{
                    "id": "catalog-track",
                    "name": "Test song",
                    "uri": "spotify:track:catalog-track",
                    "preview_url": "https://audio.example/preview.mp3",
                    "artists": [{"id": "artist-1", "name": "Artist One"}],
                    "album": {
                        "name": "Album One",
                        "images": [{"url": "https://images.example/cover.jpg"}],
                    },
                }]}}

        monkeypatch.setattr(spotipy, "Spotify", FakeSpotify)
        response = client.get(
            "/search?q=test%20song&source=spotify",
            headers={"Authorization": "Bearer user-token"},
        )

        assert response.status_code == 200
        assert response.json()["results"][0]["id"] == "catalog-track"
        assert response.json()["results"][0]["in_library"] is False
        assert cache["track_meta"]["catalog-track"]["uri"] == "spotify:track:catalog-track"
        assert cache["track_meta"]["catalog-track"]["image_url"] == "https://images.example/cover.jpg"
        assert cache["artists_by_id"]["artist-1"]["name"] == "Artist One"
    finally:
        _cache.clear()
        _cache.update(original)


def test_spotify_catalog_search_requires_user_authorization():
    original = _with_cache_state()
    try:
        response = client.get("/search?q=test%20song&source=spotify")

        assert response.status_code == 401
        assert "Inicia sesión" in response.json()["detail"]
    finally:
        _cache.clear()
        _cache.update(original)


def test_seeds_must_exist_in_library_or_spotify_search_cache():
    original = _with_cache_state()
    try:
        response = client.post("/seeds", json={"track_ids": ["unknown-track"]})

        assert response.status_code == 400
        assert "Busca las canciones" in response.json()["detail"]
    finally:
        _cache.clear()
        _cache.update(original)


def test_spotify_catalog_tracks_can_be_used_as_seeds(monkeypatch):
    original = _with_cache_state()
    try:
        _cache["track_meta"] = {
            "catalog-track": {
                "name": "Catalog song",
                "artists": "Artist One",
                "artist_ids": ["artist-1"],
                "uri": "spotify:track:catalog-track",
            }
        }
        _cache["artists_by_id"] = {"artist-1": {"name": "Artist One", "genres": []}}
        monkeypatch.setattr(
            "ai_playlist.suggest_from_seeds",
            lambda **kwargs: {
                "suggestions": [],
                "profile": {"genres": set(), "tags": [], "dominant_themes": []},
            },
        )

        response = client.post("/seeds", json={"track_ids": ["catalog-track"]})

        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert _cache["seed_ids"] == ["catalog-track"]
    finally:
        _cache.clear()
        _cache.update(original)


def test_selecting_multiple_releases_of_same_seed_keeps_one(monkeypatch):
    original = _with_cache_state()
    try:
        _cache["track_meta"] = {
            "original": {
                "name": "Song",
                "artists": "Artist One",
                "artist_ids": ["artist-1"],
                "uri": "spotify:track:original",
            },
            "remaster": {
                "name": "Song (2015 Remastered)",
                "artists": "Artist One",
                "artist_ids": ["artist-1"],
                "uri": "spotify:track:remaster",
            },
        }
        _cache["artists_by_id"] = {"artist-1": {"name": "Artist One", "genres": []}}
        monkeypatch.setattr(
            "ai_playlist.suggest_from_seeds",
            lambda **kwargs: {
                "suggestions": [],
                "profile": {"genres": set(), "tags": [], "dominant_themes": []},
            },
        )

        response = client.post("/seeds", json={"track_ids": ["original", "remaster"]})

        assert response.status_code == 200
        assert response.json()["seeds"] == 1
        assert _cache["seed_ids"] == ["original"]
    finally:
        _cache.clear()
        _cache.update(original)

from fastapi.testclient import TestClient

from api import _cache, app
from main import build_track_meta


client = TestClient(app)


def test_root_reports_ok():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_is_available_without_spotify_session():
    response = client.get("/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["loaded"] is False
    assert payload["total_tracks"] == 0
    assert payload["total_spotify"] == 0
    assert payload["total_unique"] == 0
    assert payload["seeds"] == 0
    assert payload["approved"] == 0


def test_load_does_not_block_on_artist_genre_fetch(monkeypatch):
    original = _cache.copy()
    try:
        fake_liked_items = [{
            "track": {
                "id": "track-1",
                "name": "One",
                "uri": "spotify:track:track-1",
                "artists": [{"id": "artist-1", "name": "Artist"}],
            }
        }]
        monkeypatch.setattr("spotify_client.get_user_client", lambda: object())
        monkeypatch.setattr("spotify_client.fetch_all_liked", lambda _sp, limit=None: fake_liked_items)
        monkeypatch.setattr("spotify_client.get_app_client", lambda: (_ for _ in ()).throw(AssertionError("should not fetch app client")))
        monkeypatch.setattr("spotify_client.get_artists_info", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not fetch artist genres on load")))
        _cache.update({
            "sp_user": None,
            "track_meta": {},
            "artists_by_id": {},
            "all_liked_ids": [],
            "loaded": False,
        })

        response = client.post("/load")

        assert response.status_code == 200
        assert response.json() == {
            "ok": True,
            "total": 1,
            "total_spotify": 1,
            "total_unique": 1,
            "duplicates_removed": 0,
        }
        assert _cache["track_meta"]["track-1"]["artists"] == "Artist"
        assert _cache["artists_by_id"] == {}
        assert _cache["total_saved_tracks"] == 1
    finally:
        _cache.clear()
        _cache.update(original)


def test_build_track_meta_deduplicates_same_song_and_artist():
    liked_items = [
        {
            "track": {
                "id": "track-a",
                "name": "Iris",
                "uri": "spotify:track:track-a",
                "artists": [{"id": "artist-1", "name": "Goo Goo Dolls"}],
                "album": {"name": "Album A", "images": []},
            }
        },
        {
            "track": {
                "id": "track-b",
                "name": "Iris",
                "uri": "spotify:track:track-b",
                "artists": [{"id": "artist-1", "name": "Goo Goo Dolls"}],
                "album": {"name": "Album B", "images": []},
            }
        },
    ]

    meta = build_track_meta(liked_items, {})

    assert list(meta.keys()) == ["track-a"]


def test_next_uses_actual_batch_size_for_remaining(monkeypatch):
    original = _cache.copy()
    try:
        monkeypatch.setattr("api._get_sp", lambda: (_ for _ in ()).throw(AssertionError("should not fetch Spotify track details")))
        _cache.update({
            "sp_user": None,
            "track_meta": {
                "track-1": {
                    "artist_ids": [],
                    "uri": "spotify:track:track-1",
                    "name": "One",
                    "artists": "A",
                    "album_name": "Album",
                    "image_url": "https://example.com/cover.jpg",
                    "preview_url": None,
                    "external_url": "https://open.spotify.com/track/track-1",
                }
            },
            "artists_by_id": {},
            "suggestions": [("track-1", 0.9, {"name": "One", "artists": "A", "uri": "spotify:track:track-1"})],
            "shown_ids": set(),
            "approved_ids": set(),
            "approved_signals": {},
            "rejected_signals": {},
        })

        response = client.get("/next?count=3")

        assert response.status_code == 200
        payload = response.json()
        assert payload["remaining"] == 0
        assert payload["cards"][0]["album"] == "Album"
        assert payload["cards"][0]["image_url"] == "https://example.com/cover.jpg"
    finally:
        _cache.clear()
        _cache.update(original)


def test_player_current_normalizes_spotify_playback(monkeypatch):
    class FakeSpotify:
        def current_playback(self):
            return {
                "is_playing": True,
                "progress_ms": 42000,
                "device": {"id": "dev-1", "name": "PC", "is_active": True},
                "item": {
                    "id": "track-1",
                    "name": "One",
                    "uri": "spotify:track:track-1",
                    "duration_ms": 180000,
                    "artists": [{"name": "Artist"}],
                },
            }

    monkeypatch.setattr("api._get_sp", lambda: FakeSpotify())

    response = client.get("/player/current")

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_playing"] is True
    assert payload["progress_ms"] == 42000
    assert payload["duration_ms"] == 180000
    assert payload["track"]["name"] == "One"
    assert payload["device"]["name"] == "PC"


def test_player_seek_calls_spotify_seek(monkeypatch):
    calls = []

    class FakeSpotify:
        def seek_track(self, position_ms, device_id=None):
            calls.append((position_ms, device_id))

    monkeypatch.setattr("api._get_sp", lambda: FakeSpotify())

    response = client.post("/player/seek", json={"position_ms": 12345, "device_id": "dev-1"})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "position_ms": 12345}
    assert calls == [(12345, "dev-1")]


def test_discover_search_uses_spotify_global_search(monkeypatch):
    original = _cache.copy()
    try:
        class FakeSpotify:
            def search(self, q, type, limit):
                assert q == "iris"
                assert type == "track"
                return {
                    "tracks": {
                        "items": [{
                            "id": "spotify-track-1",
                            "name": "Iris",
                            "uri": "spotify:track:spotify-track-1",
                            "artists": [{"id": "artist-1", "name": "Goo Goo Dolls"}],
                            "album": {"name": "Dizzy Up", "images": []},
                            "external_urls": {"spotify": "https://open.spotify.com/track/spotify-track-1"},
                        }]
                    }
                }

        monkeypatch.setattr("api._get_sp", lambda: FakeSpotify())
        _cache.update({"track_meta": {}, "loaded": False})

        response = client.get("/search?q=iris&source=discover")

        assert response.status_code == 200
        payload = response.json()
        assert payload["source"] == "discover"
        assert payload["results"][0]["id"] == "spotify-track-1"
        assert _cache["track_meta"]["spotify-track-1"]["name"] == "Iris"
    finally:
        _cache.clear()
        _cache.update(original)


def test_discover_seeds_build_suggestions_from_lastfm(monkeypatch):
    original = _cache.copy()
    try:
        class FakeLastFm:
            def get_similar_tracks(self, artist, track, limit=35):
                assert artist == "Goo Goo Dolls"
                assert track == "Iris"
                return [{"name": "Slide", "artist": "Goo Goo Dolls", "match": 0.91}]

        class FakeSpotify:
            def search(self, q, type, limit):
                assert "Slide" in q
                return {
                    "tracks": {
                        "items": [{
                            "id": "slide-1",
                            "name": "Slide",
                            "uri": "spotify:track:slide-1",
                            "artists": [{"id": "artist-1", "name": "Goo Goo Dolls"}],
                            "album": {"name": "Dizzy Up", "images": []},
                            "external_urls": {"spotify": "https://open.spotify.com/track/slide-1"},
                        }]
                    }
                }

        monkeypatch.setattr("api._get_sp", lambda: FakeSpotify())
        monkeypatch.setattr("lastfm_client.get_lastfm_client", lambda: FakeLastFm())
        _cache.update({
            "track_meta": {
                "seed-1": {
                    "id": "seed-1",
                    "name": "Iris",
                    "uri": "spotify:track:seed-1",
                    "artists": "Goo Goo Dolls",
                    "artist_ids": ["artist-1"],
                    "genres": [],
                    "duplicate_key": "iris::goo goo dolls",
                }
            },
            "artists_by_id": {},
            "all_liked_ids": [],
            "loaded": True,
        })

        response = client.post("/seeds", json={"track_ids": ["seed-1"], "source": "discover"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["source"] == "discover"
        assert payload["suggestions"] == 1
        assert _cache["suggestions"][0][0] == "slide-1"
        assert _cache["source_mode"] == "discover"
    finally:
        _cache.clear()
        _cache.update(original)


def test_feedback_reports_remaining_after_learning():
    original = _cache.copy()
    try:
        _cache.update({
            "track_meta": {
                "track-1": {"artist_ids": ["artist-1"], "uri": "spotify:track:track-1", "name": "One", "artists": "A"},
                "track-2": {"artist_ids": ["artist-1"], "uri": "spotify:track:track-2", "name": "Two", "artists": "A"},
            },
            "artists_by_id": {"artist-1": {"name": "Artist", "genres": ["pop"]}},
            "suggestions": [
                ("track-1", 0.9, {"name": "One", "artists": "A"}),
                ("track-2", 0.8, {"name": "Two", "artists": "A"}),
            ],
            "shown_ids": {"track-1"},
            "approved_ids": set(),
            "approved_signals": {},
            "rejected_signals": {},
            "rejected_ids": set(),
            "final_approved": [],
        })

        response = client.post("/feedback", json={"approved": [], "rejected": ["track-1"]})

        assert response.status_code == 200
        assert response.json()["remaining"] == 1
        assert response.json()["learning"]["dislikes"]
    finally:
        _cache.clear()
        _cache.update(original)


def test_complete_playlist_adds_best_remaining_tracks():
    original = _cache.copy()
    try:
        _cache.update({
            "track_meta": {
                "seed-1": {"artist_ids": ["artist-1"], "uri": "spotify:track:seed-1", "name": "Seed 1", "artists": "Artist"},
                "seed-2": {"artist_ids": ["artist-1"], "uri": "spotify:track:seed-2", "name": "Seed 2", "artists": "Artist"},
                "seed-3": {"artist_ids": ["artist-1"], "uri": "spotify:track:seed-3", "name": "Seed 3", "artists": "Artist"},
                "seed-4": {"artist_ids": ["artist-1"], "uri": "spotify:track:seed-4", "name": "Seed 4", "artists": "Artist"},
                "seed-5": {"artist_ids": ["artist-1"], "uri": "spotify:track:seed-5", "name": "Seed 5", "artists": "Artist"},
                "track-1": {"artist_ids": ["artist-1"], "uri": "spotify:track:track-1", "name": "One", "artists": "Artist"},
                "track-2": {"artist_ids": ["artist-2"], "uri": "spotify:track:track-2", "name": "Two", "artists": "Other"},
            },
            "artists_by_id": {
                "artist-1": {"name": "Artist", "genres": ["rock"]},
                "artist-2": {"name": "Other", "genres": ["pop"]},
            },
            "suggestions": [
                ("track-2", 0.6, {"name": "Two", "artists": "Other"}),
                ("track-1", 0.9, {"name": "One", "artists": "Artist"}),
            ],
            "shown_ids": {"seed-1", "seed-2", "seed-3", "seed-4", "seed-5"},
            "approved_ids": {"seed-1", "seed-2", "seed-3", "seed-4", "seed-5"},
            "approved_signals": {"rock": 5.0, "artist": 5.0},
            "rejected_signals": {},
            "rejected_ids": set(),
            "final_approved": ["seed-1", "seed-2", "seed-3", "seed-4", "seed-5"],
        })

        response = client.post("/complete-playlist", json={"target_total": 6})

        assert response.status_code == 200
        payload = response.json()
        assert payload["added"] == 1
        assert payload["approved_total"] == 6
        assert payload["tracks"][0]["name"] == "One"
        assert _cache["final_approved"][-1] == "track-1"
        assert "track-1" in _cache["shown_ids"]
    finally:
        _cache.clear()
        _cache.update(original)


def test_next_skips_duplicate_song_versions():
    original = _cache.copy()
    try:
        _cache.update({
            "track_meta": {
                "seed-1": {
                    "artist_ids": [],
                    "uri": "spotify:track:seed-1",
                    "name": "Iris",
                    "artists": "Goo Goo Dolls",
                    "duplicate_key": "iris::goo goo dolls",
                },
                "dup-1": {
                    "artist_ids": [],
                    "uri": "spotify:track:dup-1",
                    "name": "Iris",
                    "artists": "Goo Goo Dolls",
                    "duplicate_key": "iris::goo goo dolls",
                },
                "track-2": {
                    "artist_ids": [],
                    "uri": "spotify:track:track-2",
                    "name": "Name",
                    "artists": "Other",
                    "duplicate_key": "name::other",
                },
            },
            "artists_by_id": {},
            "suggestions": [
                ("dup-1", 0.99, {"name": "Iris", "artists": "Goo Goo Dolls"}),
                ("track-2", 0.8, {"name": "Name", "artists": "Other"}),
            ],
            "shown_ids": {"seed-1"},
            "approved_ids": {"seed-1"},
            "approved_signals": {},
            "rejected_signals": {},
            "rejected_ids": set(),
            "final_approved": ["seed-1"],
        })

        response = client.get("/next?count=1")

        assert response.status_code == 200
        payload = response.json()
        assert payload["cards"][0]["id"] == "track-2"
    finally:
        _cache.clear()
        _cache.update(original)


def test_complete_playlist_requires_enough_selected_tracks():
    original = _cache.copy()
    try:
        _cache.update({
            "track_meta": {
                "seed-1": {"artist_ids": [], "uri": "spotify:track:seed-1"},
                "track-1": {"artist_ids": [], "uri": "spotify:track:track-1"},
            },
            "artists_by_id": {},
            "suggestions": [("track-1", 0.9, {"name": "One", "artists": "A"})],
            "shown_ids": {"seed-1"},
            "approved_ids": {"seed-1"},
            "approved_signals": {},
            "rejected_signals": {},
            "final_approved": ["seed-1"],
        })

        response = client.post("/complete-playlist", json={"target_total": 10})

        assert response.status_code == 400
        assert "Necesitas al menos 5" in response.json()["detail"]
    finally:
        _cache.clear()
        _cache.update(original)

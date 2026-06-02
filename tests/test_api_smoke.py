from fastapi.testclient import TestClient

from api import _cache, app


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

        response = client.post("/load?limit=1")

        assert response.status_code == 200
        assert response.json() == {"ok": True, "total": 1}
        assert _cache["track_meta"]["track-1"]["artists"] == "Artist"
        assert _cache["artists_by_id"] == {}
    finally:
        _cache.clear()
        _cache.update(original)


def test_next_uses_actual_batch_size_for_remaining(monkeypatch):
    original = _cache.copy()
    try:
        monkeypatch.setattr("api._get_track_details", lambda _: {
            "image_url": None,
            "preview_url": None,
            "album_name": "",
            "external_url": None,
            "uri": "",
        })
        _cache.update({
            "sp_user": None,
            "track_meta": {"track-1": {"artist_ids": [], "uri": "spotify:track:track-1", "name": "One", "artists": "A"}},
            "artists_by_id": {},
            "suggestions": [("track-1", 0.9, {"name": "One", "artists": "A", "uri": "spotify:track:track-1"})],
            "shown_ids": set(),
            "approved_ids": set(),
            "approved_signals": {},
            "rejected_signals": {},
        })

        response = client.get("/next?count=3")

        assert response.status_code == 200
        assert response.json()["remaining"] == 0
    finally:
        _cache.clear()
        _cache.update(original)


def test_feedback_reports_remaining_after_learning():
    original = _cache.copy()
    try:
        _cache.update({
            "track_meta": {
                "track-1": {"artist_ids": ["artist-1"], "uri": "spotify:track:track-1"},
                "track-2": {"artist_ids": ["artist-1"], "uri": "spotify:track:track-2"},
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
            "final_approved": [],
        })

        response = client.post("/feedback", json={"approved": [], "rejected": ["track-1"]})

        assert response.status_code == 200
        assert response.json()["remaining"] == 1
        assert response.json()["learning"]["dislikes"]
    finally:
        _cache.clear()
        _cache.update(original)

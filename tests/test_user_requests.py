import spotipy
from fastapi.testclient import TestClient

from api import _cache, app


client = TestClient(app)


def _save_cache():
    original = _cache.copy()
    _cache.update({
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
        "loaded": False,
    })
    return original


def test_load_uses_the_authenticated_users_token_without_app_credentials(monkeypatch):
    original = _save_cache()
    try:
        class FakeSpotify:
            def __init__(self, **kwargs):
                assert kwargs["auth"] == "friend-access-token"

        monkeypatch.setattr(spotipy, "Spotify", FakeSpotify)
        monkeypatch.setattr(
            "spotify_client.fetch_all_liked",
            lambda _sp, limit=None, raise_on_error=False: [{
                "track": {
                    "id": "friend-track",
                    "name": "Friend song",
                    "uri": "spotify:track:friend-track",
                    "artists": [{"id": "friend-artist", "name": "Friend artist"}],
                }
            }],
        )

        response = client.post(
            "/load",
            headers={"Authorization": "Bearer friend-access-token"},
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True, "total": 1}
        assert _cache["track_meta"]["friend-track"]["name"] == "Friend song"
        assert _cache["loaded_auth_mode"] == "user"
    finally:
        _cache.clear()
        _cache.update(original)


def test_load_returns_actionable_error_for_unexpected_library_failure(monkeypatch):
    original = _save_cache()
    try:
        class FakeSpotify:
            def __init__(self, **kwargs):
                pass

        monkeypatch.setattr(spotipy, "Spotify", FakeSpotify)
        monkeypatch.setattr(
            "spotify_client.fetch_all_liked",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("temporary upstream failure")
            ),
        )

        response = client.post(
            "/load",
            headers={"Authorization": "Bearer friend-access-token"},
        )

        assert response.status_code == 502
        assert "Vuelve a iniciar sesión" in response.json()["detail"]
    finally:
        _cache.clear()
        _cache.update(original)


def test_load_explains_spotify_development_allowlist_for_forbidden_user(monkeypatch):
    original = _save_cache()
    try:
        class FakeSpotify:
            def __init__(self, **kwargs):
                pass

        monkeypatch.setattr(spotipy, "Spotify", FakeSpotify)
        monkeypatch.setattr(
            "spotify_client.fetch_all_liked",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                spotipy.SpotifyException(403, -1, "Forbidden")
            ),
        )

        response = client.post(
            "/load",
            headers={"Authorization": "Bearer friend-access-token"},
        )

        assert response.status_code == 403
        assert "Users Management" in response.json()["detail"]
        assert "Spotify Premium" in response.json()["detail"]
    finally:
        _cache.clear()
        _cache.update(original)


def test_playlist_creation_uses_requesting_users_token(monkeypatch):
    original = _save_cache()
    calls = []
    try:
        _cache.update({
            "final_approved": ["friend-track"],
            "track_meta": {
                "friend-track": {"uri": "spotify:track:friend-track"}
            },
        })

        class FakeSpotify:
            def __init__(self, **kwargs):
                assert kwargs["auth"] == "friend-access-token"

            def current_user(self):
                return {"id": "friend-user"}

        monkeypatch.setattr(spotipy, "Spotify", FakeSpotify)
        monkeypatch.setattr(
            "spotify_client.ensure_playlist",
            lambda sp, user_id, name, public: (
                calls.append(("create", user_id, name, public)) or "playlist-1"
            ),
        )
        monkeypatch.setattr(
            "spotify_client.get_playlist_track_uris",
            lambda _sp, playlist_id: set(),
        )
        monkeypatch.setattr(
            "spotify_client.add_tracks_in_chunks",
            lambda _sp, playlist_id, uris: calls.append(("add", playlist_id, uris)),
        )

        response = client.post(
            "/create-playlist",
            json={"name": "Friend playlist", "public": False},
            headers={"Authorization": "Bearer friend-access-token"},
        )

        assert response.status_code == 200
        assert response.json()["playlist_id"] == "playlist-1"
        assert calls == [
            ("create", "friend-user", "Friend playlist", False),
            ("add", "playlist-1", ["spotify:track:friend-track"]),
        ]
    finally:
        _cache.clear()
        _cache.update(original)

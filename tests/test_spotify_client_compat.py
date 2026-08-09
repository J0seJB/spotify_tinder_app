from unittest.mock import MagicMock

from spotify_client import ensure_playlist, get_artists_info, get_audio_features_resilient


def test_get_artists_info_fetches_artists_individually():
    sp = MagicMock()
    sp.artist.side_effect = [
        {"id": "artist-1", "name": "Artist 1", "genres": ["pop"]},
        {"id": "artist-2", "name": "Artist 2", "genres": ["rock"]},
    ]

    result = get_artists_info(sp, ["artist-1", "artist-2", "artist-1"])

    assert result == {
        "artist-1": {"id": "artist-1", "name": "Artist 1", "genres": ["pop"]},
        "artist-2": {"id": "artist-2", "name": "Artist 2", "genres": ["rock"]},
    }
    sp.artist.assert_any_call("artist-1")
    sp.artist.assert_any_call("artist-2")
    sp.artists.assert_not_called()


def test_ensure_playlist_creates_playlist_for_current_user():
    sp = MagicMock()
    sp.current_user_playlists.return_value = {"items": [], "next": None}
    sp.current_user_playlist_create.return_value = {"id": "playlist-1"}

    playlist_id = ensure_playlist(sp, "ignored-user-id", "Mi playlist", public=False)

    assert playlist_id == "playlist-1"
    sp.current_user_playlist_create.assert_called_once_with(
        name="Mi playlist",
        public=False,
        description="Autogenerada",
    )
    sp.user_playlist_create.assert_not_called()


def test_audio_features_are_disabled_by_default(monkeypatch):
    sp = MagicMock()
    monkeypatch.delenv("SPOTIFY_ENABLE_AUDIO_FEATURES", raising=False)

    result = get_audio_features_resilient(sp, ["track-1"])

    assert result == {}
    sp.audio_features.assert_not_called()

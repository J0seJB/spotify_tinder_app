from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from api import app


client = TestClient(app)


def test_login_starts_spotify_authorization_with_state_cookie(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("SPOTIFY_REDIRECT_URI", "https://api.example.com/callback")

    response = client.get("/login", follow_redirects=False)

    assert response.status_code == 307
    query = parse_qs(urlparse(response.headers["location"]).query)
    state = query["state"][0]
    assert query["redirect_uri"] == ["https://api.example.com/callback"]
    assert response.cookies["spotify_oauth_state"] == state


def test_callback_rejects_missing_or_mismatched_state(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("SPOTIFY_REDIRECT_URI", "https://api.example.com/callback")

    response = client.get("/callback?code=not-a-real-code&state=wrong")

    assert response.status_code == 400
    assert response.json()["detail"].startswith("La autorización expiró")


def test_callback_exchanges_code_and_redirects_to_absolute_frontend(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("SPOTIFY_REDIRECT_URI", "https://api.example.com/callback")
    monkeypatch.setenv("FRONTEND_URL", "https://web.example.com")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "test-access-token"}

    def fake_post(url, **kwargs):
        assert url == "https://accounts.spotify.com/api/token"
        assert kwargs["data"]["grant_type"] == "authorization_code"
        assert kwargs["data"]["redirect_uri"] == "https://api.example.com/callback"
        assert kwargs["auth"] == ("test-client", "test-secret")
        return FakeResponse()

    monkeypatch.setattr("api.requests.post", fake_post)
    login_response = client.get("/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    response = client.get(f"/callback?code=single-use-code&state={state}", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "https://web.example.com#access_token=test-access-token"
    assert "spotify_oauth_state" not in response.cookies


def test_callback_rejects_frontend_url_without_scheme(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("SPOTIFY_REDIRECT_URI", "https://api.example.com/callback")
    monkeypatch.setenv("FRONTEND_URL", "web.example.com")
    monkeypatch.setattr(
        "api.requests.post",
        lambda *_args, **_kwargs: pytest.fail("Must validate FRONTEND_URL before exchanging code"),
    )
    login_response = client.get("/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    response = client.get(f"/callback?code=single-use-code&state={state}", follow_redirects=False)

    assert response.status_code == 500
    assert response.json()["detail"].startswith("FRONTEND_URL debe ser una URL completa")

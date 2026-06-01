from fastapi.testclient import TestClient

from api import app


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

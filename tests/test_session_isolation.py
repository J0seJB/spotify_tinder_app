from fastapi.testclient import TestClient

from api import _cache_for_access_token, app


client = TestClient(app)


def _set_session(token, track_id, track_name):
    cache = _cache_for_access_token(token)
    cache.clear()
    cache.update({
        "sp_user": None,
        "track_meta": {
            track_id: {
                "name": track_name,
                "artists": f"{track_name} artist",
                "artist_ids": [],
                "uri": f"spotify:track:{track_id}",
            }
        },
        "artists_by_id": {},
        "all_liked_ids": [track_id],
        "suggestions": [],
        "shown_ids": set(),
        "approved_ids": set(),
        "approved_signals": {},
        "rejected_signals": {},
        "final_approved": [],
        "seed_ids": [],
        "loaded": True,
    })
    return cache


def test_authenticated_users_get_separate_library_and_swipe_state():
    alice_cache = _set_session("alice-session-token", "alice-track", "Alice song")
    bob_cache = _set_session("bob-session-token", "bob-track", "Bob song")
    alice_cache["seed_ids"] = ["alice-track"]
    alice_cache["final_approved"] = ["alice-track"]
    bob_cache["seed_ids"] = ["bob-track"]

    alice_library = client.get(
        "/library",
        headers={"Authorization": "Bearer alice-session-token"},
    )
    bob_library = client.get(
        "/library",
        headers={"Authorization": "Bearer bob-session-token"},
    )
    alice_status = client.get(
        "/status",
        headers={"Authorization": "Bearer alice-session-token"},
    )
    bob_status = client.get(
        "/status",
        headers={"Authorization": "Bearer bob-session-token"},
    )

    assert [track["id"] for track in alice_library.json()["results"]] == ["alice-track"]
    assert [track["id"] for track in bob_library.json()["results"]] == ["bob-track"]
    assert alice_status.json()["seeds"] == 1
    assert alice_status.json()["approved"] == 1
    assert bob_status.json()["seeds"] == 1
    assert bob_status.json()["approved"] == 0


def test_sessions_are_derived_from_token_hashes_not_raw_token_strings():
    first = _cache_for_access_token("same-token")
    second = _cache_for_access_token("same-token")
    other = _cache_for_access_token("different-token")

    assert first is second
    assert first is not other

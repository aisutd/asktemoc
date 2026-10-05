import time

from app.db.models import User
from app.db.services import UserService
from tests.conftest import make_token


def test_upsert_creates_then_updates(db):
    created = UserService.upsert_user(db, "google:1", "Ana@UTDallas.edu", "Ana")
    assert created.id is not None
    assert created.email == "ana@utdallas.edu"
    created_at, first_seen = created.created_at, created.last_seen_at

    time.sleep(0.01)
    updated = UserService.upsert_user(db, "google:1", "ana@utdallas.edu", "Ana Lopez")
    assert updated.id == created.id
    assert updated.name == "Ana Lopez"
    assert updated.last_seen_at > first_seen
    assert updated.created_at == created_at
    assert db.query(User).count() == 1


def test_same_email_new_provider_keeps_one_row(db):
    a = UserService.upsert_user(db, "google:1", "ana@utdallas.edu", "Ana")
    b = UserService.upsert_user(db, "microsoft-entra-id:9", "ana@utdallas.edu", None)
    assert b.id == a.id
    assert b.provider_sub == "microsoft-entra-id:9"
    assert b.name == "Ana"
    assert db.query(User).count() == 1


def test_authenticated_requests_upsert_user(client, fake_chain, db):
    token = make_token(sub="google:77", email="Lee@utdallas.edu", name="Lee")
    for _ in range(2):
        r = client.post("/api/chat", json={"message": "hi"}, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
    users = db.query(User).all()
    assert [(u.provider_sub, u.email, u.name) for u in users] == [("google:77", "lee@utdallas.edu", "Lee")]


def test_rejected_request_does_not_create_user(client, fake_chain, db):
    token = make_token(email="x@gmail.com")
    client.post("/api/chat", json={"message": "hi"}, headers={"Authorization": f"Bearer {token}"})
    assert db.query(User).count() == 0

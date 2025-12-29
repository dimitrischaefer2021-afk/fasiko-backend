import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    # store chat files in temp (avoid /data in tests)
    chat_dir = tempfile.mkdtemp(prefix="chat_")
    os.environ["CHAT_DIR"] = chat_dir

    # enforce 30MB max
    os.environ["MAX_UPLOAD_BYTES"] = str(30 * 1024 * 1024)

    # IMPORTANT: tests must not require real Ollama
    os.environ["OLLAMA_DISABLED"] = "1"

    from app.main import app  # noqa: E402
    c = TestClient(app)

    yield c

    try:
        os.remove(db_path)
    except FileNotFoundError:
        pass


def test_chat_session_and_message_upload(client: TestClient):
    # create session
    r = client.post("/api/chat/sessions", json={"title": "Test Chat"})
    assert r.status_code == 201
    session_id = r.json()["id"]

    # create message with file upload
    files = [
        ("files", ("note.txt", b"hello", "text/plain")),
    ]
    data = {"role": "user", "content": "Bitte speichern"}
    r = client.post(f"/api/chat/sessions/{session_id}/messages", data=data, files=files)
    assert r.status_code == 201
    body = r.json()
    assert body["session_id"] == session_id
    assert body["role"] == "user"
    assert body["content"] == "Bitte speichern"
    assert len(body["attachments"]) == 1
    assert body["attachments"][0]["filename"] == "note.txt"

    # list messages
    r = client.get(f"/api/chat/sessions/{session_id}/messages")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1


def test_chat_stream_sse_handshake(client: TestClient):
    r = client.post("/api/chat/sessions", json={"title": "Stream Chat"})
    assert r.status_code == 201
    session_id = r.json()["id"]

    # stream endpoint should return event-stream
    with client.stream(
        "POST",
        f"/api/chat/sessions/{session_id}/messages/stream",
        json={"content": "Hallo"}
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")

        # read some bytes
        chunk = next(resp.iter_text())
        assert "data:" in chunk  # should contain SSE data line
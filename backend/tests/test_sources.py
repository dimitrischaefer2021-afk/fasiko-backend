import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="session")
def client():
    # temp DB
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    # temp upload dir
    upload_dir = tempfile.mkdtemp(prefix="uploads_")
    os.environ["UPLOAD_DIR"] = upload_dir
    os.environ["MAX_UPLOAD_BYTES"] = str(30 * 1024 * 1024)

    from app.main import app  # noqa: E402
    c = TestClient(app)

    yield c

    try:
        os.remove(db_path)
    except FileNotFoundError:
        pass

    # best-effort cleanup upload_dir
    try:
        p = Path(upload_dir)
        if p.exists():
            for x in sorted(p.rglob("*"), reverse=True):
                if x.is_file():
                    x.unlink(missing_ok=True)
                else:
                    try:
                        x.rmdir()
                    except Exception:
                        pass
            try:
                p.rmdir()
            except Exception:
                pass
    except Exception:
        pass

def test_sources_upload_list_download_delete_replace(client: TestClient):
    # create project
    r = client.post("/api/projects", json={"name": "P1", "description": "D"})
    assert r.status_code == 201
    project_id = r.json()["id"]

    # upload txt source
    files = {"file": ("note.txt", b"hello world", "text/plain")}
    data = {"tags": '["Architektur","frei-tag"]'}
    r = client.post(f"/api/projects/{project_id}/sources", files=files, data=data)
    assert r.status_code == 201
    src = r.json()
    assert src["filename"] == "note.txt"
    assert src["status"] == "stored"
    src_id = src["id"]

    # list
    r = client.get(f"/api/projects/{project_id}/sources")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(x["id"] == src_id for x in items)

    # download
    r = client.get(f"/api/projects/{project_id}/sources/{src_id}/download")
    assert r.status_code == 200
    assert r.content == b"hello world"

    # replace
    files2 = {"file": ("note.txt", b"v2 content", "text/plain")}
    data2 = {"tags": "Betrieb, neu"}
    r = client.post(f"/api/projects/{project_id}/sources/{src_id}/replace", files=files2, data=data2)
    assert r.status_code == 200
    body = r.json()
    assert body["old_id"] == src_id
    new = body["new"]
    assert new["id"] != src_id
    assert new["status"] == "stored"
    assert new["group_id"] == src["group_id"]

    # delete new
    new_id = new["id"]
    r = client.delete(f"/api/projects/{project_id}/sources/{new_id}")
    assert r.status_code == 204

    # download deleted -> 404
    r = client.get(f"/api/projects/{project_id}/sources/{new_id}/download")
    assert r.status_code == 404
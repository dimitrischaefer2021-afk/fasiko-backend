import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# IMPORTANT: set DATABASE_URL BEFORE importing app
@pytest.fixture(scope="session")
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"

    # also isolate uploads for these tests (not strictly needed here)
    upload_dir = tempfile.mkdtemp(prefix="uploads_proj_")
    os.environ["UPLOAD_DIR"] = upload_dir

    from app.main import app  # noqa: E402
    c = TestClient(app)

    yield c

    try:
        os.remove(path)
    except FileNotFoundError:
        pass

def test_project_crud_contract(client: TestClient):
    # create
    payload = {"name": "Projekt A", "description": "Test"}
    r = client.post("/api/projects", json=payload)
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == "Projekt A"
    project_id = created["id"]

    # list
    r = client.get("/api/projects")
    assert r.status_code == 200
    items = r.json()
    assert any(p["id"] == project_id for p in items)

    # get
    r = client.get(f"/api/projects/{project_id}")
    assert r.status_code == 200
    got = r.json()
    assert got["id"] == project_id

    # update
    r = client.put(f"/api/projects/{project_id}", json={"name": "Projekt A (neu)"})
    assert r.status_code == 200
    upd = r.json()
    assert upd["name"] == "Projekt A (neu)"

    # delete
    r = client.delete(f"/api/projects/{project_id}")
    assert r.status_code == 204

    # get -> 404
    r = client.get(f"/api/projects/{project_id}")
    assert r.status_code == 404
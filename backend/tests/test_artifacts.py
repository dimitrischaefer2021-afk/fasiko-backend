import os
import tempfile

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="session")
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"

    # isolate uploads too (not used here, but keeps env consistent)
    upload_dir = tempfile.mkdtemp(prefix="uploads_art_")
    os.environ["UPLOAD_DIR"] = upload_dir

    from app.main import app  # noqa: E402
    c = TestClient(app)

    yield c

    try:
        os.remove(path)
    except FileNotFoundError:
        pass

def test_artifact_crud_and_versioning_contract(client: TestClient):
    # create project
    r = client.post("/api/projects", json={"name": "Projekt", "description": "D"})
    assert r.status_code == 201
    project_id = r.json()["id"]

    # create artifact with v1
    payload = {
        "type": "sicherheitskonzept",
        "title": "Sicherheitskonzept (Entwurf)",
        "status": "draft",
        "initial_content_md": "# Kapitel 1\n\nText.\n\n## Abschnitt 1.1\n\nMehr Text.",
    }
    r = client.post(f"/api/projects/{project_id}/artifacts", json=payload)
    assert r.status_code == 201
    art = r.json()
    artifact_id = art["id"]
    assert art["current_version"] == 1
    assert art["versions_count"] == 1

    # get detail -> should include current content
    r = client.get(f"/api/projects/{project_id}/artifacts/{artifact_id}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["current_version"] == 1
    assert "# Kapitel 1" in detail["current_content_md"]

    # list artifacts
    r = client.get(f"/api/projects/{project_id}/artifacts")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(x["id"] == artifact_id for x in items)

    # create v2 (make current)
    r = client.post(
        f"/api/projects/{project_id}/artifacts/{artifact_id}/versions",
        json={"content_md": "# Kapitel 1\n\nGeändert.\n", "make_current": True},
    )
    assert r.status_code == 201
    v2 = r.json()
    assert v2["version"] == 2

    # detail now current_version=2
    r = client.get(f"/api/projects/{project_id}/artifacts/{artifact_id}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["current_version"] == 2
    assert "Geändert" in detail["current_content_md"]

    # list versions includes 2 and 1
    r = client.get(f"/api/projects/{project_id}/artifacts/{artifact_id}/versions")
    assert r.status_code == 200
    vers = r.json()["items"]
    assert any(x["version"] == 2 for x in vers)
    assert any(x["version"] == 1 for x in vers)

    # set current back to 1
    r = client.post(
        f"/api/projects/{project_id}/artifacts/{artifact_id}/set-current",
        json={"version": 1},
    )
    assert r.status_code == 200
    assert r.json()["current_version"] == 1

    # update meta (status)
    r = client.put(
        f"/api/projects/{project_id}/artifacts/{artifact_id}",
        json={"status": "review"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "review"

    # delete artifact
    r = client.delete(f"/api/projects/{project_id}/artifacts/{artifact_id}")
    assert r.status_code == 204

    # get -> 404
    r = client.get(f"/api/projects/{project_id}/artifacts/{artifact_id}")
    assert r.status_code == 404
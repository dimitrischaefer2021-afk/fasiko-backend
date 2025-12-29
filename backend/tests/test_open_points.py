import os
import tempfile

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="session")
def client():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    # isolate storage dirs
    uploads_dir = tempfile.mkdtemp(prefix="uploads_")
    openpoints_dir = tempfile.mkdtemp(prefix="openpoints_")
    os.environ["UPLOAD_DIR"] = uploads_dir
    os.environ["OPENPOINT_DIR"] = openpoints_dir
    os.environ["MAX_UPLOAD_BYTES"] = str(30 * 1024 * 1024)

    from app.main import app  # noqa: E402
    c = TestClient(app)

    yield c

    try:
        os.remove(db_path)
    except FileNotFoundError:
        pass

def test_open_points_contract_text_choice_and_file(client: TestClient):
    # create project
    r = client.post("/api/projects", json={"name": "P", "description": "D"})
    assert r.status_code == 201
    project_id = r.json()["id"]

    # create artifact (for optional linking)
    r = client.post(f"/api/projects/{project_id}/artifacts", json={
        "type": "schutzbedarf",
        "title": "Schutzbedarf",
        "initial_content_md": "# Kapitel\n",
        "status": "draft",
    })
    assert r.status_code == 201
    artifact_id = r.json()["id"]

    # create open point (text)
    r = client.post(f"/api/projects/{project_id}/open-points", json={
        "question": "Welche Nutzergruppen sind im Scope?",
        "input_type": "text",
        "priority": "kritisch",
        "status": "offen",
        "artifact_id": artifact_id,
        "bsi_ref": "APP.1.2",
        "section_ref": "Kapitel 2",
        "category": "Organisation",
    })
    assert r.status_code == 201
    op_text = r.json()
    op_text_id = op_text["id"]
    assert op_text["priority"] == "kritisch"
    assert op_text["status"] == "offen"

    # WRONG: sending answer_choice for text must be rejected (prevents Swagger "string")
    r = client.post(
        f"/api/projects/{project_id}/open-points/{op_text_id}/answer",
        json={"answer_text": "Admin", "answer_choice": "string", "mark_done": False},
    )
    assert r.status_code == 400

    # correct answer text -> should mark fertig
    r = client.post(f"/api/projects/{project_id}/open-points/{op_text_id}/answer", json={
        "answer_text": "Admin, Standardnutzer",
        "mark_done": True
    })
    assert r.status_code == 200
    answered = r.json()
    assert answered["status"] == "fertig"
    assert "Admin" in (answered["answer_text"] or "")
    # ensure answer_choice is cleared
    assert answered["answer_choice"] is None

    # create open point (choice)
    r = client.post(f"/api/projects/{project_id}/open-points", json={
        "question": "Gibt es Patchmanagement? (ja/nein)",
        "input_type": "choice",
        "priority": "wichtig",
        "status": "offen",
    })
    assert r.status_code == 201
    op_choice_id = r.json()["id"]

    # WRONG: sending answer_text for choice must be rejected
    r = client.post(
        f"/api/projects/{project_id}/open-points/{op_choice_id}/answer",
        json={"answer_choice": "ja", "answer_text": "irgendwas", "mark_done": True},
    )
    assert r.status_code == 400

    # answer choice
    r = client.post(f"/api/projects/{project_id}/open-points/{op_choice_id}/answer", json={
        "answer_choice": "ja",
        "mark_done": True
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "fertig"
    assert body["answer_choice"] == "ja"
    # ensure answer_text is cleared
    assert body["answer_text"] is None

    # create open point (file)
    r = client.post(f"/api/projects/{project_id}/open-points", json={
        "question": "Bitte lade den Nachweis hoch (Richtlinie).",
        "input_type": "file",
        "priority": "nice-to-have",
        "status": "offen",
    })
    assert r.status_code == 201
    op_file_id = r.json()["id"]

    # attach file
    files = {"file": ("nachweis.txt", b"nachweis-content", "text/plain")}
    r = client.post(f"/api/projects/{project_id}/open-points/{op_file_id}/attachments", files=files)
    assert r.status_code == 201
    att = r.json()
    att_id = att["id"]

    # get detail -> attachments present
    r = client.get(f"/api/projects/{project_id}/open-points/{op_file_id}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["attachments_count"] == 1
    assert len(detail["attachments"]) == 1

    # download attachment
    r = client.get(f"/api/projects/{project_id}/open-points/{op_file_id}/attachments/{att_id}/download")
    assert r.status_code == 200
    assert r.content == b"nachweis-content"

    # list filter by status
    r = client.get(f"/api/projects/{project_id}/open-points?status=fertig")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(x["id"] == op_text_id for x in items)
    assert any(x["id"] == op_choice_id for x in items)

    # update status manually (in_bearbeitung)
    r = client.put(f"/api/projects/{project_id}/open-points/{op_file_id}", json={"status": "in_bearbeitung"})
    assert r.status_code == 200
    assert r.json()["status"] == "in_bearbeitung"
Änderungen im FaSiKo‑Backend

Dieses Änderungsprotokoll dokumentiert alle Anpassungen am Backend. Jede Änderung wird mit dem entsprechenden Block versehen.

Block 01 – Erstellung der Dokumentation
	•	Neue Dateien:
	•	docs/TRUTH.md: initiale Beschreibung des Ist‑Zustands des Repos und der Architektur (siehe TRUTH.md).
	•	docs/CHANGES_LOG.md: dieses Änderungsprotokoll.
	•	Bemerkungen: Es wurden noch keine Code‑Dateien verändert. Die Datenbank verwendet weiterhin SQLite. Die folgenden Blöcke werden die Migration zu PostgreSQL, LLM‑Routing, SearXNG‑Integration und weitere Funktionen umsetzen.

Block 02 – Konfigurationsbasis und Umgebungsvariablen
	•	Neue Datei: .env.example mit allen erforderlichen Umgebungsvariablen (Datenbank‑URL, Speicherpfade, LLM‑Modelle, SearXNG‑URL, Limits, API‑Key, CORS usw.). Diese Datei dient als Vorlage für eigene .env‑Dateien.
	•	Neues Modul: backend/app/settings.py liest sämtliche Umgebungsvariablen. Es definiert Variablen wie DATABASE_URL, UPLOAD_DIR, OLLAMA_URL, MODEL_FASIKO_CREATE_70B, MODEL_GENERAL_8B, SEARXNG_URL, Grenzwerte und Sicherheitsoptionen. Damit werden die bisherigen Einstellungen erweitert.
	•	Änderung an TRUTH.md: Ein Abschnitt „Konfiguration über .env“ wurde hinzugefügt. Darin werden alle verfügbaren Variablen erklärt und ihre Standardwerte dokumentiert.

Block 03 – Migration zu PostgreSQL und Alembic
	•	Neue Abhängigkeiten: psycopg2-binary und alembic wurden zur backend/requirements.txt hinzugefügt, um PostgreSQL‑Support und Datenbankmigrationen zu ermöglichen.
	•	Neue Module:
	•	backend/app/db.py stellt jetzt eine SQLAlchemy‑Engine bereit, die sich dynamisch an die Umgebungsvariable DATABASE_URL anpasst. Es definiert die Basisklasse Base und Funktionen zur Sessionerstellung. Zudem gibt es eine Funktion init_db() für die Erstellung eines frischen Schemas.
	•	backend/app/models.py enthält die kompletten SQLAlchemy‑Modelle für Projekte, Quellen, Artefakte, Versionen, offene Punkte sowie Chat‑Sessions, Nachrichten und Anhänge. Diese wurden aus dem ursprünglichen Repo übernommen.
	•	Migrationstool:
	•	Eine Alembic‑Konfiguration (backend/alembic.ini) und ein Migrationsverzeichnis (backend/alembic/) wurden hinzugefügt. Das Skript env.py liest die DATABASE_URL aus der Umgebung, importiert die Modelle und führt Migrationen offline oder online aus. Die erste Migration (backend/alembic/versions/0001_initial.py) erstellt oder entfernt alle Tabellen mithilfe der SQLAlchemy‑Metadaten.
	•	Startskript: backend/entrypoint.sh führt beim Containerstart automatisch alembic upgrade head aus und startet anschließend Uvicorn. Dies gewährleistet, dass die Datenbank immer auf dem aktuellen Stand ist.
	•	Dockerfile: Ein neues backend/Dockerfile installiert die Abhängigkeiten, kopiert den Anwendungscode, die Alembic‑Dateien und das Startskript in den Container und setzt das Startkommando auf das neue Skript.
	•	Docker‑Compose: Neue docker-compose.yml, die folgende Dienste startet: db (PostgreSQL), backend (FastAPI‑Server), ollama (LLM) und searxng (Websuche). Persistente Volumes (backend_data, pg_data, ollama_data, searxng_data) sorgen für dauerhafte Datenspeicherung.
	•	.env.example: Erweiterung um DATABASE_URL (jetzt Standard‑PostgreSQL), POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST und POSTGRES_PORT. Das Backend generiert aus diesen Variablen automatisch eine DATABASE_URL, falls keine explizite URL gesetzt ist. Hinweise zur Nutzung von SQLite wurden ergänzt.
	•	settings.py: Überarbeitet, um eine DATABASE_URL zu generieren, falls diese nicht explizit gesetzt ist. Es berücksichtigt die neuen POSTGRES_*‑Variablen und ermöglicht weiterhin das Verwenden einer SQLite‑URL für lokale Tests.
	•	TRUTH.md: Abschnitte „Ausgangsarchitektur“, „Bekannte Einschränkungen“ und „Konfiguration über .env“ wurden aktualisiert. Die Dokumentation beschreibt nun die neue Microservice‑Struktur (Backend, DB, LLM, SearXNG), die PostgreSQL‑Migration und die neuen Umgebungsvariablen.

Block 04 – Artefakt‑Generierung über LLM
	•	Neues Modul: backend/app/generator.py implementiert die Anbindung an den Ollama‑Server. Es definiert Prompts für die verschiedenen Artefakt‑Typen (strukturanalyse, schutzbedarf, modellierung, grundschutz_check, risikoanalyse, maßnahmenplan, sicherheitskonzept). Sollte der LLM‑Service nicht verfügbar sein, liefert das Modul ein statisches Skelett.
	•	Neue Endpunkte: Im Router backend/app/api/artifacts.py wurde die Funktionalität zur Generierung implementiert (POST /api/v1/projects/{project_id}/artifacts/generate). Der Nutzer übergibt eine Liste von Artefakt‑Typen; für jeden Typ wird eine neue Version erzeugt. Offene Fragen im LLM‑Output (im Format OFFENE_FRAGE: Kategorie; Frage) werden als offene Punkte angelegt.
	•	Erweiterte Schemas: Die Datei backend/app/schemas.py enthält jetzt die Klassen ArtifactGenerateRequest, GeneratedArtifactOut und ArtifactGenerateResponse. Diese definieren die Eingabe und Ausgabe der Generierung.
	•	Router‑Registrierung: backend/app/main.py registriert nun alle Router (Health, Projekte, Artefakte, Offene Punkte) unter dem Prefix /api/v1. Die bisherige Health‑Funktion im Hauptmodul wurde entfernt, um Dopplungen zu vermeiden.
	•	TRUTH.md aktualisiert: Die Ausgangsarchitektur wurde für Block 04 angepasst. Es gibt nun einen Abschnitt zur Artefakt‑Generierung sowie eine Liste unterstützter Artefakt‑Typen. Die bekannten Einschränkungen wurden entsprechend aktualisiert: Die Generierung ist vorhanden, Bearbeitungen und Websuche folgen in späteren Blöcken.
	•	.env.example: Keine Änderungen erforderlich – die Generierung nutzt weiterhin MODEL_FASIKO_CREATE_70B und OLLAMA_URL.

Block 05 – Websuche & Chat‑Erweiterung
	•	Neue Datei: backend/app/api/chat.py implementiert sämtliche Chat‑Funktionen. Nutzer können Sessions erstellen, umbenennen, löschen, Nachrichten hinzufügen und löschen sowie Dateianhänge hochladen oder herunterladen. Außerdem gibt es einen Assistent‑Endpunkt, der die Frage an den LLM (llama3.1:8b) sendet und zuvor eine Websuche über SearXNG durchführt. Die Ergebnisse der Suche werden als Quellen im Antworttext ausgegeben.
	•	Neue Datei: backend/app/websearch.py stellt eine asynchrone Funktion searxng_search() bereit, die Anfragen an einen selbst gehosteten SearXNG‑Server schickt und eine Liste von Treffern (Titel, URL, Snippet) zurückliefert.
	•	Erweiterungen in backend/app/storage.py: Es wurden Funktionen zum Speichern und Löschen von Chat‑Anhängen hinzugefügt (chat_session_dir, chat_message_dir, save_chat_attachment_to_disk, delete_chat_attachment_files). Dadurch können hochgeladene Dateien in einer klaren Ordnerstruktur (CHAT_DIR/session_id/message_id/attachment_id) abgelegt und wieder entfernt werden.
	•	Erweiterungen in backend/app/schemas.py: Neue Pydantic‑Modelle (ChatSessionUpdate, ChatAttachmentOut, ChatMessageDetailOut, ChatAssistantIn, WebSearchResult, ChatAssistantReplyOut) beschreiben die Eingabe und Ausgabe der Chat‑API, inklusive Assistent und Websuche.
	•	Erweiterungen in backend/app/crud.py: Funktionen delete_chat_session und delete_chat_message wurden ergänzt, um Chat‑Sessions bzw. einzelne Nachrichten inklusive ihrer Anhänge aus der Datenbank zu entfernen.
	•	main.py aktualisiert: Der neue Chat‑Router wird nun unter /api/v1/chat/sessions registriert.
	•	TRUTH.md aktualisiert: Ein neuer Abschnitt „Websuche und Chat (Block 05)“ wurde ergänzt. Außerdem wurde die Beschreibung des Moduls api/chat.py angepasst, um die integrierte Websuche und das LLM‐Modell zu erwähnen.
	•	Sonstiges: Die .env.example bleibt unverändert, da CHAT_DIR bereits enthalten war. Die Docker‑Konfiguration musste nicht angepasst werden, da der SearXNG‑Dienst bereits in Block 03 eingerichtet wurde.

	## Block 06 – Ready-Endpoint & LLM-Routing

### Neue Funktionen

- Neuer Router:
  - `backend/app/api/ready.py`
- Neuer Endpunkt:
  - `GET /api/v1/ready`

### Ready-Checks

Der Ready-Endpoint prüft:

- `database`
  - Verbindungstest via `SELECT 1`
- `llm_llama3.1:8b`
  - POST `/api/chat` gegen Ollama
- `llm_llama3.1:70b`
  - POST `/api/chat` gegen Ollama
- `searxng`
  - HTTP-GET auf SearXNG-Service

Antwortformat:
```json
{
  "components": [
    { "name": "...", "status": "ok|error", "message": "optional" }
  ]
}
LLM-Routing (Generator)
	•	Definition:
	•	Erstellung = erstmalige Generierung eines Artefakts
	•	Bearbeitung = jede Änderung danach
	•	Routing-Regeln:
	•	Erstellung → llama3.1:70b
	•	Bearbeitung & Chat → llama3.1:8b
	•	Fallback-Verhalten:
	•	DEV (ENV_PROFILE != prod)
	•	70B nicht verfügbar → automatischer Fallback auf 8B
	•	PROD
	•	70B nicht verfügbar → statisches Template + Fehlerstatus im Ready-Check
	•	Keine stillen Abweichungen

Anpassungen an bestehenden Dateien
	•	backend/app/schemas.py
	•	Neue Modelle: ReadyComponent, ReadyOut
	•	backend/app/main.py
	•	Registrierung des Ready-Routers unter /api/v1
	•	docs/TRUTH.md
	•	Aktualisierung des Architektur- und Ready-Abschnitts

Ergebnis Block 06
	•	System meldet klaren Betriebszustand
	•	70B-Modell kann lokal fehlschlagen (Hardware-bedingt)
	•	Verhalten ist transparent, reproduzierbar und produktionsfähig
	•	Voraussetzung für Jobs, Exporte und Versionierung geschaffen

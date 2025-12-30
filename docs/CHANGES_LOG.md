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
Wahrheitsquelle für FaSiKo‑Backend

Dieses Dokument beschreibt den aktuellen Ist‑Zustand des Backends (Stand Block 01).

Ausgangsarchitektur (nach Block 04)
	•	Das Backend ist als FastAPI‑Anwendung implementiert (Python 3.11) und läuft im Docker‑Container.
	•	Es gibt einen Ordner backend/app mit folgenden Modulen:
	•	main.py: startet die FastAPI‑App. Seit Block 04 werden alle Router (Health, Projekte, Artefakte, Offene Punkte) unter dem Prefix /api/v1 registriert. Die Chat‑Integration folgt in Block 05.
	•	settings.py: liest Umgebungsvariablen, z. B. APP_NAME, DATABASE_URL, UPLOAD_DIR, OPENPOINT_DIR und MAX_UPLOAD_BYTES.
	•	db.py: definiert eine SQLAlchemy‑Engine; aktuell wird standardmäßig SQLite (sqlite:///…) verwendet.
	•	models.py: enthält SQLAlchemy‑Modelle für Projekte, Quellen, Artefakte, Versionen, offene Punkte, Chat‑Sessions, Chat‑Nachrichten und Anhänge.
	•	crud.py: enthält Datenbank‑CRUD‑Funktionen für Projekte, Quellen, Artefakte/Versionen, offene Punkte, Chat‑Sessions und Nachrichten.
	•	storage.py: regelt das Speichern und Löschen von hochgeladenen Dateien im Dateisystem unter /data.
	•	schemas.py: definiert Pydantic‑Schemas für Ein‑ und Ausgaben der API.
	•	api/: enthält FastAPI‑Router:
	•	projects.py – CRUD‑Operationen für Projekte und Uploads von Quellen.
	•	artifacts.py – Verwaltung von Artefakten, deren Versionen und Generierung. Über einen neuen Endpunkt können Artefakte per LLM erstellt oder aktualisiert werden; offene Fragen werden als offene Punkte gespeichert.
	•	open_points.py – CRUD für offene Punkte sowie Anhänge und Beantworten von Punkten.
	•	chat.py – Chat‑Sessions und Nachrichten mit Uploads. Der Chat nutzt Ollama über die Umgebungsvariable OLLAMA_URL und ein Modell (OLLAMA_CHAT_MODEL) für Antworten (Überarbeitung folgt in Block 05).
	•	health.py – Health‑ und (später) Ready‑Endpoints.
	•	Im Repository liegt eine docker-compose.yml, die vier Dienste startet:
	•	db: PostgreSQL 16‑alpine mit persistentem Volume (pg_data).
	•	backend: FastAPI‑Server mit Uvicorn. Dieser Dienst führt beim Start automatisch Alembic‑Migrationen aus und verbindet sich mit der PostgreSQL‑Datenbank.
	•	ollama: LLM‑Server, der die Modelle llama3.1:8b und llama3.1:70b bereitstellt.
	•	searxng: selbst gehostete Metasuchmaschine für Webrecherche.
Datenpersistenz erfolgt über Volumes: backend_data, pg_data, ollama_data und searxng_data. Die Anwendung verwendet nun PostgreSQL als Standarddatenbank.

Bekannte Einschränkungen (nach Block 03)
	•	Die Migration auf PostgreSQL ist implementiert. Für lokale Experimente kann weiterhin SQLite genutzt werden, indem in der .env eine entsprechende DATABASE_URL gesetzt wird.
	•	Die Generierung von FaSiKo‑Artefakten wurde in Block 04 eingeführt, jedoch existiert noch keine LLM‑unterstützte Bearbeitung (Umschreiben, Diff, Versionierung). Diese Funktionen werden in den folgenden Blöcken ergänzt.
	•	Der Chat‑Endpoint bietet weiterhin keine Websuche; die SearXNG‑Integration folgt in Block 05.
	•	Eine vollständige LLM‑Routing‑Logik für die Nutzung von 70B‑ und 8B‑Modellen wird erst in Block 06 umgesetzt; aktuell nutzt das System 70B nur für die Generierung.
	•	Eine verfeinerte Klassifikation von offenen Punkten (z. B. Kategorie, BSI‑Baustein) wird sukzessive ergänzt. Zurzeit werden Kategorien direkt aus dem LLM‑Output übernommen, sofern vorhanden.

Server und Deployment
	•	Das Projekt wird per docker-compose up gestartet. Die Ports 8000 (Backend) und 11434 (Ollama) werden bereitgestellt.
	•	Uploads werden im Verzeichnis /data/uploads gespeichert; Open‑Point‑Anhänge im Verzeichnis /data/openpoints; Chat‑Uploads im Verzeichnis /data/chat.

Konfiguration über .env

Ab Block 02 gibt es eine Beispiel‑Konfigurationsdatei .env.example im Projekt‑Root. Diese enthält alle wichtigen Umgebungsvariablen, die die Anwendung benötigt. Beim Start werden die Variablen aus einer .env‑Datei oder direkt aus der Umgebung gelesen. Wichtige Parameter:
Variable
Bedeutung
Standardwert
APP_NAME
Anzeigename der Anwendung
FaSiKo‑Studio Backend
ENV_PROFILE
Entwicklungsprofil (dev/prod)
dev
DATABASE_URL
Datenbankverbindung (z. B. PostgreSQL)
sqlite:////data/app.db
UPLOAD_DIR
Speicherort für hochgeladene Quellen
/data/uploads
OPENPOINT_DIR
Speicherort für Anhänge zu offenen Punkten
/data/openpoints
CHAT_DIR
Speicherort für Chat‑Uploads
/data/chat
EXPORT_DIR
Speicherort für Export‑Dateien
/data/exports
MAX_UPLOAD_BYTES
Maximale Upload‑Größe in Bytes
31457280 (30 MB)
MAX_SOURCES_PER_PROJECT
Maximale Anzahl Quellen pro Projekt
50
MAX_PARALLEL_JOBS
Maximale Anzahl gleichzeitiger Jobs
3
JOB_TIMEOUT
Max. Laufzeit eines Jobs in Sekunden
1800
OLLAMA_URL
Basis‑URL des Ollama‑Servers
http://ollama:11434
OLLAMA_CHAT_MODEL
LLM‑Modell für Chats
llama3.1:8b
MODEL_FASIKO_CREATE_70B
Modell zur initialen FaSiKo‑Erstellung
llama3.1:70b
MODEL_GENERAL_8B
Modell für Bearbeitungen
llama3.1:8b
SEARXNG_URL
URL zum SearXNG‑Metasuche‑Service
http://searxng:8080
WEBSEARCH_MAX_RESULTS
Anzahl Suchergebnisse pro Anfrage
5
WEBSEARCH_TIMEOUT
Timeout für Websuche (Sek.)
15
WEBSEARCH_MAX_QUERY_LENGTH
Max. Länge der Suchanfragen
200
API_KEY_ENABLED
Aktiviert API‑Key‑Authentifizierung (true/false)
false
API_KEY
API‑Schlüssel (wenn aktiviert)
–
CORS_ALLOWED_ORIGINS
Liste erlaubter Ursprünge (* für alle)
*

Ab Block 03 gibt es zusätzliche Variablen für die PostgreSQL‑Datenbank:
	•	POSTGRES_DB – Name der Datenbank (Standard: fasiko_db).
	•	POSTGRES_USER – Benutzername für die Verbindung (Standard: fasiko_user).
	•	POSTGRES_PASSWORD – Passwort (Standard: fasiko_pass).
	•	POSTGRES_HOST – Hostname des Datenbankservers (Standard: db innerhalb von Docker).
	•	POSTGRES_PORT – Port des Datenbankservers (Standard: 5432).

Wenn in der Umgebung keine DATABASE_URL gesetzt ist, baut das Backend aus diesen Parametern automatisch eine PostgreSQL‑URL im Format postgresql+psycopg2://<USER>:<PASS>@<HOST>:<PORT>/<DB>. Für lokale Tests können Sie alternativ weiterhin eine SQLite‑URL angeben (beispielsweise sqlite:////tmp/fasiko.db).

Diese Datei wird mit jedem Block aktualisiert, um den Stand der Wahrheit zu dokumentieren.

Artefakt‑Generierung (Block 04)

In Block 04 wurde eine erste KI‑Unterstützung implementiert. Über den Endpunkt
POST /api/v1/projects/{project_id}/artifacts/generate

kann der Nutzer eine oder mehrere Artefakt‑Typen anfordern. Folgende Typen
werden derzeit unterstützt:
	•	strukturanalyse
	•	schutzbedarf
	•	modellierung
	•	grundschutz_check
	•	risikoanalyse
	•	maßnahmenplan
	•	sicherheitskonzept

Der Server sendet für jeden Typ einen vordefinierten Prompt an das LLM
(llama3.1:70b). Fehlen Eingaben, produziert das LLM offene Fragen im
Format OFFENE_FRAGE: Kategorie; Frage. Diese werden als offene
Punkte persistiert. Das generierte Dokument wird als neue Version
gespeichert. Falls das LLM nicht erreichbar ist, liefert der Server
eine einfache Skelett‑Struktur mit Überschriften.
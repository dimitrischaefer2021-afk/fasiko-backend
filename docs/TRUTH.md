Wahrheitsquelle für FaSiKo‑Backend

Dieses Dokument beschreibt den aktuellen Ist‑Zustand des Backends (Stand Block 01).

Ausgangsarchitektur
	•	Das Backend ist als FastAPI‑Anwendung implementiert (Python 3.11) und läuft im Docker‑Container.
	•	Es gibt einen Ordner backend/app mit folgenden Modulen:
	•	main.py: startet die FastAPI‑App und registriert Router für Projekte, Artefakte, offene Punkte, Chat und Health.
	•	settings.py: liest Umgebungsvariablen, z. B. APP_NAME, DATABASE_URL, UPLOAD_DIR, OPENPOINT_DIR und MAX_UPLOAD_BYTES.
	•	db.py: definiert eine SQLAlchemy‑Engine; aktuell wird standardmäßig SQLite (sqlite:///…) verwendet.
	•	models.py: enthält SQLAlchemy‑Modelle für Projekte, Quellen, Artefakte, Versionen, offene Punkte, Chat‑Sessions, Chat‑Nachrichten und Anhänge.
	•	crud.py: enthält Datenbank‑CRUD‑Funktionen für Projekte, Quellen, Artefakte/Versionen, offene Punkte, Chat‑Sessions und Nachrichten.
	•	storage.py: regelt das Speichern und Löschen von hochgeladenen Dateien im Dateisystem unter /data.
	•	schemas.py: definiert Pydantic‑Schemas für Ein‑ und Ausgaben der API.
	•	api/: enthält FastAPI‑Router:
	•	projects.py – CRUD‑Operationen für Projekte und Uploads von Quellen.
	•	artifacts.py – Erstellung und Verwaltung von Artefakten (Meta‑Daten und Versionen). Es erfolgt noch keine KI‑Erzeugung der Inhalte.
	•	open_points.py – CRUD für offene Punkte sowie Anhänge und Beantworten von Punkten.
	•	chat.py – Chat‑Sessions und Nachrichten mit Uploads. Der Chat nutzt Ollama über die Umgebungsvariable OLLAMA_URL und ein Modell (OLLAMA_CHAT_MODEL) für Antworten.
	•	health.py – einfacher Health‑Check.
	•	Im Repository liegt eine docker-compose.yml, die zwei Dienste startet: backend (FastAPI) und ollama (LLM Server). Die Datenpersistenz wird über fasiko_data und ollama_data Volumes realisiert. Standardmäßig wird sqlite genutzt.

Bekannte Einschränkungen
	•	Es gibt noch keine PostgreSQL‑Unterstützung und keine Migration (SQLite wird direkt verwendet).
	•	Die KI‑Logik zur Generierung von FaSiKo‑Dokumenten aus Quellen und zur Erzeugung offener Punkte fehlt.
	•	Der Chat‑Endpoint bietet noch keine Websuche; es wird lediglich der LLM über Ollama angesprochen.
	•	Es gibt keine LLM‑Routing‑Logik für 70B‑/8B‑Modelle und keine Konfiguration per .env.example.
	•	Es existieren keine Dokumente für offene Punkte‐Kategorien, Bausteine oder Artefakt‑Typen; diese müssen noch definiert werden.

Server und Deployment
	•	Das Projekt wird per docker-compose up gestartet. Die Ports 8000 (Backend) und 11434 (Ollama) werden bereitgestellt.
	•	Uploads werden im Verzeichnis /data/uploads gespeichert; Open‑Point‑Anhänge im Verzeichnis /data/openpoints; Chat‑Uploads im Verzeichnis /data/chat.

Diese Datei wird mit jedem Block aktualisiert, um den Stand der Wahrheit zu dokumentieren.
	•	Im Repository liegt eine docker-compose.yml, die zwei Dienste startet: backend (FastAPI) und ollama (LLM Server). Die Datenpersistenz wird über fasiko_data und ollama_data Volumes realisiert. Standardmäßig wird sqlite genutzt.

Bekannte Einschränkungen
	•	Es gibt noch keine PostgreSQL‑Unterstützung und keine Migration (SQLite wird direkt verwendet).
	•	Die KI‑Logik zur Generierung von FaSiKo‑Dokumenten aus Quellen und zur Erzeugung offener Punkte fehlt.
	•	Der Chat‑Endpoint bietet noch keine Websuche; es wird lediglich der LLM über Ollama angesprochen.
	•	Es gibt keine LLM‑Routing‑Logik für 70B‑/8B‑Modelle und keine Konfiguration per .env.example.
	•	Es existieren keine Dokumente für offene Punkte‐Kategorien, Bausteine oder Artefakt‑Typen; diese müssen noch definiert werden.

Server und Deployment
	•	Das Projekt wird per docker-compose up gestartet. Die Ports 8000 (Backend) und 11434 (Ollama) werden bereitgestellt.
	•	Uploads werden im Verzeichnis /data/uploads gespeichert; Open‑Point‑Anhänge im Verzeichnis /data/openpoints; Chat‑Uploads im Verzeichnis /data/chat.

Diese Datei wird mit jedem Block aktualisiert, um den Stand der Wahrheit zu dokumentieren.
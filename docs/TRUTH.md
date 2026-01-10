Wahrheitsquelle für FaSiKo‑Backend

Dieses Dokument beschreibt den aktuellen Ist‑Zustand des Backends (Stand Block 06). Es dient als zentrale Wahrheitsquelle und wird mit jedem Block erweitert.

Ausgangsarchitektur (nach Block 04)
•   Das Backend ist als FastAPI‑Anwendung implementiert (Python 3.11) und läuft im Docker‑Container.
•   Es gibt einen Ordner backend/app mit folgenden Modulen:
•   main.py: startet die FastAPI‑App. Seit Block 04 werden alle Router (Health, Projekte, Artefakte, Offene Punkte, Chat) unter dem Prefix /api/v1 registriert.
•   settings.py: liest Umgebungsvariablen, z. B. APP_NAME, DATABASE_URL, UPLOAD_DIR, OPENPOINT_DIR und MAX_UPLOAD_BYTES.
•   db.py: definiert eine SQLAlchemy‑Engine; standardmäßig wird eine PostgreSQL‑URL verwendet, kann aber via DATABASE_URL überschrieben werden. Eine init_db‑Funktion erzeugt bei Bedarf ein frisches Schema.
•   models.py: enthält SQLAlchemy‑Modelle für Projekte, Quellen, Artefakte, Versionen, offene Punkte, Chat‑Sessions, Chat‑Nachrichten und Anhänge.
•   crud.py: enthält Datenbank‑CRUD‑Funktionen für Projekte, Quellen, Artefakte/Versionen, offene Punkte, Chat‑Sessions und Nachrichten.
•   storage.py: regelt das Speichern und Löschen von hochgeladenen Dateien im Dateisystem unter /data.
•   schemas.py: definiert Pydantic‑Schemas für Ein‑ und Ausgaben der API. Seit Block 06 enthält es auch die Klassen ReadyComponent und ReadyOut für den Ready‑Endpoint.
•   api/: enthält FastAPI‑Router:
•   projects.py – CRUD‑Operationen für Projekte und Uploads von Quellen.
•   artifacts.py – Verwaltung von Artefakten, deren Versionen und Generierung. Über einen Endpunkt können Artefakte per LLM erstellt oder aktualisiert werden; offene Fragen werden als offene Punkte gespeichert.
•   open_points.py – CRUD für offene Punkte sowie Anhänge und Beantworten von Punkten.
•   chat.py – Chat‑Sessions, Nachrichten, Dateianhänge und ein Assistent mit Websuche. Der Chat nutzt das Modell llama3.1:8b. Suchergebnisse des selbst gehosteten SearXNG‑Dienstes werden als Kontext an das LLM übergeben und als Quellen ausgewiesen.
•   health.py – Health‑Endpoint.
•   ready.py – (seit Block 06) Ready‑Endpoint für Betriebsbereitschaftstests.
•   generator.py: implementiert die LLM‑Anbindung für die initiale Artefakt‑Generierung. Es definiert pro Typ einen Prompt und generiert Markdown‑Inhalte. Bei Fehlern nutzt es Fallback‑Skelette.
•   websearch.py: kapselt die Kommunikation mit dem SearXNG‑Service.

Microservices und Container
Im Repository liegt eine docker-compose.yml, die vier Dienste startet:
•   db: PostgreSQL 16‑alpine mit persistentem Volume (pg_data).
•   backend: FastAPI‑Server mit Uvicorn. Dieser Dienst führt beim Start automatisch Alembic‑Migrationen aus und verbindet sich mit der Datenbank. Der Dienst nutzt die in .env konfigurierten Modelle und URLs.
•   ollama: LLM‑Server, der die Modelle llama3.1:8b und llama3.1:70b bereitstellt.
•   searxng: selbst gehostete Metasuchmaschine für Webrecherche.
Datenpersistenz erfolgt über Volumes: backend_data, pg_data, ollama_data und searxng_data.

Bekannte Einschränkungen (vor Block 06)
•   Die Generierung von FaSiKo‑Artefakten wurde in Block 04 eingeführt, jedoch existierte noch keine LLM‑unterstützte Bearbeitung (Umschreiben, Diff, Versionierung). Diese Funktionen werden in zukünftigen Blöcken ergänzt.
•   Die Websuche wurde in Block 05 implementiert. Sie ruft über SearXNG verschiedene Suchmaschinen auf und übergibt die Ergebnisse an das LLM. Snippets werden aus Datenschutzgründen nicht zurückgegeben.
•   Die LLM‑Routing‑Logik wurde erst in Block 06 implementiert. Zuvor nutzte das System immer das 70B‑Modell für die Generierung. Bearbeitungen und Chat nutzten bereits das 8B‑Modell, es gab jedoch keine automatische Fallback‑Logik.

Ready‑Endpunkt und LLM‑Routing (Block 06)
In Block 06 wurde ein neuer Ready‑Endpunkt implementiert. Dieser prüft die folgenden Komponenten und gibt deren Status zurück:
•   database – erfolgreiche Verbindung zur Datenbank (ein einfacher SELECT 1 Test).
•   llm_llama3.1:8b – Testet, ob das 8B‑Modell des Ollama‑Servers erreichbar ist.
•   llm_llama3.1:70b – Testet, ob das 70B‑Modell des Ollama‑Servers erreichbar ist.
•   searxng – Verbindungsprüfung zum SearXNG‑Server.
Der Endpunkt GET /api/v1/ready liefert eine Liste dieser Komponenten mit Status „ok“ oder „error“ sowie einer optionalen Fehlermeldung. So kann ein Orchestrator schnell erkennen, ob das System betriebsbereit ist.
Zusätzlich wurde die LLM‑Routing‑Logik im Generator ergänzt: Das 70B‑Modell wird nur für die initiale Generierung verwendet. Tritt beim Aufruf ein Fehler auf, versucht das System in Entwicklungsumgebungen (ENV_PROFILE ≠ prod) automatisch das 8B‑Modell. In Produktionsumgebungen führt ein Fehler bei 70B zur Nutzung des statischen Skeletts; der Ready‑Check liefert in diesem Fall eine Fehlermeldung. Bearbeitungen und Chat nutzen stets das 8B‑Modell.

Server und Deployment
•   Das Projekt wird per docker‑compose up gestartet. Die Ports 8000 (Backend), 11434 (Ollama) und 8080 (SearXNG) werden bereitgestellt.
•   Uploads werden im Verzeichnis /data/uploads gespeichert; Open‑Point‑Anhänge im Verzeichnis /data/openpoints; Chat‑Uploads im Verzeichnis /data/chat.

Konfiguration über .env
Ab Block 02 gibt es eine Beispiel‑Konfigurationsdatei .env.example im Projekt‑Root. Diese enthält alle wichtigen Umgebungsvariablen, die die Anwendung benötigt. Beim Start werden die Variablen aus einer .env‑Datei oder direkt aus der Umgebung gelesen.

Diese Datei wird mit jedem Block aktualisiert, um den Stand der Wahrheit zu dokumentieren.

Jobs und Export (Block 07)
In Block 07 wurde ein einfacher Job‑Service implementiert, um
langlaufende Aufgaben wie Exporte auszulagern. Der Service
besteht aus zwei API‑Endpunkten:
• POST /api/v1/jobs – startet einen neuen Job. Aktuell wird
nur der Typ “export” unterstützt. Der Nutzer gibt eine
Liste von Artefakt‑IDs und optional ein Dateiformat an.
Das System erzeugt eine Job‑ID, legt einen Eintrag im
in‑memory jobs_store an und startet im Hintergrund den
Exportprozess. Die Antwort enthält die Job‑ID und den
initialen Status (queued).
• GET /api/v1/jobs/{job_id} – gibt den aktuellen Status des
angegebenen Jobs zurück. Ist der Job abgeschlossen, enthält
die Antwort den Namen der erzeugten ZIP‑Datei. Bei Fehlern
wird eine Fehlermeldung geliefert.
Für den Export werden für jede übergebene Artefakt‑ID einfache
Textdateien mit Platzhalter‑Inhalten erzeugt und zu einer ZIP‑Datei
gepackt. Diese Implementierung dient als Platzhalter; in einer
späteren Version sollen echte Artefakt‑Inhalte exportiert und
zusätzliche Formate (DOCX, PDF) unterstützt werden. Das
Export‑Verzeichnis wird über die Umgebungsvariable EXPORT_DIR
definiert (Standard: /data/exports). Diese Variable wurde in
settings.py ergänzt.

Download von Exporten (Block 08)
In Block 08 wurde der Export‑Service um einen Download‑Endpunkt
erweitert. Ein neuer Router backend/app/api/export.py stellt
den Pfad GET /api/v1/exports/{job_id} bereit. Dieser Endpunkt
liefert die ZIP‑Datei eines abgeschlossenen Export‑Jobs, sofern
der Job im Jobs‑Store den Status completed besitzt und das
resultierende Archiv existiert. Damit können Nutzer das Ergebnis
eines Exports herunterladen, nachdem sie den Job‑Status über
GET /api/v1/jobs/{job_id} auf completed geprüft haben.
Der Export‑Mechanismus selbst bleibt unverändert (Platzhalter‑Text
pro Artefakt); nur die Abrufmöglichkeit wurde hinzugefügt. Der
Download‑Endpunkt prüft Pfad und Existenz der Datei im durch
EXPORT_DIR konfigurierten Verzeichnis und gibt sie als
FileResponse zurück. Dieses Feature erweitert den
Job‑Service, ohne die bestehenden Block 07‑Funktionen zu
beeinflussen.

DOCX/PDF‑Export (Block 09)
In Block 09 wird der Export‑Service ausgebaut: Nutzer können
Artefakte nun auch als Microsoft Word‑Dokumente (DOCX) oder
PDF‑Dateien exportieren. Beim Start eines Export‑Jobs darf im
Feld format neben txt jetzt auch docx oder pdf
angegeben werden (Standard bleibt txt). Für jedes Artefakt
wird im angegebenen Format eine Datei erzeugt und anschließend
wie gewohnt zu einer ZIP‑Datei zusammengefasst. Die Erstellung
der unterschiedlichen Formate basiert auf externen Bibliotheken:
•   python‑docx wird verwendet, um ein einfaches DOCX
mit einer Überschrift (Artefakt‑ID) und einem
Platzhaltertext zu erzeugen.
•   reportlab nutzt das Platypus‑Modul, um ein PDF
mit Titel und Platzhaltertext zu erstellen. Es wird
ausschließlich SimpleDocTemplate und Standard‑Styles
verwendet, um die Richtlinien für PDF‑Exports einzuhalten.
Beide Bibliotheken werden erst zur Laufzeit importiert. Falls
eine der Libraries nicht installiert ist, schlägt der Job mit
status=failed fehl und die Fehlermeldung wird im Job‑Status
zurückgegeben. Nicht unterstützte Formate führen zu einer
400 Bad Request. Der Download‑Endpunkt (Block 08)
funktioniert unverändert: Er liefert das erzeugte ZIP‑Archiv
unabhängig vom enthaltenen Dateiformat.

Dokumentenlayout und Export (Block 10)
In Block 10 wurde die Export‑Funktionalität weiterentwickelt,
um die Formatierung der ausgegebenen Dateien zu verbessern. Die
PDF‑Erstellung nutzt jetzt das Platypus‑Modul von reportlab
zusammen mit symmetrischen Seitenrändern (50 pt links und
rechts) und automatischem Zeilenumbruch. Überschriften aus den
generierten Markdown‑Inhalten werden in Heading‑Stile (1–3)
umgesetzt, und Listenpunkte werden einheitlich mit Aufzählungs-
symbolen versehen. In der DOCX‑Erzeugung werden Überschriften
der Stufen 1–3 erkannt und in Word‑Headings überführt;
numerierte Listen erscheinen als nummerierte Word‑Listen und
Aufzählungen als Bullets. Diese Anpassungen sorgen für eine
professionellere Darstellung der exportierten Artefakte und
verhindern, dass Text im PDF rechts abgeschnitten wird. Die
Export‑Schnittstellen und Endpunkte bleiben unverändert – nur
die Darstellung der Inhalte hat sich verbessert.
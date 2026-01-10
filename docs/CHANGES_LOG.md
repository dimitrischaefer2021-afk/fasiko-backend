Änderungen im FaSiKo‑Backend

Dieses Änderungsprotokoll dokumentiert alle Anpassungen am Backend. Jede Änderung wird mit dem entsprechenden Block versehen.

Block 01 – Erstellung der Dokumentation
•   Neue Dateien:
•   docs/TRUTH.md: initiale Beschreibung des Ist‑Zustands des Repos und der Architektur.
•   docs/CHANGES_LOG.md: dieses Änderungsprotokoll.
•   Bemerkungen: Es wurden noch keine Code‑Dateien verändert. Die Datenbank verwendete weiterhin SQLite. Die folgenden Blöcke sollten die Migration zu PostgreSQL, LLM‑Routing, SearXNG‑Integration und weitere Funktionen umsetzen.

Block 02 – Konfigurationsbasis und Umgebungsvariablen
•   Neue Datei: .env.example mit allen erforderlichen Umgebungsvariablen (Datenbank‑URL, Speicherpfade, LLM‑Modelle, SearXNG‑URL, Limits, API‑Key, CORS usw.). Diese Datei dient als Vorlage für eigene .env‑Dateien.
•   Neues Modul: backend/app/settings.py liest sämtliche Umgebungsvariablen. Es definiert Variablen wie DATABASE_URL, UPLOAD_DIR, OLLAMA_URL, MODEL_FASIKO_CREATE_70B, MODEL_GENERAL_8B, SEARXNG_URL, Grenzwerte und Sicherheitsoptionen.
•   Änderung an TRUTH.md: Ein Abschnitt „Konfiguration über .env“ wurde hinzugefügt. Darin werden alle verfügbaren Variablen erklärt und ihre Standardwerte dokumentiert.

Block 03 – Migration zu PostgreSQL und Alembic
•   Neue Abhängigkeiten: psycopg2‑binary und alembic wurden zur backend/requirements.txt hinzugefügt, um PostgreSQL‑Support und Datenbankmigrationen zu ermöglichen.
•   Neue Module:
•   backend/app/db.py stellt jetzt eine SQLAlchemy‑Engine bereit, die sich dynamisch an die Umgebungsvariable DATABASE_URL anpasst. Es definiert die Basisklasse Base und Funktionen zur Sessionerstellung. Zudem gibt es eine Funktion init_db() für die Erstellung eines frischen Schemas.
•   backend/app/models.py enthält die kompletten SQLAlchemy‑Modelle für Projekte, Quellen, Artefakte, Versionen, offene Punkte sowie Chat‑Sessions, Nachrichten und Anhänge.
•   Migrationstool: Eine Alembic‑Konfiguration (backend/alembic.ini) und ein Migrationsverzeichnis (backend/alembic/) wurden hinzugefügt. Das Skript env.py liest die DATABASE_URL aus der Umgebung, importiert die Modelle und führt Migrationen offline oder online aus. Die erste Migration (backend/alembic/versions/0001_initial.py) erstellt alle Tabellen.
•   Startskript: backend/entrypoint.sh führt beim Containerstart automatisch alembic upgrade head aus und startet anschließend Uvicorn. Dies gewährleistet, dass die Datenbank immer auf dem aktuellen Stand ist.
•   Docker‑Compose: Neue docker‑compose.yml, die folgende Dienste startet: db (PostgreSQL), backend (FastAPI‑Server), ollama (LLM) und searxng (Websuche). Persistente Volumes sorgen für dauerhafte Datenspeicherung.
•   .env.example: Erweiterung um DATABASE_URL (jetzt Standard‑PostgreSQL), POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST und POSTGRES_PORT. Das Backend generiert aus diesen Variablen automatisch eine DATABASE_URL, falls keine explizite URL gesetzt ist. Hinweise zur Nutzung von SQLite wurden ergänzt.
•   TRUTH.md: Abschnitte „Ausgangsarchitektur“, „Bekannte Einschränkungen“ und „Konfiguration über .env“ wurden aktualisiert. Die Dokumentation beschreibt nun die neue Microservice‑Struktur (Backend, DB, LLM, SearXNG), die PostgreSQL‑Migration und die neuen Umgebungsvariablen.

Block 04 – Artefakt‑Generierung über LLM
•   Neues Modul: backend/app/generator.py implementiert die Anbindung an den Ollama‑Server. Es definiert Prompts für die verschiedenen Artefakt‑Typen (strukturanalyse, schutzbedarf, modellierung, grundschutz_check, risikoanalyse, maßnahmenplan, sicherheitskonzept). Sollte der LLM‑Service nicht verfügbar sein, liefert das Modul ein statisches Skelett.
•   Neue Endpunkte: Im Router backend/app/api/artifacts.py wurde die Funktionalität zur Generierung implementiert (POST /api/v1/projects/{project_id}/artifacts/generate). Der Nutzer übergibt eine Liste von Artefakt‑Typen; für jeden Typ wird eine neue Version erzeugt. Offene Fragen im LLM‑Output (im Format OFFENE_FRAGE: Kategorie; Frage) werden als offene Punkte angelegt.
•   Erweiterte Schemas: Die Datei backend/app/schemas.py enthält jetzt die Klassen ArtifactGenerateRequest, GeneratedArtifactOut und ArtifactGenerateResponse. Diese definieren die Eingabe und Ausgabe der Generierung.
•   Router‑Registrierung: backend/app/main.py registriert nun alle Router (Health, Projekte, Artefakte, Offene Punkte) unter dem Prefix /api/v1. Die bisherige Health‑Funktion im Hauptmodul wurde entfernt, um Dopplungen zu vermeiden.
•   TRUTH.md aktualisiert: Die Ausgangsarchitektur wurde für Block 04 angepasst. Es gibt nun einen Abschnitt zur Artefakt‑Generierung sowie eine Liste unterstützter Artefakt‑Typen. Die bekannten Einschränkungen wurden entsprechend aktualisiert: Die Generierung ist vorhanden, Bearbeitungen und Websuche folgen in späteren Blöcken.

Block 05 – Websuche & Chat‑Erweiterung
•   Neue Datei: backend/app/api/chat.py implementiert sämtliche Chat‑Funktionen. Nutzer können Sessions erstellen, umbenennen, löschen, Nachrichten hinzufügen und löschen sowie Dateianhänge hochladen oder herunterladen. Außerdem gibt es einen Assistent‑Endpunkt, der die Frage an das LLM (llama3.1:8b) sendet und zuvor eine Websuche über SearXNG durchführt. Die Ergebnisse der Suche werden als Quellen im Antworttext ausgegeben.
•   Neue Datei: backend/app/websearch.py stellt eine asynchrone Funktion searxng_search() bereit, die Anfragen an einen selbst gehosteten SearXNG‑Server schickt und eine Liste von Treffern (Titel und URL) zurückliefert.
•   Erweiterungen in backend/app/storage.py: Es wurden Funktionen zum Speichern und Löschen von Chat‑Anhängen hinzugefügt (chat_session_dir, chat_message_dir, save_chat_attachment_to_disk, delete_chat_attachment_files). Dadurch können hochgeladene Dateien in einer klaren Ordnerstruktur (CHAT_DIR/session_id/message_id/attachment_id) abgelegt und wieder entfernt werden.
•   Erweiterungen in backend/app/schemas.py: Neue Pydantic‑Modelle (ChatSessionUpdate, ChatAttachmentOut, ChatMessageDetailOut, ChatAssistantIn, WebSearchResult, ChatAssistantReplyOut) beschreiben die Eingabe und Ausgabe der Chat‑API, inklusive Assistent und Websuche.
•   Erweiterungen in backend/app/crud.py: Funktionen delete_chat_session und delete_chat_message wurden ergänzt, um Chat‑Sessions bzw. einzelne Nachrichten inklusive ihrer Anhänge aus der Datenbank zu entfernen.
•   main.py aktualisiert: Der neue Chat‑Router wird nun unter /api/v1/chat/sessions registriert.
•   TRUTH.md aktualisiert: Ein neuer Abschnitt „Websuche und Chat (Block 05)“ wurde ergänzt. Außerdem wurde die Beschreibung des Moduls api/chat.py angepasst, um die integrierte Websuche und das LLM‑Modell zu erwähnen.

Block 06 – Ready‑Endpoint und LLM‑Routing
•   Neues Modul: backend/app/api/ready.py implementiert einen Ready‑Endpoint (GET /api/v1/ready), der den Zustand des Backends überprüft. Die Prüfung umfasst die Datenbankverbindung, den Ollama‑Dienst mit den Modellen llama3.1:8b und llama3.1:70b sowie den SearXNG‑Dienst. Für jede Komponente wird ein ReadyComponent mit Status „ok“ oder „error“ und einer optionalen Fehlermeldung erstellt. Alle Ergebnisse werden in einem ReadyOut zusammengefasst.
•   Erweiterungen in backend/app/schemas.py: Neue Pydantic‑Modelle ReadyComponent und ReadyOut beschreiben die Struktur des Ready‑Responses. ReadyComponent enthält den Namen der Komponente, den Status und eine optionale message; ReadyOut liefert eine Liste von Komponenten.
•   main.py aktualisiert: Der Ready‑Router wird zusammen mit dem Health‑Router unter /api/v1 registriert, sodass die API jetzt über /api/v1/ready und /api/v1/health erreichbar ist.
•   Neue Dateien backend/app/settings.py, backend/app/db.py und backend/app/api/health.py wurden eingeführt, um eine lauffähige Minimalversion des Backends bereitzustellen. In späteren Blöcken folgen zusätzliche Modelle, CRUD‑Funktionen und weitere Router.
•   Anpassungen in backend/app/generator.py: Die LLM‑Routing‑Logik wurde erweitert.  Für die initiale Generierung wird weiterhin das llama3.1:70b‑Modell genutzt.  Tritt bei der Kommunikation mit diesem Modell ein Fehler auf, wechselt das System in Entwicklungsumgebungen (ENV_PROFILE ≠ prod) automatisch auf das llama3.1:8b‑Modell.  In Produktionsumgebungen greift es hingegen auf ein statisches Skelett zurück.  Bearbeitungen und Chat‑Funktionen nutzen weiterhin ausschließlich das 8B‑Modell.

Block 07 – Job‑Service und Export
•   Neues Modul: backend/app/api/jobs.py implementiert einen Job‑Router. Dieser stellt zwei Endpunkte bereit:
– POST /api/v1/jobs startet einen Job. Aktuell wird nur der Typ export unterstützt. Der Nutzer übermittelt eine Liste von artifact_ids und optional ein format. Das Backend legt einen neuen Job im jobs_store an, startet im Hintergrund einen Export und liefert die Job‑ID sowie den initialen Status zurück.
– GET /api/v1/jobs/{job_id} gibt den Status eines Jobs zurück. Neben status und progress wird – nach erfolgreichem Abschluss – der Name der erzeugten ZIP‑Datei ausgegeben. Bei Fehlern enthält die Antwort ein error‑Feld.
•   Neue Schemas: JobCreate, JobStatus und JobOut in backend/app/schemas.py. Diese Modelle beschreiben die Eingabe- und Ausgabestruktur der Job‑API und dienen dem in‑memory Job‑Store.
•   Job‑Implementierung: Das Export‑Back‑End erstellt für jede Artefakt‑ID eine einfache Textdatei mit Platzhalterinhalt und packt alle Dateien zu einem ZIP‑Archiv (Name = {job_id}.zip). Das Archiv wird im Verzeichnis EXPORT_DIR gespeichert. Fortschritt (progress) und Status werden laufend aktualisiert. Fehler führen zu status=failed und einem Eintrag im error‑Feld.
•   Erweiterungen in backend/app/api/__init__.py: Der neue jobs_router wird beim Erstellen des API‑Routers automatisch hinzugefügt.
•   Ergänzung in backend/app/schemas.py: Import von datetime und Definition der neuen Job‑Modelle. Das __all__‑Tuple wurde angepasst.
•   Erweiterungen in docs/TRUTH.md: Neuer Abschnitt „Jobs und Export (Block 07)“ beschreibt den Zweck des Job‑Services, die API‑Endpunkte und das Export‑Verfahren.

Block 08 – Export‑Download
•   Neues Modul: backend/app/api/export.py implementiert einen Router
für den Download von Export‑Jobs. Der Endpunkt GET /api/v1/exports/{job_id}
liefert die ZIP‑Datei eines abgeschlossenen Export‑Jobs, sofern
der Job den Status completed besitzt und eine Datei vorhanden ist.
•   backend/app/main.py aktualisiert: Der Export‑Router wird neben
den bestehenden Routern (Health, Projects, Artifacts, Open Points,
Chat, Ready, Jobs) unter /api/v1 registriert.
•   docs/TRUTH.md erweitert: Ein neuer Abschnitt „Download von
Exporten (Block 08)“ beschreibt den Download‑Endpunkt und dessen
Nutzung.

Block 09 – DOCX/PDF‑Export
•   Neue Abhängigkeiten: python-docx und reportlab werden der
Datei backend/requirements.txt hinzugefügt, um die
Erstellung von DOCX- und PDF-Dateien zu ermöglichen.
•   Erweiterungen in backend/app/api/jobs.py:
– Die Hintergrundfunktion _run_export_job erzeugt jetzt
Platzhalter-Dateien im Format txt, docx oder pdf.
Für docx wird python-docx genutzt, um eine einfache
Word-Datei mit einer Überschrift und einem Absatz zu
erstellen. Für pdf wird reportlab.platypus verwendet,
um ein PDF mit Titel und Fließtext zu generieren. Die
Generierung erfolgt nur, wenn die jeweiligen Bibliotheken
installiert sind; andernfalls schlägt der Job mit
status=failed fehl.
– Die Validierung im Job-Endpoint prüft nun, ob das
angegebene Format zu den erlaubten Werten txt, docx
oder pdf gehört. Bei einem nicht unterstützten Format
wird eine 400-Fehlerantwort ausgegeben.
•   Aktualisierte Schemas: Das Pydantic-Modell JobCreate
dokumentiert jetzt, dass format eines der drei erlaubten
Formate sein muss (txt, docx, pdf). Der
Description-Text und das Beispiel wurden entsprechend
angepasst.
•   Anpassung von docs/TRUTH.md: Ein neuer Abschnitt
„DOCX/PDF‑Export (Block 09)“ beschreibt die Erweiterung des
Export-Services um die Formate DOCX und PDF, erläutert den
Einsatz der Bibliotheken python-docx und reportlab und
weist auf die Formatvalidierung und Fehlerbehandlung hin.
•   Keine Änderungen an anderen Modulen: Die bestehende
Download-Logik aus Block 08 bleibt unverändert; sie liefert
weiterhin das erzeugte ZIP-Archiv, das nun auch DOCX- oder
PDF-Dateien enthalten kann.

Block 10 – Verbessertes Dokumentenlayout
•   Neues Modul backend/app/exporter.py wurde erstellt, das
sämtliche Export-Funktionen bündelt. Es lädt aktuelle
Artefakt-Versionen aus der Datenbank, generiert Dateien in
verschiedenen Formaten (txt, md, docx, pdf) und erstellt ein
ZIP-Archiv. Das Modul sorgt für sichere Dateinamen und
entfernt temporäre Dateien nach dem Export.
•   Die PDF-Erstellung verwendet nun reportlab.platypus mit
symmetrischen Seitenrändern von 50 pt links und rechts sowie
automatischem Zeilenumbruch. Markdown-Überschriften werden
in PDF-Heading-Stile übertragen, Listenpunkte werden mit einem
einheitlichen Aufzählungssymbol versehen, und leerzeilen
erzeugen Abstände im Dokument. Damit wird verhindert, dass
Text abgeschnitten wird oder am Rand klebt.
•   Die DOCX-Erzeugung erkennt Überschriften der Stufen 1–3 und
formatiert sie als Word-Heading (Heading 1–3). Numerierte
Zeilen werden als nummerierte Listen (List Number) in
Word angelegt, während Aufzählungen mit - oder * als
Bullet-Listen (List Bullet) umgesetzt werden. Normale
Zeilen werden als einfache Absätze geschrieben.
•   backend/app/api/jobs.py wurde hinsichtlich der
Dokumentation aktualisiert: Die Docstrings erklären nun alle
unterstützten Formate und das Zusammenspiel mit dem neuen
exporter-Modul. Die Job-Logik selbst bleibt unverändert.
•   docs/TRUTH.md wurde um einen neuen Abschnitt ergänzt,
der die verbesserten Layouts und das Verhalten des Exports
beschreibt (siehe „Dokumentenlayout und Export (Block 10)“).
•   Es wurden keine neuen Abhängigkeiten hinzugefügt; die
Bibliotheken python-docx und reportlab waren bereits
in Block 09 integriert. Die Verbesserungen beruhen auf
bestehender Funktionalität.
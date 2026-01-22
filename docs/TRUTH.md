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

BSI‑Baustein‑Bewertung (Block 11)
In Block 11 wurde ein neues Modul eingeführt, das die Bewertung von
einzelnen BSI‑Grundschutz‑Bausteinen ermöglicht. Über den Endpunkt
POST /api/v1/projects/{project_id}/bsi/generate können Nutzer eine
Liste von Baustein‑Codes (z. B. SYS.2.1 oder APP.1.2) an das
Backend übergeben. Für jedes Modul legt das System eine initiale
Bewertung mit dem Status offen an und erzeugt eine offene Frage,
die den Umsetzungsstand des Bausteins erfasst. Alle Bewertungen
werden in einem speicherresidenten Store gespeichert. Weitere
Endpunkte erlauben das Auflisten aller Bausteine eines Projekts
(GET /api/v1/projects/{project_id}/bsi), das Abrufen einer
einzelnen Bewertung (GET /api/v1/projects/{project_id}/bsi/{module_code})
sowie das Aktualisieren des Status oder Kommentars eines Bausteins
(PUT /api/v1/projects/{project_id}/bsi/{module_code}). Dieses
Modul bildet die Grundlage für eine strukturierte Soll‑Ist‑Analyse
der BSI‑Bausteine und erleichtert die Erfassung offener Punkte.

BSI‑Baustein‑Analyse (Block 12)
In Block 12 wird die BSI‑Baustein‑Bewertung um eine KI‑gestützte
Analyse ergänzt. Über den neuen Endpunkt
POST /api/v1/projects/{project_id}/bsi/analyze kann eine Liste
von BSI‑Baustein‑Codes zur automatischen Soll‑Ist‑Bewertung
übergeben werden. Die Analyse nutzt ausschließlich die beim
Projekt hochgeladenen Quellen (TXT, MD oder DOCX) und durchsucht
deren Inhalte nach Hinweisen für die Erfüllung der jeweiligen
Maßnahmen. Die zugehörigen Maßnahmen (z. B. SYS.2.1.A1 für
Patchmanagement) sind exemplarisch im Code hinterlegt und sollen in
einer späteren Version aus offiziellen Quellen geladen werden.
Für jede Maßnahme wird ein Status ermittelt:

•   erfüllt – wenn die Anforderung vollständig in den
Projektquellen nachgewiesen wird.
•   teilweise – wenn einige, aber nicht alle Schlüsselwörter
gefunden werden.
•   offen – wenn kein Hinweis gefunden wird; in diesem Fall
wird eine konkrete offene Frage formuliert, die als Open Point
aufgeführt wird.

Das Ergebnis der Analyse ist ein neues Schema
BsiEvaluationDetailOut, das den aggregierten Status pro
Baustein (erfüllt, teilweise oder offen), die Liste der
Einzelmaßnahmen und deren Nachweise sowie alle offenen Fragen
enthält. Die KI‑Analyse ändert nichts an den manuellen
Bewertungen (Block 11); sie liefert zusätzliche Informationen,
die beim späteren Ausfüllen der Offenen Punkte helfen können. Die
Analyse greift niemals auf externe Daten oder das Internet zu,
sondern wertet nur die hochgeladenen Projektquellen aus. Für
nicht unterstützte Dateitypen (z. B. PDF) wird aktuell kein Text
extrahiert; diese Dateien fließen erst dann in die Analyse ein,
wenn ein entsprechender Parser implementiert wurde.

Hinweis zu unbekannten Bausteinen: Wenn ein Bausteincode in
der aktuellen Implementierung nicht im internen Maßnahmenkatalog
(MODULE_MEASURES) hinterlegt ist, wird der Baustein automatisch
mit dem Status offen bewertet. In diesem Fall wird eine
entsprechende offene Frage (z. B. Baustein SYS.3.2.2 ist nicht im Katalog definiert. Bitte ergänzen Sie die Maßnahmen.) als Open
Point zurückgegeben. Dieses Verhalten verhindert fälschlicherweise
den Status erfüllt bei nicht definierten Bausteinen und macht
transparent, dass eine Definition der Maßnahmen fehlt.

Projektquellen‑Upload (Block 13)
Um die KI‑Analyse mit realen Inhalten zu versorgen, wurde in Block 13
ein Upload‑Mechanismus für Projektquellen eingeführt. Über den
neuen Endpunkt POST /api/v1/projects/{project_id}/sources/upload
können Nutzer eine oder mehrere Dateien (TXT, MD, DOCX oder PDF)
für ein Projekt hochladen. Die hochgeladenen Dateien werden im
Verzeichnis UPLOAD_DIR/<project_id> gespeichert, das per
Umgebungsvariable konfiguriert ist (Standard: /data/uploads).

Für jede Datei wird eine einfache Textextraktion durchgeführt, um
Inhalte für die BSI‑Analyse verfügbar zu machen:
• TXT/MD – der gesamte Text wird direkt aus dem Upload gelesen.
• DOCX – der Text wird mithilfe der Bibliothek
python‑docx extrahiert.
• PDF – die Datei wird gespeichert, die Extraktion ist jedoch
noch nicht implementiert (Status = partial). Diese Dateien
fließen in die Analyse ein, sobald ein Parser ergänzt wird.
Die Ergebnisse der Extraktion werden als SourceUploadResponse
zurückgegeben, das für jede Datei eine ID, den Dateinamen,
den Extraktionsstatus, eine optionale Fehlermeldung und die Länge
des extrahierten Textes enthält. Die Metadaten aller Quellen
werden in einem speicherresidenten sources_store abgelegt.

Der Upload‑Endpoint bildet die Grundlage für spätere Blöcke, in
denen die KI automatisch Text aus Projektquellen verarbeiten kann.
Er ergänzt das bestehende Upload‑Verhalten für Chat‑Anhänge und
Open‑Point‑Anhänge und stellt sicher, dass alle relevanten
Dokumente an einem konsistenten Ort gespeichert sind.

Artefakt‑Bearbeitung (Block 14)

In Block 14 wurde die Möglichkeit ergänzt, bestehende Artefakte mit Hilfe
der KI zu bearbeiten. Nutzer können eine Bearbeitungsanweisung senden, um
ein Dokument umzuschreiben, zu kürzen, zu verlängern oder anderweitig
anzupassen.
•	Endpunkt: POST /api/v1/projects/{project_id}/artifacts/{artifact_id}/edit
– Erwartet ein JSON‐Objekt mit dem Feld instructions, das eine klare
Anweisung zur Überarbeitung enthält. Das Backend ruft das kleine
LLM‑Modell (llama3.1:8b) auf, übergibt die Anweisung zusammen mit dem
aktuellen Markdown‐Inhalt des Dokuments und erhält den überarbeiteten
Text zurück.
•	Versionierung: Die Bearbeitung erzeugt immer eine neue Version des
Artefakts, wird aber nicht automatisch als aktuelle Version gesetzt.
Nutzer können über den bestehenden Endpunkt zum Setzen der aktuellen
Version entscheiden, ob sie die Änderungen übernehmen möchten.
•	Diff: Die Antwort enthält einen Unified‑Diff (im Stil von
difflib.unified_diff), der die Unterschiede zwischen der bisherigen
und der neuen Version darstellt. So kann der Nutzer die Änderungen
nachvollziehen, bevor er sie übernimmt.
•	Fallback: Sollte bei der Bearbeitung ein Fehler auftreten (z. B. LLM
nicht erreichbar), bleibt der Inhalt unverändert und eine Fehlermeldung
wird zurückgegeben.

Diese Erweiterung ermöglicht iteratives Arbeiten am Dokument, ohne die
Ausgangsversion zu verlieren. Die Bearbeitung ist auf das kleine Modell
beschränkt; der Einsatz des 70B‑Modells ist weiterhin ausschließlich
für die initiale Generierung reserviert.

LLM‑Jobs, Generierung und Bearbeitung (Block 15)

In Block 15 wurde der Job‑Service erweitert und die Generierung sowie
Bearbeitung von Artefakten verbessert. Ziel ist es, langlaufende
Operationen wie LLM‑Generierung und ‑Bearbeitung als asynchrone Jobs
über den bestehenden Job‑Service auszuführen und gleichzeitig die
Qualität der Dokumente zu erhöhen.
•	Job‑Typen: Der Endpunkt POST /api/v1/jobs unterstützt jetzt drei
Typen:
•	export – unverändert, erstellt ZIP‑Archive für Artefakte.
•	generate – generiert ein oder mehrere Artefakte für ein Projekt. Es
sind project_id und types (Liste der Artefakt‑Typen) anzugeben.
Das System ruft für jeden Typ das LLM auf und erstellt das Artefakt
mit Version 1 direkt mit dem generierten Inhalt. Existiert das
Artefakt bereits, wird eine neue Version erstellt und als aktuelle
Version markiert. Offene Fragen werden erkannt und als Open Points
gespeichert.
•	edit – bearbeitet ein vorhandenes Artefakt. Es sind project_id,
artifact_id und instructions anzugeben. Das LLM (8B) erhält
Anweisung und den aktuellen Inhalt, entfernt keine
OFFENE_FRAGE‑Zeilen, behält die Struktur bei und fügt alle
offenen Fragen unter einer eigenen Überschrift „Offene Punkte“ am
Ende ein. Neue Fakten dürfen nicht erfunden werden. Die Bearbeitung
erzeugt eine neue Version, die nicht automatisch als aktuelle
Version gesetzt wird. Der Job liefert die neue Versionsnummer und
einen Unified‑Diff zurück.
•	Versionierung bei Generierung: Wenn ein Artefakt zum ersten Mal
generiert wird, speichert das System den generierten Inhalt direkt in
Version 1. Die zuvor verwendete leere Version 1 entfällt damit. Bei
erneuter Generierung wird wie gewohnt eine neue Version erstellt
(Version 2, 3, …) und als aktuelle Version gesetzt. Dieses Verhalten
stellt sicher, dass es keine leere Vorgängerversion mehr gibt.
•	Erweiterte Open‑Point‑Erkennung: Bei der Generierung werden jetzt
auch Zeilen erkannt, die mit „- OFFENE_FRAGE:“ beginnen. Diese
Varianten treten in den Vorlagen als Aufzählungspunkte auf. Sie
werden aus dem generierten Inhalt entfernt und als offene Punkte
persistiert.
•	Bearbeitungs‑Prompt: Das Editor‑Prompt wurde angepasst, damit das
kleine Modell OFFENE_FRAGE‑Zeilen nicht entfernt, die Struktur
beibehält und keine neuen Fakten erfindet. Zusätzlich wird am Ende
automatisch eine Liste aller offenen Fragen unter der Überschrift
„## Offene Punkte“ eingefügt.

Diese Erweiterungen sorgen dafür, dass Generierungen und Bearbeitungen
skalierbar über Jobs ausgeführt werden können und die entstehenden
Dokumente qualitativ hochwertig bleiben. Nutzer können den
Fortschritt und das Ergebnis eines Jobs über GET /api/v1/jobs/{job_id}
einsehen. Bei „generate“ liefert das Ergebnis die IDs der erzeugten
Artefakte, ihre Versionsnummern und die IDs der erzeugten offenen
Punkte. Bei „edit“ liefert das Ergebnis die neue Versionsnummer und den
Unified‑Diff.

Apply/Reject und Änderungszusammenfassung (Block 16)

Block 16 erweitert das Versionsmanagement um explizites Übernehmen
(Apply) und Verwerfen (Reject) neuer Versionen sowie um eine
Zusammenfassung der Änderungen zwischen Versionen.
•	Version‑Zusammenfassung: Über den Endpunkt
GET /api/v1/projects/{project_id}/artifacts/{artifact_id}/versions/{version}/summary
können Nutzer sich vor dem Übernehmen einen Überblick verschaffen. Die
Antwort liefert added_count (hinzugefügte Zeilen), removed_count
(entfernte Zeilen) und changed_sections (Liste geänderter
Markdown‑Abschnitte). Vergleichsbasis ist jeweils die Vorgängerversion
oder ein leeres Dokument bei Version 1.
•	Apply: Mit
POST /api/v1/projects/{project_id}/artifacts/{artifact_id}/versions/{version}/apply
wird eine Version als aktuelle Version gesetzt. Dies ersetzt
bestehende Inhalte nicht still, sondern erfolgt explizit. Wenn die
Version bereits aktuell ist, passiert nichts.
•	Reject: Mit
POST /api/v1/projects/{project_id}/artifacts/{artifact_id}/versions/{version}/reject
kann eine Version verworfen werden. Die Version bleibt in der
Historie erhalten, wird aber nicht zur aktuellen Version gemacht. Das
Verwerfen der aktuellen Version ist nicht erlaubt. Eine echte
Löschfunktion ist für spätere Blöcke vorgesehen.

Diese Erweiterung schließt den Versionslebenszyklus: Generierung
erstellt eine neue Version, die über die Bearbeitungsendpunkte
angepasst werden kann. Der Nutzer entscheidet anschließend anhand
einer diff‑basierten Zusammenfassung, ob die Änderungen übernommen
oder verworfen werden sollen.

Projektquellen‑Persistenz & Limits (Block 17)

In Block 17 wird die Verwaltung von Projektquellen (Uploads) deutlich
verbessert und der Summary‑Endpunkt aus Block 16 korrigiert.
•	Persistente Quellen: Bisher wurden hochgeladene Dateien nur im
Verzeichnis UPLOAD_DIR/<project_id> gespeichert und in einem
speicherresidenten sources_store verwaltet. Ab Block 17 werden
alle Metadaten zu den Quellen in der Datenbanktabelle
sources (SourceDocument) persistiert. Diese Tabelle
enthält neben Datei‑ID, Name, Größe und Speicherdatum jetzt auch
neue Felder zur Textextraktion:
•	extraction_status –  ok, partial oder error.
•	extraction_reason –  kurze Fehlerbeschreibung oder Grund für
einen partiellen Erfolg.
•	extracted_text_len –  Anzahl der extrahierten Zeichen.
Diese Werte werden beim Upload gesetzt. Für TXT/MD werden die
Inhalte direkt eingelesen, für DOCX über python‑docx, bei PDF
wird ab sofort mithilfe der Bibliothek PyPDF2 der Text
extrahiert (falls die Bibliothek verfügbar ist). Schlägt die
Extraktion fehl oder ist die Bibliothek nicht installiert, wird
der Status error gesetzt und eine Fehlermeldung zurückgegeben.
Leere Texte führen zu partial mit dem Grund „No text
extracted“. Die In‑Memory‑Struktur sources_store
bleibt vorerst bestehen, um die Kompatibilität zu älteren Modulen
sicherzustellen; sie wird parallel zur Datenbank aktualisiert.
•	Upload‑Limits: Es gelten jetzt feste Grenzwerte für
Projekt‑Uploads, die über Umgebungsvariablen steuerbar sind:
•	MAX_UPLOAD_BYTES (Standard 30 MB) – maximale Größe einer
einzelnen Datei. Überschreiten Dateien diesen Wert, bricht der
Upload mit HTTP 413 ab.
•	MAX_SOURCES_PER_PROJECT (Standard 50) – maximale Anzahl von
Quellen pro Projekt. Werden mehr Dateien hochgeladen, als
erlaubt sind (inklusive bereits gespeicherter Quellen), wird
der Upload mit HTTP 400 abgelehnt.
•	Unterstützte Dateitypen sind unverändert .txt, .md, .docx und
.pdf. Andere Endungen führen zu HTTP 400.
•	Summary‑Fix: Der Endpunkt
GET /api/v1/projects/{project_id}/artifacts/{artifact_id}/versions/{version}/summary
liefert ab Block 17 zwei wesentliche Verbesserungen:
•	Leere Vorgängerversion – für Version 1 wird immer
eine leere Änderungsliste zurückgegeben (added_count = 0,
removed_count = 0, changed_sections = []), weil es keinen
Vergleichsstand gibt. Die früheren Zeilenzählungen für Version 1
sind damit behoben.
•	Ignorieren von Formatänderungen – bei der Berechnung des
Diffs werden nun vorab Leerzeilen und trailing spaces
normalisiert. Mehrere aufeinanderfolgende Leerzeilen werden auf
eine reduziert. Dadurch werden reine Formatänderungen (z. B.
unterschiedliche Anzahl leerer Zeilen) nicht mehr als inhaltliche
Änderungen gezählt. Nur echte Textänderungen wirken sich auf
added_count/removed_count und changed_sections aus.

Diese Anpassungen stellen sicher, dass hochgeladene Quellen
nachvollziehbar gespeichert und später auch versioniert oder ersetzt
werden können. Durch die Limits wird verhindert, dass einzelne
Projekte den Speicher überlasten. Die Korrektur des Summary‑Endpoints
erhöht die Transparenz bei der Versionsverwaltung.

BSI‑Kataloge (Block 18)

Mit Block 18 wird das FaSiKo‑Backend um einen vollständigen BSI‑Baustein‑Katalog
erweitert, der nicht mehr statisch im Code hinterlegt ist. Nutzer können
offizielle BSI‑PDFs (z. B. das IT‑Grundschutz‑Kompendium) hochladen; aus
jeder hochgeladenen Datei wird ein neuer Katalog mit eigener Version erzeugt.
Die PDF wird im Verzeichnis BSI_CATALOG_DIR gespeichert und anschließend
verarbeitet:
•	Textextraktion: Der Inhalt des PDFs wird mithilfe von PyPDF2
extrahiert und grob normalisiert (Silbentrennung wird entfernt). Ist
kein PDF‑Parser vorhanden oder kann kein Text ausgelesen werden,
wird der Upload als error markiert.
•	Modul‑Erkennung: Aus dem normalisierten Text werden alle
Bausteine erkannt, deren Zeilen mit einem Modulkürzel wie
SYS.3.2.2 beginnen, gefolgt von einem Titel. Jede gefundene Zeile
erzeugt einen neuen BsiModule‑Datensatz mit Code und Titel.
•	Anforderungen: Unterhalb eines Moduls werden Anforderungen erkannt,
die entweder mit A und einer Nummer (z. B. A1, A 2) beginnen oder
bereits das vollständige Modulpräfix enthalten (z. B. OPS.1.1.2.A2).
Für jede erkannte Zeile wird aus Modulcode und Nummer sowie dem Titel
inklusive Klassifizierung (z. B. „Regelungen zum Umgang mit
eingebetteten Systemen (B)“) ein vollständiger BSI‑Code im Format
SYS.4.3.A1 Regelungen zum Umgang mit eingebetteten Systemen (B)
gebildet und als req_id gespeichert. Der Parser durchsucht die
Anforderungszeile nach der ersten vorkommenden Klassifizierung in
Klammern (B), (S) oder (H) und trennt die Kennung vom
Beschreibungstext. Alles bis zu dieser Klammer bildet die Kennung
inklusive Titel und Klassifizierung; der danach folgende normative
Text wird in der Spalte description gespeichert. Die Beschreibung
kann sich über mehrere Zeilen erstrecken und wird beim Parsen zu
einem Fließtext zusammengeführt. Jede Anforderung wird als
BsiRequirement persistiert. Sollten im PDF mehrere Zeilen mit
identischem Modulcode vorkommen (z. B. IND.2.3 Sensoren und Aktoren und IND.2.3 Sensoren und Aktoren R2 IT‑System), so wird
das Modul nur einmal angelegt, und die Anforderungen aller
Vorkommen werden zusammengeführt.

Die so extrahierten Daten werden persistiert: Die neuen Tabellen
bsi_catalogs, bsi_modules und bsi_requirements halten Kataloge,
Bausteine und Anforderungen. Pro Upload wird die Versionsnummer des
Katalogs automatisch erhöht. Über eine neue API können Kataloge
aufgelistet und die enthaltenen Module sowie deren Anforderungen
abgerufen werden.

Dieser Katalog bildet die Grundlage für spätere KI‑Analysen. Die
Verarbeitung erfolgt asynchron im Upload‑Endpunkt, sodass
Fehler oder unvollständige Extraktion mit einem Status (ok,
partial oder error) zurückgemeldet werden.

Nachträgliche Parser‑Verbesserung

Beim Einsatz des ersten Parsers zeigte sich, dass viele Anforderungen im
IT‑Grundschutz‑Kompendium nicht mit einer reinen A‑Kennung beginnen,
sondern das Modulpräfix enthalten (z. B. SYS.3.2.2.A1). Um diese
Fälle korrekt zu verarbeiten, erlaubt der Parser nun auch Zeilen mit
vorangestelltem Modulkürzel und Punkt vor der Anforderungsnummer.
Zudem werden Beschreibungstexte, die sich über mehrere Zeilen erstrecken,
auf eine Zeile zusammengeführt. Diese Verbesserung behebt ein Problem,
bei dem die API zum Abrufen der Anforderungen eine leere Liste zurückgab.

Weitere Optimierungen

Bei der weiteren Nutzung des Katalog‑Uploads wurden zusätzliche
Verbesserungen vorgenommen:
•	Deduplication von Modulen: Einige BSI‑PDFs enthalten denselben
Baustein mehrfach, beispielsweise IND.2.3 Sensoren und Aktoren und
IND.2.3 Sensoren und Aktoren R2 IT‑System. Der Parser führt solche
Duplikate nun zu einem Modul zusammen, sodass jeder Modulcode nur
einmal in der Datenbank vorkommt.
•	Längere Anforderungskennungen: Da req_id den vollständigen
Modulcode inklusive Titel und Klassifizierung enthält, kann dieses
Feld erheblich länger werden als die ursprünglichen 50 Zeichen.
Zunächst wurde die Spaltenlänge schrittweise erhöht (Migration
0004_alter_req_id_length auf 256 Zeichen und
0005_expand_bsi_req_id_length auf 512 Zeichen). Es zeigte sich
jedoch, dass einige Anforderungen gar keine Klassifizierung besitzen
oder besonders lange Titel haben. Um unnötige Upload‑Fehler zu
vermeiden, setzt die Migration 0006_change_req_id_to_text den
Datentyp der Spalte req_id auf TEXT (unbegrenzte Länge).

BSI‑Katalog‑Validierung und Anforderungsdetails (Block 19)

In Block 19 wurde der BSI‑Katalog‑Mechanismus weiterentwickelt, um die
aus den PDFs extrahierten Anforderungen präziser abzubilden und eine
grundlegende Validierung zu ermöglichen. Die wichtigsten Erweiterungen
im Überblick:
•	Zusätzliche Felder pro Anforderung: Neben der Kennung req_id
werden nun folgende Felder gespeichert:
•	title – der reine Titel der Maßnahme ohne BSI‑Code und ohne
Klassifizierung.
•	classification – Klassifizierung der Maßnahme (B = Basis,
S = Standard, H = Hoch). Fehlende Klassifizierungen
bleiben null.
•	is_obsolete – ein Flag, das auf true gesetzt wird, wenn der
Titel die Zeichenfolge „ENTFALLEN“ (Groß/Kleinschreibung
ignoriert) enthält. Damit können entfallene Maßnahmen im UI
gesondert markiert werden.
•	description – der normative Beschreibungs­text der Maßnahme.
•	Parser‑Verbesserungen: Der Parser sucht nun explizit nach der
ersten Klassifizierung in Klammern und trennt sie mitsamt Titel vom
nachfolgenden normativen Text. Wird keine Klassifizierung gefunden,
wird die gesamte Zeile als Titel übernommen und der normative Text
bleibt zunächst leer; nachfolgende Zeilen werden an den
Beschreibungstext angehängt. Damit werden Kennung, Titel,
Klassifizierung und Beschreibung korrekt getrennt und gespeichert.
•	Deduplication und Konsistenz: Wie bereits in Block 18 werden
doppelte Module zusammengeführt. In Block 19 wird zusätzlich
sichergestellt, dass Anforderungen eindeutig pro Modul identifiziert
werden. Die neuen Felder erlauben später eine qualifizierte
Validierung (z. B. Plausibilitätsprüfungen oder automatisierte
Soll‑Ist‑Auswertungen).
•	Migrationen: Die neue Alembic‑Revision
0007_add_req_extras fügt die Spalten
title, classification und is_obsolete zur Tabelle
bsi_requirements hinzu. Die Spalte req_id bleibt vom Typ
TEXT (siehe 0006_change_req_id_to_text).

Mit diesen Anpassungen ist der BSI‑Katalog bereit für weitere
Automatisierungen, wie etwa die Bewertung der Anforderungen anhand
der Projektquellen.

Überarbeitung der PDF‑Extraktion (Block 20)

Nach weiteren Tests und Rückmeldungen wurde die PDF‑Extraktion erneut
überarbeitet. Wir setzen wieder auf pdfplumber als
primäres Werkzeug, da es eine layout‑bewusste Extraktion ermöglicht,
die Zeilenumbrüche, Einrückungen und Listen aus dem PDF besser
rekonstruiert ￼. Um die Wortabstände zu
verbessern, werden bei page.extract_text spezifische Parameter
(x_tolerance=2, line_overlap=0.5) genutzt. Sollte pdfplumber nicht
installiert sein oder fehlschlagen, greift das System automatisch
auf PyPDF2 als Fallback zurück.

Die wichtigsten Anpassungen im Zuge dieser Überarbeitung:
•	Reaktivierung von pdfplumber: Das Paket pdfplumber wird
erneut verwendet und in requirements.txt aufgenommen. _extract_pdf_text
versucht zunächst, den Text mit pdfplumber zu extrahieren; nur wenn
dies fehlschlägt, wird auf PyPDF2 zurückgegriffen.
•	Parameter für Wortabstände: Beim Aufruf von page.extract_text
werden x_tolerance=2 und line_overlap=0.5 gesetzt. Diese
Parameter sorgen laut pdfplumber‑Dokumentation dafür, dass Wörter
mit geringen Abständen zusammengeführt und Zeilenüberlappungen
besser erkannt werden ￼.
•	Titelerkennung und Untermodul‑Logik: Die Module werden weiterhin
anhand ihrer Codes erkannt; Bullet‑Zeichen und tiefere Codes (z. B.
DER.2.1) werden als neue Module interpretiert. Titel werden am
frühesten Auftreten eines Bullets, eines weiteren Modulcodes oder
eines Klassifikationszusatzes (z. B. R3 Informationsverbund) geschnitten.
•	Bereinigungsheuristiken: Die Funktion _cleanup_description
entfernt weiterhin Silbentrennungen, fügt Leerzeichen nach Satzzeichen
ein und trennt zusammengeklebte Groß-/Kleinbuchstaben. Zusätzlich wird
eine vorsichtige Präpositionsheuristik verwendet, um fehlende
Leerzeichen vor häufigen Präpositionen nachträglich einzufügen.

Mit dieser Anpassung kombinieren wir die Vorteile von pdfplumber (Layout
und Listen) mit fallback‑Sicherheit durch PyPDF2. Wenn weiterhin
Worttrennungsprobleme auftreten, können manuelle Nachbearbeitungen oder
zukünftige Parser‑Updates helfen, die Qualität weiter zu verbessern.

LLM‑Text‑Normalisierung (Block 21)

Die PDF‑Extraktion liefert trotz der verbesserten Parser oft weiterhin
Texte mit Silbentrennungen, fehlenden Leerzeichen oder Zeilenumbrüchen.
Um diese Artefakte zu beheben, wurde in Block 21 ein deterministischer
LLM‑basierter Text‑Normalizer eingeführt. Die Normalisierung korrigiert
ausschließlich Worttrennungen, Leerzeichen, Zeilenumbrüche und andere
Formatierungsfehler, ohne irgendwelche inhaltlichen Änderungen
vorzunehmen. Weder werden neue Sätze erzeugt noch bestehende Aussagen
entfernt. Aufzählungszeichen (Bullets) bleiben als separate Zeilen
erhalten.

Die wichtigsten Aspekte der Normalisierung:
•	Rohdatenpersistenz – Jede Anforderung speichert nun zusätzlich
die Felder raw_title und raw_description mit dem
unveränderten Text aus der PDF‑Extraktion. Die bestehenden Felder
title und description enthalten nach der Normalisierung die
korrigierte Fassung. Alte Kataloge ohne diese Rohdaten bleiben
weiterhin gültig; die Spalten können None sein.
•	8B‑Modell – Die Normalisierung verwendet ausschließlich das
kleine LLM‑Modell (8‑B‑Variante) über die Ollama‑API. Das 70B‑Modell
bleibt weiterhin nur für die initiale FaSiKo‑Generierung reserviert.
Der Prompt weist das Modell strikt an, nur Formatierungsfehler zu
korrigieren (Worttrennung, Grammatik, Leerzeichen) und keine
neuen Inhalte hinzuzufügen. Fachbegriffe, Codes und Norm‑
Begriffe (MUSS/SOLL/SOLLTE) werden unverändert gelassen.
Hinweis zu Modellbezeichnungen – Ab Mitte 2025 hat Ollama
die Modellbezeichnungen geändert. Die zuvor verwendeten Namen
llama3.1:8b und llama3.1:70b existieren nicht mehr in der
öffentlichen Bibliothek und führen zu 404 Not Found‑Fehlern. Die
Anwendung verwendet daher standardmäßig die Varianten
llama3:8b und llama3:70b. Diese Modelle sind
identisch in der Funktion, lediglich die Versionskennzeichnung wurde
angepasst. Für individuelle Umgebungen können die Modellnamen über
die Umgebungsvariablen OLLAMA_CHAT_MODEL, MODEL_GENERAL_8B
und MODEL_FASIKO_CREATE_70B angepasst werden.
Hinweis zum API‑Endpoint – In neueren Ollama‑Versionen wurde der
Endpunkt /api/chat entfernt und durch die OpenAI‑kompatiblen
Routen (z. B. /v1/chat/completions) ersetzt. Einige Versionen
bieten stattdessen /api/generate für einfache Prompt‑basierte
Aufrufe. Um dennoch eine stabile Normalisierung zu gewährleisten,
versucht das Backend zuerst den klassischen Chat‑Endpoint
/api/chat. Schlägt dieser mit 404 Not Found fehl, wird
/api/generate genutzt. Sollte auch dieser Endpunkt nicht
verfügbar sein, fällt das System automatisch auf die
OpenAI‑kompatible Route /v1/chat/completions zurück. Dieser
mehrstufige Fallback benötigt keine Benutzerinteraktion und stellt
sicher, dass die Normalisierung mit allen unterstützten
Ollama‑Versionen funktioniert.
•	Asynchroner Job – Die Normalisierung erfolgt als
Hintergrundjob (Typ normalize) über den bestehenden
Job‑Service. Ein neuer Endpunkt
POST /api/v1/bsi/catalogs/{catalog_id}/normalize
startet den Job. Optional kann der module_code Parameter
genutzt werden, um nur die Anforderungen eines einzelnen Moduls zu
normalisieren. Der Fortschritt und der Status des Jobs können über
GET /api/v1/jobs/{id} verfolgt werden.
•	Vorschau – Ein weiterer Endpunkt
GET /api/v1/bsi/catalogs/{catalog_id}/normalize/preview bietet
eine Vorschau der Normalisierung. Er gibt für die ersten limit
Anforderungen (standardmäßig 3) eines Katalogs oder Moduls jeweils
den Rohtext und die normalisierte Fassung zurück, ohne sie zu
speichern. Damit können Nutzer das Ergebnis prüfen, bevor sie den
Job starten.
•	Fehlerbehandlung – Schlägt der LLM‑Aufruf während der
Normalisierung fehl, hängt das Verhalten vom Profil ab: In der
Entwicklungsumgebung (ENV_PROFILE != ‘prod’) wird der
unveränderte Rohtext übernommen und der Fehler im Job‑Status
vermerkt. In der Produktion bricht der Job mit status=failed
ab und liefert eine verständliche Fehlermeldung. Die bisherige
Klassifizierung (B/S/H) und das is_obsolete‑Flag bleiben
unberührt.

Die Normalisierung verbessert die Lesbarkeit der extrahierten
Anforderungen deutlich und bereitet sie für weitere
Verarbeitungsschritte, wie die KI‑Analyse oder das Generieren von
Dokumenten, vor. Die Implementierung umfasst neue Spalten in der
Datenbank, einen Normalisierungs‑Service im Backend sowie
entsprechende API‑Endpunkte und Dokumentation.

Seit dem Block 21‑Fix wird die Normalisierung automatisch nach dem
Hochladen eines Katalogs ausgelöst. Der Upload‑Endpunkt startet für
jeden erfolgreich gespeicherten Katalog einen Normalisierungsjob im
Hintergrund und liefert die Job‑ID im Feld normalize_job_id der
Upload‑Antwort zurück. Dies ermöglicht es der Benutzeroberfläche, den
Fortschritt ohne zusätzliche Interaktion zu überwachen. Der manuelle
Normalisierungsendpunkt bleibt für erneute oder gezielte
Normalisierungen weiterhin verfügbar.

Gemeinsamer LLM‑Client und Endpunkt‑Fallback (Block 21‑Fix)

In neueren Ollama‑Versionen wurden die bisher genutzten Chat‑ und
Generate‑Endpoints verändert. Um sicherzustellen, dass alle
LLM‑gestützten Funktionen – Chat, Dokumentenbearbeitung,
Artefakt‑Generierung und die Normalisierung – weiterhin funktionieren,
wurde ein zentraler LLM‑Client (backend/app/llm_client.py)
eingeführt. Dieser Client kapselt die Kommunikation mit dem
Ollama‑Server und versucht automatisch nacheinander die folgenden
HTTP‑Routen:
1.	/api/chat – klassischer Chat‑Endpoint, geeignet für
mehrteilige Unterhaltungen. Einige ältere Ollama‑Versionen
unterstützen ausschließlich diesen Pfad.
2.	/api/generate – einfacher Generate‑Endpoint, der einen
Prompt vervollständigt. Dieser Endpunkt wird verwendet, wenn
/api/chat nicht vorhanden ist.
3.	/v1/chat/completions – OpenAI‑kompatibler Endpoint, der
seit 2025 von Ollama bereitgestellt wird. Er ist Bestandteil
einer neuen API‑Struktur und entspricht weitgehend dem
OpenAI‑Chatformat.

Der Client bereitet die Nutzdaten entsprechend der jeweiligen
Schnittstelle auf und extrahiert die Antwort aus dem jeweiligen
Antwortformat. Kann keiner der Endpoints erreicht werden oder liefert
keiner eine Antwort, wird eine Exception ausgelöst. Alle Module, die
das LLM nutzen – insbesondere chat.py, generator.py,
ready.py und normalizer.py – verwenden nun den
gemeinsamen Client. Dadurch werden separate Fehlerbehandlungen und
harte Endpunktadressen im Code vermieden. Der Ready‑Endpoint
prüft die Erreichbarkeit der Modelle nun ebenfalls über diesen Client.

Dieser Umbau stellt sicher, dass Chat‑Funktionen, Websearch‑Chat,
Bearbeitung, Normalisierung und Modell‑Checks weiterhin mit allen
Ollama‑Versionen funktionieren, ohne dass der Nutzer Endpunkte
manuell auswählen oder anpassen muss.

Verbesserte Normalisierung und DEV/PROD‑Modus (Block 22)

In Block 22 wurde der Text‑Normalizer verfeinert und an unterschiedliche
Umgebungsprofile angepasst. Die Kernidee bleibt unverändert: Der
Normalizer repariert weiterhin ausschließlich Formatierungsfehler
in den aus PDF‑Katalogen extrahierten Anforderungstexten (Titel und
Beschreibung). Neu ist jedoch, dass das Verhalten nun zwischen
Entwicklungs‑ und Produktionsumgebung unterscheidet und zusätzliche
Heuristiken einsetzt, um Artefakte zu erkennen und zu entfernen.

DEV‑Modus (ENV_PROFILE ≠ prod): In Entwicklungsumgebungen
wird jede Anforderung über das 8B‑Modell und anschließend mit
deterministischen Heuristiken bereinigt. Das Ergebnis wird nicht
mehr in die Datenbank geschrieben. Stattdessen liefert der
Hintergrundjob ein Vorschaudokument zurück (result_data), das
für jede Anforderung den Rohtext, das LLM‑Ergebnis, den finalen Text
und eine Reihe von Flags enthält. Diese Flags zeigen an, ob das LLM
aufgerufen wurde (llm_used), ob sich der Text dadurch verändert hat
(llm_changed), ob Heuristiken angewendet wurden (heuristic_used)
sowie ob Artefakte vor und nach der Bereinigung vorhanden waren
(artifact_before, artifact_after). Zusätzlich gibt eine
Summary‑Struktur im Preview an, für wie viele Anforderungen das LLM
genutzt wurde, wie oft Änderungen erfolgten, wie häufig
Heuristiken eingriffen und wie viele Artefakte nach der Reinigung
verblieben. Wenn nach der Bereinigung noch Artefakte gefunden werden,
wird der Job zwar als abgeschlossen markiert, enthält aber im Feld
error eine Warnung (z. B. „WARN: Normalization incomplete for
5/120 requirements; Artefakte verbleiben.“). Somit gibt es
im DEV‑Modus keine „stillen Erfolge“ mehr – jeder unvollständig
bereinigte Text wird transparent angezeigt.

PROD‑Modus (ENV_PROFILE == prod): In Produktionsumgebungen
persistiert der Normalizer weiterhin die bereinigten Texte. Rohdaten
(raw_title und raw_description) werden nur gesetzt, wenn sie noch
nicht vorhanden sind. Treten beim LLM‑Aufruf Fehler auf, bricht der
Job ab (status = failed) und liefert eine verständliche
Fehlermeldung zurück. In prod werden keine Heuristik‑Warnungen
geliefert, weil nur vollständig bereinigte Texte gespeichert werden.

Heuristiken und Artefakterkennung: Zusätzlich zum LLM‑Output
wird nun eine Reihe konservativer Regeln angewendet: Zeilenumbrüche
werden in Leerzeichen umgewandelt, mehrfache Leerzeichen reduziert,
getrennte Silben wie „E influss“ zu „Einfluss“ zusammengeführt,
Bindestrich‑Zeilenumbrüche wie „Sicher- heit“ korrigiert und Bullets
(„•“) in eigene Zeilen gestellt. Eine kleine Funktion erkennt
häufige Extraktionsartefakte anhand dieser Muster und unterstützt die
Flagberechnung.

Modellbezeichnungen: Seit Block 22 ersetzt der zentrale
LLM‑Client in Entwicklungsumgebungen alte Modellbezeichnungen wie
llama3.1:8b automatisch durch die neue Form (llama3:8b). In
Produktionsumgebungen führt die Verwendung veralteter Namen zu einem
Fehler. Diese Regel verhindert unerwartete Fallbacks und macht
Modelländerungen transparent.

Diese Erweiterungen verbessern die Nachvollziehbarkeit und Qualität
der Normalisierung erheblich. Entwickler können in der Vorschau
sehen, ob das LLM tatsächlich wirkt und welche Artefakte entfernt
wurden, ohne dass bereits Daten überschrieben werden. In der
Produktion bleiben die stabilen Persistenz‑ und Fehlerregeln
erhalten.

## Parser‑Fixes und Jobs‑Store (Block 23)

In Block 23 wurden mehrere Fehler behoben, die beim Upload und der Verarbeitung von BSI‑Katalogen sowie bei der Registrierung von Jobs auftraten.

### Anforderungen ohne Punkt erkennen

Der Parser in `backend/app/api/bsi_catalogs.py` erkannte bisher nur Anforderungen, wenn nach dem Buchstaben „A“ ein Punkt stand (z. B. `A.1`). Im offiziellen BSI‑Katalog `SYS.3.2.2` werden Kennungen jedoch ohne Punkt geschrieben (z. B. `A1`). Der Regex zur Erkennung wurde so angepasst, dass der Punkt optional ist. Damit werden nun sowohl `A.1` als auch `A1` korrekt erkannt und als BsiRequirement gespeichert.

### Modul‑Erkennung einschränken

Das Parsen des PDF‑Textes führte gelegentlich dazu, dass Referenzen auf andere Module (etwa „ORP.4“) als neue Module interpretiert wurden. Die Logik speichert nun das Präfix des ersten gefundenen Bausteins (z. B. `SYS`) und erstellt nur dann einen neuen BsiModule‑Datensatz, wenn das Präfix übereinstimmt. Fremde Modulreferenzen werden ignoriert.

### Erweiterte Heuristiken

Die Funktion `_cleanup_description` entfernt Extraktionsartefakte und fügt fehlende Leerzeichen ein. Um ungewöhnliche Silbentrennungs‑Artefakte zu beheben, wurden folgende Korrekturen ergänzt:

- `"verar beitet" → "verarbeitet"`
- `"m indestens" → "mindestens"`
- `"Anfor derungen" → "Anforderungen"`
- `"indie" → "in die"`

Diese Erweiterungen verbessern die Lesbarkeit der extrahierten Texte und reduzieren die Anzahl der verbleibenden Artefakte.

### JobsStore‑Fix

Der Job‑Service verwendet einen `JobsStore`, der über die Methoden `create()`, `get()` und `set()` verfügt. An einigen Stellen im Code (insbesondere beim Starten von Normalisierungsjobs) wurde fälschlicherweise eine Dictionary‑Zuweisung verwendet (`jobs_store[job_id] = job_status`). Da `JobsStore` kein dict ist, führte dies zu einem Fehler. Alle Stellen wurden angepasst, sodass neue Jobs nun mit `jobs_store.set(job_status)` registriert werden.

### Auswirkungen

Dank dieser Änderungen werden beim Upload von BSI‑Katalogen sowohl die Module als auch deren Anforderungen zuverlässig erkannt, auch wenn die Kennungen variieren oder sich Silbentrennungsfehler im Text befinden. Jobs zur Normalisierung und Generierung werden nun ohne Fehler registriert und können über die API verfolgt werden.

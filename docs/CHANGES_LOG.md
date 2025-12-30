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
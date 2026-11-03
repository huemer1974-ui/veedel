# Veedel-Info Junkersdorf & Müngersdorf

Automatisch aktualisierte Seite für www.huemer.org: Stadion-Termine, Verkehr, Baustellen und
Meldungen aus dem Veedel. Läuft stündlich über GitHub Actions, ohne KI, ohne Datenbank, ohne Kosten.

## Was wo steht

| Datei | Zweck |
|---|---|
| `build.py` | holt alle Quellen, filtert, erzeugt die Seite in `public/` |
| `build.py` → Abschnitt *Einstellungen* | Stichworte, Umkreis, Mittelpunkt – hier kann man nachschärfen |
| `seiten/impressum.html`, `seiten/datenschutz.html` | **vor dem Livegang ausfüllen** (Platzhalter in eckigen Klammern) |
| `data/meldungen.json` | Archiv gefundener Meldungen (30 Tage), wird automatisch gepflegt |
| `.github/workflows/aktualisieren.yml` | der stündliche Zeitplan |

## Quellen

- RheinEnergieSTADION – Termine inkl. Anwohnerschutzkonzept (rheinenergiestadion.de/termine)
- Stadt Köln – Verkehrskalender (RSS) und Presseservice (RSS)
- Stadt Köln – Baustellen-Verzeichnis (WFS, Offene Daten, dl-de/by-2-0)
- Die Autobahn GmbH – A1/A4 Baustellen, Sperrungen, Meldungen (verkehr.autobahn.de)
- Polizei Köln – Presseportal (RSS)
- Wetter – Deutscher Wetterdienst über Bright Sky (api.brightsky.dev)

Fällt eine Quelle aus, zeigt nur dieser Abschnitt einen Hinweis; der Rest der Seite bleibt aktuell.

## Lokal testen

```bash
python3 build.py
python3 -m http.server 8765 -d public
```

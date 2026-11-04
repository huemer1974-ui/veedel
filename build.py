#!/usr/bin/env python3
"""
Veedel-Info Junkersdorf / Müngersdorf / Stadion.

Sammelt Meldungen aus öffentlichen Quellen, filtert sie nach festen Regeln
(Ortsnamen, Straßen, Umkreis auf der Karte) und erzeugt daraus eine statische
Webseite im Ordner public/. Keine KI, keine Datenbank, nur Python-Standardbibliothek.

Aufruf:  python3 build.py
"""
import datetime as dt
import html
import json
import math
import re
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------- Einstellungen

TITEL = "Veedel-Info Junkersdorf & Müngersdorf"
SEITE_URL = "https://www.huemer.org"

# Mittelpunkt des Gebiets (zwischen Junkersdorf, Müngersdorf und Stadion)
MITTE = (50.935, 6.868)
RADIUS_BAUSTELLEN_KM = 2.2
RADIUS_AUTOBAHN_KM = 5.0
VORLAUF_BAUSTELLEN = 60   # Tage: so weit im Voraus werden geplante Baustellen gezeigt

# Meldungen gelten als "aus dem Veedel", wenn eines dieser Wörter vorkommt.
STICHWORTE = [
    "Junkersdorf", "Müngersdorf", "Muengersdorf", "Braunsfeld", "Lövenich", "Weiden",
    "RheinEnergieStadion", "RheinEnergieSTADION", "Stadion", "Sportpark",
    "Stadionbad", "Sporthochschule", "Militärring", "Militärringstraße",
    "Kreuz Köln-West", "Belvederestraße", "Wendelinstraße", "Junkersdorfer",
    "Rhein-Energie-Stadion", "Müngersdorfer",
]
# Kürzel in den Adressen des Baustellen-Verzeichnisses
ORTSKUERZEL = {"Ju": "Junkersdorf", "Mü": "Müngersdorf", "Lö": "Lövenich", "We": "Weiden",
               "Md": "Marsdorf", "Bf": "Braunsfeld", "Li": "Lindenthal", "Wi": "Widdersdorf"}

AUTOBAHNEN = ["A1", "A4"]
TAGE_ARCHIV = 10          # wie lange gefundene Meldungen sichtbar bleiben
TAGE_SCHULEN = 30         # Schul-Nachrichten erscheinen seltener, daher etwas länger
MONATE_KARNEVAL = 5       # so weit im Voraus werden Karnevalstermine gezeigt

# Schulen mit Nachrichten-Feed (RSS) und weitere Einrichtungen nur als Link
SCHUL_FEEDS = {
    "Gymnasium Müngersdorf": "https://www.gymnasium-muengersdorf.de/feed/",
    "Ildefons-Herwegen-Schule (GGS)": "https://ildefons-herwegen-schule.de/feed/",
}
LINKS_VEEDEL = [
    ("Große Junkersdorfer Karnevals Gesellschaft von 1973", "https://koelnerkarneval.de/detaillierte-informationen/grosse-junkersdorfer-karnevalsgesellschaft-von-1973-ev"),
    ("GGS Müngersdorf, Wendelinstraße", "https://www.ggs-muengersdorf.de/"),
    ("GGS Alfons-Nowak-Straße, Junkersdorf", "https://www.alfons-nowak-strasse.de/"),
    ("Gymnasium Müngersdorf", "https://www.gymnasium-muengersdorf.de/"),
    ("Ildefons-Herwegen-Schule, Junkersdorf", "https://ildefons-herwegen-schule.de/"),
    ("Ernst-Simons-Realschule, Müngersdorf", "https://www.ernst-simons-realschule.de/"),
]
MONATE = {m: i for i, m in enumerate(["januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
                                       "september", "oktober", "november", "dezember"], 1)}
BASIS = Path(__file__).resolve().parent
AUSGABE = BASIS / "public"
ARCHIV = BASIS / "data" / "meldungen.json"
TZ = ZoneInfo("Europe/Berlin")
JETZT = dt.datetime.now(TZ)
HEUTE = JETZT.date()

QUELLEN = {
    "stadion": "https://www.rheinenergiestadion.de/termine",
    "verkehrskalender": "https://www.stadt-koeln.de/externe-dienste/rss/verkehrskalender.xml",
    "stadt_presse": "https://www.stadt-koeln.de/externe-dienste/rss/pressemeldungen.xml",
    "polizei": "https://www.presseportal.de/rss/dienststelle_12415.rss2",
    "baustellen_wfs": "https://geoportal.stadt-koeln.de/wss/service/baustellen_wfs/guest",
    "autobahn": "https://verkehr.autobahn.de/o/autobahn/{a}/services/{s}",
    "wetter": "https://api.brightsky.dev/current_weather?lat={lat}&lon={lon}",
}

BAUSTELLEN_ARTEN = [
    "ampelarbeiten", "arbeitsbuehne", "baustelleneinrichtung", "brueckenarbeiten",
    "gleisbau", "kanalsanierung", "markierungsarbeiten", "notfall", "sondierungsarbeiten",
    "strassenbauarbeiten", "tunnelarbeiten", "versorgungsarbeiten",
]

# ---------------------------------------------------------------- Hilfsfunktionen


def laden(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": f"Veedel-Info ({SEITE_URL})"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def text(s):
    """HTML zu reinem Text."""
    s = re.sub(r"<(script|style).*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</h\d>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


def treffer(s):
    """Ganze Wörter, Groß-/Kleinschreibung beachten (z. B. nicht "Südstadion" oder "weiden")."""
    return sorted({w for w in STICHWORTE if re.search(rf"(?<![\wäöüß-]){re.escape(w)}(?![\wäöüß])", s or "")})


def km(a, b):
    dlat = math.radians(b[0] - a[0])
    dlon = math.radians(b[1] - a[1])
    x = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(x))


def utm32_zu_wgs84(e, n):
    """ETRS89/UTM Zone 32N (EPSG:25832) -> Breite/Länge."""
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    x, y = e - 500000.0, n
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
         + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
         + (151 * e1**3 / 96) * math.sin(6 * mu))
    c1 = ep2 * math.cos(p) ** 2
    t1 = math.tan(p) ** 2
    n1 = a / math.sqrt(1 - e2 * math.sin(p) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * math.sin(p) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = p - (n1 * math.tan(p) / r1) * (d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
                                          + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720)
    lon = (d - (1 + 2 * t1 + c1) * d**3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120) / math.cos(p)
    return math.degrees(lat), 9 + math.degrees(lon)


def wgs84_zu_utm32(lat, lon):
    """Grobe Umkehrung (reicht für die Abfrage-Box) per Newton-Iteration."""
    e, n = 500000 + (lon - 9) * 70000, lat * 111000
    for _ in range(5):
        la, lo = utm32_zu_wgs84(e, n)
        n += (lat - la) * 111000
        e += (lon - lo) * 70000
    return e, n


def rss_items(xml):
    out = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def feld(k):
            m = re.search(rf"<{k}>(.*?)</{k}>", it, re.S)
            v = m.group(1) if m else ""
            return re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", v.strip(), flags=re.S)
        datum = None
        try:
            datum = dt.datetime.strptime(feld("pubDate"), "%a, %d %b %Y %H:%M:%S %z").astimezone(TZ)
        except ValueError:
            pass
        out.append({"titel": text(feld("title")), "link": html.unescape(feld("link")),
                    "text": text(feld("description")), "datum": datum})
    return out


def kurz(s, n=260):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: s.rfind(" ", 0, n)] + " …"


WOCHENTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def datum_de(d):
    return f"{WOCHENTAG[d.weekday()]}, {d.day:02d}.{d.month:02d}.{d.year}"


# ---------------------------------------------------------------- Quellen


def stadion():
    seite = laden(QUELLEN["stadion"])
    termine = []
    for block in seite.split('<div class="events_list_item">')[1:]:
        datum = text(re.search(r"<b[^>]*>(.*?)</b>", block, re.S).group(1))
        tage = [dt.datetime.strptime(d, "%d/%m/%Y").date() for d in re.findall(r"\d{2}/\d{2}/\d{4}", datum)]
        if not tage:
            continue
        info = text(re.search(r"<p[^>]*>(.*?)</p>", block, re.S).group(1))
        def zeit(label):
            m = re.search(label + r"[^:]*:\s*(?:ab\s*)?(\d{1,2}:\d{2})", info.replace("-\n", "").replace("\n", " "))
            return m.group(1) if m else None
        titel = text(re.search(r"<h2[^>]*>(.*?)</h2>", block, re.S).group(1))
        notiz = re.search(r'class="termine-notes"><h2>(.*?)</h2>', block, re.S)
        ical = re.search(r'class="termine-cal".*?href="([^"]+)"', block, re.S)
        termine.append({
            "von": tage[0], "bis": tage[-1], "titel": titel,
            "untertitel": text(notiz.group(1)) if notiz else "",
            "beginn": zeit("Beginn"), "einlass": zeit("Einlass"), "anwohnerschutz": zeit("konzept"),
            "offen": "noch nicht terminiert" in block,
            "ical": ical.group(1) if ical else None,
        })
    return [t for t in termine if t["bis"] >= HEUTE]


def daten_im_text(s):
    """Alle Datumsangaben wie '3. November 2026', '17.11.26' oder '08.11.2026' als date."""
    tage = []
    for t, m, j in re.findall(r"(\d{1,2})\.\s*([A-Za-zäÄ]+)\s+(\d{4})", s):
        if m.lower() in MONATE:
            tage.append((int(j), MONATE[m.lower()], int(t)))
    for t, m, j in re.findall(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b", s):
        tage.append((int(j) + (2000 if len(j) == 2 else 0), int(m), int(t)))
    out = []
    for j, m, t in tage:
        try:
            out.append(dt.date(j, m, t))
        except ValueError:
            pass
    return out


def abgelaufen(s):
    """True, wenn der Text Daten nennt und das späteste davon schon vorbei ist."""
    d = daten_im_text(s)
    return bool(d) and max(d) < HEUTE


def verkehrskalender():
    out = []
    for it in rss_items(laden(QUELLEN["verkehrskalender"])):
        w = treffer(it["titel"] + " " + it["text"])
        if w and not abgelaufen(it["text"]):
            it["treffer"] = w
            out.append(it)
    return out


def baustellen():
    e, n = wgs84_zu_utm32(*MITTE)
    r = RADIUS_BAUSTELLEN_KM * 1000
    box = f"{e - r:.0f},{n - r:.0f},{e + r:.0f},{n + r:.0f}"
    gesehen, out = set(), []
    for art in BAUSTELLEN_ARTEN:
        url = (f"{QUELLEN['baustellen_wfs']}?SERVICE=WFS&VERSION=1.1.0&REQUEST=GetFeature"
               f"&TYPENAME=ms:{art}&OUTPUTFORMAT=geojson&BBOX={box}")
        try:
            daten = json.loads(laden(url, timeout=60))
        except Exception:
            continue
        for f in daten.get("features", []):
            p = f["properties"]
            koord = f["geometry"]["coordinates"]
            while isinstance(koord[0], list):     # Linien/Flächen: ersten Punkt nehmen
                koord = koord[0]
            lat, lon = utm32_zu_wgs84(*koord[:2])
            if km(MITTE, (lat, lon)) > RADIUS_BAUSTELLEN_KM:
                continue
            m = re.findall(r"\d{2}-\d{2}-\d{4}", p.get("Genehmigungs-Zeitraum", ""))
            if len(m) != 2:
                continue
            von, bis = (dt.datetime.strptime(x, "%d-%m-%Y").date() for x in m)
            if bis < HEUTE or von > HEUTE + dt.timedelta(days=VORLAUF_BAUSTELLEN) or (bis - von).days > 730:
                continue  # vorbei, noch weit weg oder Dauer-Genehmigung
            adresse = re.sub(r"\s+", " ", p.get("Adresse", "")).strip()
            ort = ""
            m_ort = re.search(r"\s(" + "|".join(ORTSKUERZEL) + r")\b\.?", adresse)
            if m_ort:
                ort = ORTSKUERZEL[m_ort.group(1)]
                adresse = (adresse[:m_ort.start()] + adresse[m_ort.end():]).strip()
            schluessel = (p.get("Aktenzeichen"), adresse)
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            out.append({"art": p.get("Kategorie", art), "adresse": adresse, "ort": ort, "von": von, "bis": bis,
                        "lat": lat, "lon": lon, "neu": von >= HEUTE - dt.timedelta(days=3),
                        "entfernung": km(MITTE, (lat, lon))})
    out.sort(key=lambda b: b["entfernung"])
    return out


def autobahn():
    out, gesehen = [], set()
    namen = {"warning": "Verkehrsmeldung", "closure": "Sperrung", "roadworks": "Baustelle"}
    for a in AUTOBAHNEN:
        for s, art in namen.items():
            daten = json.loads(laden(QUELLEN["autobahn"].format(a=a, s=s)))
            for x in next(iter(daten.values()), []):
                pos = (float(x["coordinate"]["lat"]), float(x["coordinate"]["long"]))
                if km(MITTE, pos) > RADIUS_AUTOBAHN_KM:
                    continue
                beschr = " ".join(x.get("description", []))
                if art != "Verkehrsmeldung" and abgelaufen(beschr):
                    continue  # Baustelle/Sperrung ist laut Beschreibung schon vorbei
                zeitraum = re.search(r"(?:gültig:|Bauphase:|Beginn:)\s*(.*?)(?:\s{2}|$)", beschr)
                zeilen = [z.strip() for z in x.get("description", [])]
                ort = next((z for z in zeilen if z.startswith(("Auffahrt", "Abfahrt"))), "")
                schluessel = (x["title"].strip(), art, ort or x["subtitle"].strip(),
                              zeitraum.group(1)[:60] if zeitraum else "")
                if schluessel in gesehen:
                    continue
                gesehen.add(schluessel)
                out.append({"art": art, "titel": x["title"].strip(), "richtung": ort or x["subtitle"].strip(),
                            "zeit": kurz(zeitraum.group(1), 140) if zeitraum else "",
                            "sperrung": art == "Sperrung" or x.get("isBlocked") == "true",
                            "lat": pos[0], "lon": pos[1]})
    reihenfolge = {"Verkehrsmeldung": 0, "Sperrung": 1, "Baustelle": 2}
    out.sort(key=lambda x: reihenfolge[x["art"]])
    return out


def pressemeldungen(feed, quelle):
    """Meldungen holen, Volltext lesen, nur behalten, was das Veedel erwähnt."""
    neu = []
    for it in rss_items(laden(QUELLEN[feed])):
        if it["datum"] and it["datum"].date() < HEUTE - dt.timedelta(days=TAGE_ARCHIV):
            continue
        volltext = it["text"]
        try:
            seite = laden(it["link"])
            haupt = re.search(r"<main.*?</main>|<article.*?</article>", seite, re.S)
            volltext = text(haupt.group(0) if haupt else seite)
            volltext = volltext.split("Weitere Meldungen")[0]
        except Exception:
            pass
        w = treffer(it["titel"] + " " + volltext)
        if not w:
            continue
        # Absatz mit dem ersten Treffer als kurzer Anriss
        absatz = next((a for a in volltext.split("\n") if treffer(a) and len(a) > 40), it["text"])
        neu.append({"quelle": quelle, "titel": it["titel"], "link": it["link"],
                    "datum": it["datum"].isoformat() if it["datum"] else JETZT.isoformat(),
                    "anriss": kurz(absatz), "treffer": w})
    return neu


def karneval():
    """Sessionskalender des Festkomitees: Monat für Monat, nur Termine aus dem Veedel."""
    basis = "https://koelnerkarneval.de"
    seite = laden(basis + "/session/veranstaltungen")
    out, gesehen = [], set()
    for _ in range(MONATE_KARNEVAL):
        for karte in seite.split('<div class="card border-0">')[1:]:
            datum = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", karte)
            titel = re.search(r"<h5[^>]*>(.*?)</h5>", karte, re.S)
            if not (datum and titel):
                continue
            tag = dt.date(int(datum.group(3)), int(datum.group(2)), int(datum.group(1)))
            beschr = re.search(r'itemprop="description">(.*?)</div>', karte, re.S)
            beschr = text(beschr.group(1)) if beschr else ""
            if tag < HEUTE or not treffer(text(titel.group(1)) + " " + beschr):
                continue
            uhr = re.search(r"fa-clock\"></i>\s*(\d{1,2}:\d{2})", karte)
            link = re.search(r'href="(/session/veranstaltungen/veranstaltung/[^"]+)"', karte)
            schluessel = (tag, text(titel.group(1)))
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            out.append({"tag": tag, "uhr": uhr.group(1) if uhr else "", "titel": text(titel.group(1)),
                        "text": beschr, "link": basis + link.group(1) if link else basis + "/session/veranstaltungen"})
        # Link zum nächsten Monat suchen (der mit dem spätesten Monat auf der Seite)
        monate = []
        for l in re.findall(r'href="(/session/veranstaltungen\?[^"]*action%5D=month[^"]*)"', seite):
            m = re.search(r"month%5D=(\d+).*?year%5D=(\d+)", l)
            if m:
                monate.append((int(m.group(2)) * 12 + int(m.group(1)), html.unescape(l)))
        if not monate:
            break
        seite = laden(basis + max(monate)[1])
    return sorted(out, key=lambda k: (k["tag"], k["uhr"]))


def schulen():
    out = []
    for name, url in SCHUL_FEEDS.items():
        try:
            items = rss_items(laden(url))
        except Exception as ex:
            print(f"!! Schule {name}: {ex}")
            continue
        for it in items[:3]:
            if it["datum"] and it["datum"].date() >= HEUTE - dt.timedelta(days=TAGE_SCHULEN):
                out.append({"quelle": name, "titel": it["titel"], "link": it["link"],
                            "datum": it["datum"], "anriss": kurz(it["text"], 200)})
    return sorted(out, key=lambda m: m["datum"], reverse=True)


def wetter():
    d = json.loads(laden(QUELLEN["wetter"].format(lat=MITTE[0], lon=MITTE[1])))["weather"]
    return {"temp": d.get("temperature"), "icon": d.get("icon"), "wind": d.get("wind_speed_10"),
            "regen": d.get("precipitation_60")}


# ---------------------------------------------------------------- Archiv


def archiv_aktualisieren(neue):
    alt = json.loads(ARCHIV.read_text("utf-8")) if ARCHIV.exists() else []
    if isinstance(alt, dict):
        alt = alt.get("meldungen", [])
    nach_link = {m["link"]: m for m in alt}
    for m in neue:
        nach_link.setdefault(m["link"], m)
    grenze = (JETZT - dt.timedelta(days=TAGE_ARCHIV)).isoformat()
    liste = sorted((m for m in nach_link.values() if m["datum"] >= grenze), key=lambda m: m["datum"], reverse=True)
    ARCHIV.parent.mkdir(exist_ok=True)
    # "lebenszeichen" ändert sich monatlich -> der Bot speichert mindestens einmal im Monat,
    # und GitHub pausiert den Zeitplan nicht (Pause nach 60 Tagen ohne Aktivität).
    ARCHIV.write_text(json.dumps({"lebenszeichen": f"{HEUTE:%Y-%m}", "meldungen": liste},
                                 ensure_ascii=False, indent=1), "utf-8")
    return liste


# ---------------------------------------------------------------- Kalender-Datei


def ics(termine):
    zeilen = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//huemer.org//Veedel-Info//DE",
              "X-WR-CALNAME:RheinEnergieSTADION – Termine", "X-WR-TIMEZONE:Europe/Berlin"]
    for t in termine:
        uid = re.sub(r"\W+", "-", f"{t['von']}-{t['titel']}", flags=re.ASCII).lower()
        zeilen += ["BEGIN:VEVENT", f"UID:{uid}@huemer.org", f"DTSTAMP:{JETZT.astimezone(dt.timezone.utc):%Y%m%dT%H%M%SZ}"]
        if t["beginn"] and t["von"] == t["bis"]:
            h, m = map(int, t["beginn"].split(":"))
            start = dt.datetime.combine(t["von"], dt.time(h, m), TZ)
            zeilen += [f"DTSTART;TZID=Europe/Berlin:{start:%Y%m%dT%H%M%S}",
                       f"DTEND;TZID=Europe/Berlin:{start + dt.timedelta(hours=3):%Y%m%dT%H%M%S}"]
        else:
            zeilen += [f"DTSTART;VALUE=DATE:{t['von']:%Y%m%d}",
                       f"DTEND;VALUE=DATE:{t['bis'] + dt.timedelta(days=1):%Y%m%d}"]
        notiz = [t["untertitel"]]
        if t["anwohnerschutz"]:
            notiz.append(f"Anwohnerschutzkonzept ab {t['anwohnerschutz']} Uhr")
        if t["offen"]:
            notiz.append("Spieltag noch nicht genau terminiert")
        zeilen += [f"SUMMARY:{t['titel']}", "LOCATION:RheinEnergieSTADION\\, Aachener Str. 999\\, Köln",
                   "DESCRIPTION:" + "\\n".join(x for x in notiz if x).replace(",", "\\,"), "END:VEVENT"]
    zeilen.append("END:VCALENDAR")
    return "\r\n".join(zeilen) + "\r\n"


# ---------------------------------------------------------------- HTML

e = html.escape
WETTER_SYMBOL = {"clear-day": "☀️", "clear-night": "🌙", "partly-cloudy-day": "⛅", "partly-cloudy-night": "☁️",
                 "cloudy": "☁️", "fog": "🌫️", "wind": "💨", "rain": "🌧️", "sleet": "🌨️", "snow": "❄️",
                 "hail": "🌨️", "thunderstorm": "⛈️"}


def abschnitt(id_, titel, inhalt, quelle_html, leer="Zurzeit keine Meldungen."):
    return f"""
<section id="{id_}">
  <h2>{titel}</h2>
  {inhalt or f'<p class="leer">{leer}</p>'}
  <p class="quelle">Quelle: {quelle_html}</p>
  <p class="nach-oben"><a href="#oben">↑ nach oben</a></p>
</section>"""


def fehler_html(name):
    return f'<p class="leer">⚠️ {name} ist gerade nicht erreichbar. Beim nächsten Update wird es erneut versucht.</p>'


def banner_html(termine):
    for t in termine:
        if t["von"] <= HEUTE + dt.timedelta(days=1) and t["bis"] >= HEUTE and not t["offen"]:
            wann = "Heute" if t["von"] == HEUTE else "Morgen"
            details = []
            if t["anwohnerschutz"]:
                details.append(f"Anwohnerschutz ab <b>{t['anwohnerschutz']}&nbsp;Uhr</b>")
            if t["einlass"]:
                details.append(f"Einlass {t['einlass']}&nbsp;Uhr")
            if t["beginn"]:
                details.append(f"Beginn {t['beginn']}&nbsp;Uhr")
            return f"""<div class="banner alarm"><span class="banner-kopf">🏟️ {wann} ist Stadion-Tag</span>
<strong>{e(t['titel'])}</strong><span>{' · '.join(details)}</span>
<span class="klein">Rund ums Stadion mit Sperrungen und Parkkontrollen rechnen.</span></div>"""
    nächster = next((t for t in termine if not t["offen"]), None)
    if nächster:
        tage = (nächster["von"] - HEUTE).days
        return f"""<div class="banner ruhig"><span class="banner-kopf">🏟️ Nächster Stadion-Termin in {tage} Tagen</span>
<strong>{e(nächster['titel'])}</strong><span>{datum_de(nächster['von'])}{' · Beginn ' + nächster['beginn'] + '&nbsp;Uhr' if nächster['beginn'] else ''}</span></div>"""
    return ""


def stadion_html(termine):
    zeilen = []
    for t in termine[:8]:
        wann = datum_de(t["von"]) if t["von"] == t["bis"] else f"{datum_de(t['von'])} – {datum_de(t['bis'])}"
        zeiten = []
        if t["offen"]:
            zeiten.append("Termin noch offen")
        if t["beginn"]:
            zeiten.append(f"Beginn {t['beginn']}")
        if t["anwohnerschutz"]:
            zeiten.append(f"Anwohnerschutz ab {t['anwohnerschutz']}")
        zeilen.append(f"""<li><div class="datum">{wann}</div><div><strong>{e(t['titel'])}</strong>
<span class="klein">{e(t['untertitel'])}</span><span class="zeiten">{' · '.join(zeiten)}</span></div></li>""")
    return f'<ul class="liste termine">{"".join(zeilen)}</ul><p><a class="knopf" href="stadion.ics">📅 Alle Termine als Kalender abonnieren</a></p>'


def verkehr_html(vk, ab):
    teile = []
    for it in vk or []:
        teile.append(f"""<li><strong>{e(it['titel'])}</strong><span>{e(kurz(it['text'], 260))}</span>
{f'<a href="{e(it["link"])}">Details bei der Stadt Köln</a>' if it['link'].count('/') > 3 else ''}</li>""")
    if vk is None:
        stadt = "<h3>Stadtstraßen</h3>" + fehler_html("Der Verkehrskalender")
    else:
        stadt = "<h3>Stadtstraßen</h3>" + (f'<ul class="liste kompakt">{"".join(teile)}</ul>' if teile
                                            else '<p class="leer klein">Keine Meldungen für das Veedel im Verkehrskalender.</p>')
    if ab is None:
        return stadt + "<h3>Autobahn A1 / A4</h3>" + fehler_html("Die Autobahn GmbH")

    def zeile(x):
        klasse = "warn" if x["art"] == "Verkehrsmeldung" else ("sperr" if x["sperrung"] else "")
        return f"""<li class="{klasse}"><span><span class="etikett">{x['art']}</span> <strong>{e(x['titel'])}</strong> · {e(x['richtung'])}</span>
<span class="klein">{e(x['zeit'])}</span></li>"""
    stau = [x for x in ab if x["art"] == "Verkehrsmeldung"]
    bahn = f"<h3>Autobahn A1 / A4 (Umkreis {RADIUS_AUTOBAHN_KM:.0f} km)</h3>"
    bahn += f'<ul class="liste kompakt">{"".join(map(zeile, stau))}</ul>' if stau else '<p class="leer klein">Zurzeit kein Stau gemeldet.</p>'
    for art, titel in [("Sperrung", "Sperrungen"), ("Baustelle", "Baustellen")]:
        liste = [x for x in ab if x["art"] == art]
        if liste:
            bahn += (f'<details><summary>Autobahn-{titel} ({len(liste)}) – auch in der Karte</summary>'
                     f'<ul class="liste mini">{"".join(map(zeile, liste))}</ul></details>')
    return stadt + bahn


STADION = (50.9335, 6.8750)
LEAFLET = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/"


def leaflet_holen():
    """Kartenbibliothek einmal pro Lauf herunterladen und selbst ausliefern (kein Fremd-Skript im Browser)."""
    ziel = AUSGABE / "leaflet"
    ziel.mkdir(parents=True, exist_ok=True)
    for name in ["leaflet.min.js", "leaflet.min.css"]:
        (ziel / name).write_text(laden(LEAFLET + name), "utf-8")
    return True


def karte_html(bs, ab):
    def dauer(von, bis):
        if von > HEUTE:
            t = (von - HEUTE).days
            return f"beginnt {'morgen' if t == 1 else f'in {t} Tagen'} ({von:%d.%m.%Y})"
        t = (bis - HEUTE).days
        return "endet heute" if t == 0 else f"noch {t} {'Tag' if t == 1 else 'Tage'} (bis {bis:%d.%m.%Y})"

    punkte = []
    for b in bs:
        typ = "bald" if b["von"] > HEUTE else "endet" if (b["bis"] - HEUTE).days <= 7 else "aktuell"
        ort = f" ({b['ort']})" if b["ort"] else ""
        punkte.append({"lat": round(b["lat"], 6), "lon": round(b["lon"], 6), "typ": typ,
                       "html": f"<strong>{e(b['adresse'])}{e(ort)}</strong><br>{e(b['art'])}<br>"
                               f"<span class='k-{typ}'>{'Demnächst' if typ == 'bald' else 'Läuft'}: {dauer(b['von'], b['bis'])}</span>"
                               f"<br><small>Genehmigt {b['von']:%d.%m.%Y} – {b['bis']:%d.%m.%Y}</small>"})
    for x in ab or []:
        punkte.append({"lat": round(x["lat"], 6), "lon": round(x["lon"], 6), "typ": "autobahn",
                       "html": f"<strong>{e(x['art'])}: {e(x['titel'])}</strong><br>{e(x['richtung'])}"
                               f"<br><small>{e(x['zeit'])}</small>"})
    daten = json.dumps({"mitte": MITTE, "stadion": STADION, "punkte": punkte}, ensure_ascii=False).replace("</", "<\\/")
    zahl = {t: sum(p["typ"] == t for p in punkte) for t in ["aktuell", "endet", "bald", "autobahn"]}
    return f"""
<div class="karte-legende">
  <label><input type="checkbox" data-typ="aktuell" checked> <span class="punkt k-aktuell-bg"></span> Läuft gerade ({zahl['aktuell']})</label>
  <label><input type="checkbox" data-typ="endet" checked> <span class="punkt k-endet-bg"></span> Endet in den nächsten 7 Tagen ({zahl['endet']})</label>
  <label><input type="checkbox" data-typ="bald" checked> <span class="punkt k-bald-bg"></span> Beginnt in den nächsten {VORLAUF_BAUSTELLEN} Tagen ({zahl['bald']})</label>
  <label><input type="checkbox" data-typ="autobahn" checked> <span class="punkt k-autobahn-bg"></span> Autobahn A1/A4 ({zahl['autobahn']})</label>
</div>
<div id="karte-huelle">
  <div id="karte"></div>
  <div id="karte-hinweis"><p><strong>Karte anzeigen?</strong><br>Beim Laden werden Kartenbilder von OpenStreetMap abgerufen.
  Dabei wird Ihre IP-Adresse an die OpenStreetMap Foundation übertragen (<a href="datenschutz.html">Datenschutz</a>).</p>
  <button type="button" class="knopf" id="karte-laden">🗺️ Karte laden</button>
  <label class="klein"><input type="checkbox" id="karte-merken"> Karte künftig automatisch laden</label></div>
</div>
<script>
(function(){{
var D={daten}, karte=null, gruppen={{}};
var FARBE={{aktuell:"#d62839",endet:"#f08ca0",bald:"#e08a00",autobahn:"#6a3fc4"}};
function merken(){{try{{return localStorage.getItem("karte-ok")==="1";}}catch(e){{return false;}}}}
function zeigen(){{
  document.getElementById("karte-hinweis").style.display="none";
  var css=document.createElement("link");css.rel="stylesheet";css.href="leaflet/leaflet.min.css";document.head.appendChild(css);
  var js=document.createElement("script");js.src="leaflet/leaflet.min.js";js.onload=bauen;document.head.appendChild(js);
}}
function bauen(){{
  karte=L.map("karte",{{scrollWheelZoom:false}}).setView(D.mitte,14);
  L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png",{{maxZoom:19,
    attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende'}}).addTo(karte);
  ["aktuell","endet","bald","autobahn"].forEach(function(t){{gruppen[t]=L.layerGroup().addTo(karte);}});
  D.punkte.forEach(function(p){{
    var m=p.typ==="autobahn"
      ? L.circleMarker([p.lat,p.lon],{{radius:9,color:"#fff",weight:2,fillColor:FARBE[p.typ],fillOpacity:.95}})
      : L.circleMarker([p.lat,p.lon],{{radius:7,color:"#fff",weight:1.5,fillColor:FARBE[p.typ],fillOpacity:.9}});
    m.bindPopup(p.html).addTo(gruppen[p.typ]);
  }});
  L.marker(D.stadion,{{icon:L.divIcon({{className:"stadion-icon",html:"🏟️",iconSize:[26,26]}})}})
    .bindPopup("<strong>RheinEnergieSTADION</strong>").addTo(karte);
  var alle=D.punkte.filter(function(p){{return p.typ!=="autobahn";}}).map(function(p){{return [p.lat,p.lon];}});
  if(alle.length) karte.fitBounds(alle,{{padding:[20,20],maxZoom:15}});
  filtern();
}}
function filtern(){{
  if(!karte) return;
  document.querySelectorAll(".karte-legende input").forEach(function(c){{
    var g=gruppen[c.dataset.typ]; if(c.checked) karte.addLayer(g); else karte.removeLayer(g);
  }});
}}
document.querySelectorAll(".karte-legende input").forEach(function(c){{c.addEventListener("change",filtern);}});
document.getElementById("karte-laden").addEventListener("click",function(){{
  if(document.getElementById("karte-merken").checked){{try{{localStorage.setItem("karte-ok","1");}}catch(e){{}}}}
  zeigen();
}});
if(merken()) zeigen();
}})();
</script>"""


WOCHEN_EINZELN = 6   # so viele Wochen werden einzeln gezeigt, danach "später"


def baustellen_html(bs):
    """Baustellen nach Wochen gruppiert: kommende nach Beginn, laufende nach Ende."""
    montag = HEUTE - dt.timedelta(days=HEUTE.weekday())

    def woche(d):
        return (d - montag).days // 7

    def spanne(n):
        a = montag + dt.timedelta(weeks=n)
        return f"{a:%d.%m.}–{a + dt.timedelta(days=6):%d.%m.}"

    gruppen = {}
    for b in bs:
        if b["von"] > HEUTE:
            n = min(woche(b["von"]), WOCHEN_EINZELN)
            schluessel = (0, n)
            titel = ("Beginnen diese Woche" if n == 0 else "Beginnen nächste Woche" if n == 1
                     else f"Beginnen ab {spanne(n)[:6]}" if n == WOCHEN_EINZELN else f"Beginnen {spanne(n)}")
        else:
            n = min(woche(b["bis"]), WOCHEN_EINZELN)
            schluessel = (1, n)
            titel = ("Enden diese Woche" if n == 0 else "Enden nächste Woche" if n == 1
                     else f"Enden später (nach {(montag + dt.timedelta(weeks=n) - dt.timedelta(days=1)):%d.%m.})"
                     if n == WOCHEN_EINZELN else f"Enden in der Woche {spanne(n)}")
        gruppen.setdefault(schluessel, (titel, []))[1].append(b)

    teile = []
    for i, schluessel in enumerate(sorted(gruppen)):
        titel, liste = gruppen[schluessel]
        liste.sort(key=lambda b: (b["bis"] if schluessel[0] else b["von"], b["adresse"]))
        z = []
        for b in liste:
            osm = f"https://www.openstreetmap.org/?mlat={b['lat']:.5f}&mlon={b['lon']:.5f}#map=18/{b['lat']:.5f}/{b['lon']:.5f}"
            zeit = f"{b['von']:%d.%m.} – {b['bis']:%d.%m.%Y}"
            neu = ' <span class="etikett neu">neu</span>' if b["neu"] else ""
            ort = f" ({e(b['ort'])})" if b["ort"] else ""
            z.append(f'<li><span><a href="{osm}" title="Auf der Karte zeigen">{e(b["adresse"])}</a>{ort}{neu}</span>'
                     f'<span>{e(b["art"])} · {zeit}</span></li>')
        offen = " open" if i < 2 else ""
        teile.append(f'<details{offen}><summary>{titel} ({len(liste)})</summary><ul class="liste mini spalten">{"".join(z)}</ul></details>')
    if not teile:
        return ""
    return (f"<h3>Baustellen im Veedel ({len(bs)})</h3><p class=\"klein\">Genehmigte Arbeiten im Umkreis von {RADIUS_BAUSTELLEN_KM} km, "
            f"die laufen oder in den nächsten {VORLAUF_BAUSTELLEN} Tagen beginnen – nach Woche sortiert. "
            "Ein Klick auf die Adresse zeigt die Stelle auf OpenStreetMap.</p>" + "".join(teile))


def alter(d):
    tage = (HEUTE - d).days
    return "heute" if tage == 0 else "gestern" if tage == 1 else f"vor {tage} Tagen"


def meldungen_html(liste):
    z = []
    for m in liste:
        d = dt.datetime.fromisoformat(m["datum"]).astimezone(TZ)
        z.append(f"""<li><div class="klein">{datum_de(d.date())} ({alter(d.date())}) · {e(m['quelle'])} · erwähnt: {e(', '.join(m['treffer']))}</div>
<a href="{e(m['link'])}"><strong>{e(m['titel'])}</strong></a><span>{e(m['anriss'])}</span></li>""")
    return f'<ul class="liste">{"".join(z)}</ul>' if z else ""


def karneval_html(liste):
    z = []
    for k in liste[:12]:
        uhr = f" · {k['uhr']} Uhr" if k["uhr"] else ""
        z.append(f"""<li><div class="datum">{datum_de(k['tag'])}</div><div><a href="{e(k['link'])}"><strong>{e(k['titel'])}</strong></a>
<span class="klein">{e(k['text'])}{uhr}</span></div></li>""")
    return f'<ul class="liste termine">{"".join(z)}</ul>' if z else ""


def schulen_html(liste):
    z = []
    for m in liste:
        z.append(f"""<li><div class="klein">{datum_de(m['datum'].date())} ({alter(m['datum'].date())}) · {e(m['quelle'])}</div>
<a href="{e(m['link'])}"><strong>{e(m['titel'])}</strong></a>{f"<span>{e(m['anriss'])}</span>" if m['anriss'] else ""}</li>""")
    neu = f'<ul class="liste">{"".join(z)}</ul>' if z else f'<p class="leer">In den letzten {TAGE_SCHULEN} Tagen keine neuen Beiträge.</p>'
    links = " · ".join(f'<a href="{e(u)}">{e(n)}</a>' for n, u in LINKS_VEEDEL)
    return neu + f'<h3>Schulen und Vereine im Veedel</h3><p class="klein">{links}</p>'


def wetter_html(w):
    if not w or w["temp"] is None:
        return ""
    regen = f" · Regen {w['regen']:.1f} mm/h" if w.get("regen") else ""
    return f'<div class="wetter">{WETTER_SYMBOL.get(w["icon"], "🌡️")} {w["temp"]:.0f} °C · Wind {w["wind"]:.0f} km/h{regen}</div>'


CSS = """
:root{--bg:#f6f5f2;--karte:#fff;--text:#1d1d1f;--leise:#6b6b70;--linie:#e3e1dc;--akzent:#b0122b;--akzent-hell:#fbe9ec;--warn:#9a5b00;--warn-hell:#fff3dc;--ok:#1f6f43}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--karte:#1e1e21;--text:#ececef;--leise:#a0a0a8;--linie:#2e2e33;--akzent:#ff6b7f;--akzent-hell:#3a1a20;--warn:#ffb648;--warn-hell:#33280f;--ok:#5fd193}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--akzent)}
.wrap{max-width:760px;margin:0 auto;padding:16px}
header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:8px;padding:8px 0 4px}
header h1{font-size:1.5rem;margin:0}
.stand,.klein,.quelle{color:var(--leise);font-size:.85rem}
nav{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 18px}
nav a{background:var(--karte);border:1px solid var(--linie);border-radius:99px;padding:4px 12px;text-decoration:none;color:var(--text);font-size:.9rem}
.wetter{font-size:.95rem}
.banner{display:flex;flex-direction:column;gap:2px;border-radius:14px;padding:14px 18px;margin-bottom:18px}
.banner.alarm{background:var(--akzent-hell);border:2px solid var(--akzent)}
.banner.ruhig{background:var(--karte);border:1px solid var(--linie)}
.banner-kopf{font-weight:600;color:var(--akzent)}
.banner strong{font-size:1.15rem}
section{background:var(--karte);border:1px solid var(--linie);border-radius:14px;padding:4px 18px 10px;margin-bottom:18px}
section h2{font-size:1.2rem;margin:14px 0 8px}
section h3{font-size:1rem;margin:16px 0 6px;color:var(--leise)}
.liste{list-style:none;margin:0;padding:0}
.liste li{display:flex;flex-direction:column;gap:2px;padding:10px 0;border-top:1px solid var(--linie)}
.liste li:first-child{border-top:0}
.liste.termine li{flex-direction:row;gap:14px}
.liste.termine .datum{min-width:120px;font-weight:600;color:var(--akzent);font-size:.9rem}
.liste.termine li>div:last-child{display:flex;flex-direction:column}
.zeiten{font-size:.85rem}
.liste.spalten{columns:2 260px;column-gap:24px}
.liste.spalten li{break-inside:avoid}
.liste li.warn{background:var(--warn-hell);margin:0 -10px;padding:10px;border-radius:8px}
.etikett{display:inline-block;font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.03em;color:var(--leise)}
li.warn .etikett{color:var(--warn)} li.sperr .etikett{color:var(--akzent)} .etikett.neu{color:var(--ok)}
.leer{color:var(--leise);font-style:italic}
.knopf{display:inline-block;background:var(--akzent);color:#fff;text-decoration:none;padding:8px 14px;border-radius:10px;font-weight:600}
footer{color:var(--leise);font-size:.85rem;padding:10px 0 30px}
.nach-oben{text-align:right;margin:4px 0 6px;font-size:.85rem}.nach-oben a{text-decoration:none}
.liste.kompakt li{padding:7px 0;font-size:.92rem}
.liste.mini li{padding:5px 0;font-size:.82rem;gap:0;line-height:1.35}
.liste.mini li>span:last-child{color:var(--leise)}
details{margin:4px 0 8px}
summary{cursor:pointer;font-weight:600;font-size:.92rem;padding:6px 0;color:var(--text)}
summary::marker{color:var(--akzent)}
.karte-legende{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.9rem;margin:6px 0 10px}
.karte-legende label{display:flex;align-items:center;gap:6px;cursor:pointer}
.punkt{display:inline-block;width:12px;height:12px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px #0003}
.k-aktuell-bg{background:#d62839}.k-endet-bg{background:#f08ca0}.k-bald-bg{background:#e08a00}.k-autobahn-bg{background:#6a3fc4}
.k-aktuell,.k-endet{color:#d62839;font-weight:600}.k-bald{color:#b86e00;font-weight:600}
#karte-huelle{position:relative;height:460px;border-radius:12px;overflow:hidden;border:1px solid var(--linie);margin-bottom:14px;background:var(--bg)}
#karte{position:absolute;inset:0}
#karte-hinweis{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;text-align:center;padding:20px;background:var(--bg)}
#karte-hinweis p{max-width:460px;margin:0}
.stadion-icon{font-size:22px;line-height:26px;text-align:center;background:none;border:0}
.leaflet-popup-content{font:14px/1.45 system-ui,sans-serif;color:#1d1d1f}
@media (max-width:560px){#karte-huelle{height:380px}}
#veraltet{display:none;background:var(--warn-hell);color:var(--warn);border-radius:10px;padding:10px 14px;margin-bottom:14px;font-weight:600}
@media (max-width:560px){.liste.termine li{flex-direction:column;gap:2px}.wrap{padding:12px 16px}}
"""


def seite(titel, inhalt):
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(titel)}</title>
<meta name="description" content="Automatisch aktualisierte Infos für Junkersdorf, Müngersdorf und rund ums RheinEnergieSTADION: Termine, Verkehr, Baustellen, Meldungen.">
<style>{CSS}</style></head>
<body><div class="wrap">{inhalt}
<footer>Diese Seite wird stündlich automatisch aus öffentlichen Quellen zusammengestellt, ohne redaktionelle Prüfung und ohne Gewähr.
Maßgeblich sind immer die verlinkten Originalquellen. Keine Cookies, kein Tracking.<br>
<a href="impressum.html">Impressum</a> · <a href="datenschutz.html">Datenschutz</a> · <a href="index.html">Startseite</a></footer>
</div>
<script>
// Warnung, falls die automatische Aktualisierung ausgefallen ist (Stand älter als 3 Stunden)
(function(){{var stand={int(JETZT.timestamp() * 1000)},el=document.getElementById("veraltet");
if(el&&Date.now()-stand>3*3600*1000){{el.style.display="block";}}}})();
</script></body></html>"""


# ---------------------------------------------------------------- Ablauf


def versuche(name, fn, *args):
    try:
        return fn(*args)
    except Exception as ex:
        print(f"!! {name}: {ex}")
        return None


def main():
    termine = versuche("Stadion", stadion)
    vk = versuche("Verkehrskalender", verkehrskalender)
    ab = versuche("Autobahn", autobahn)
    bs = versuche("Baustellen", baustellen)
    w = versuche("Wetter", wetter)
    neue = (versuche("Polizei", pressemeldungen, "polizei", "Polizei Köln") or []) + \
           (versuche("Stadt", pressemeldungen, "stadt_presse", "Stadt Köln") or [])
    meldungen = archiv_aktualisieren(neue)
    kk = versuche("Karneval", karneval)
    AUSGABE.mkdir(exist_ok=True)
    karte_ok = versuche("Kartenbibliothek", leaflet_holen)
    sch = versuche("Schulen", schulen)

    kopf = f"""<header id="oben"><h1>{TITEL}</h1><span class="stand">Stand: {datum_de(HEUTE)}, {JETZT:%H:%M} Uhr</span></header>
<div id="veraltet">⚠️ Diese Seite wurde seit mehreren Stunden nicht aktualisiert. Die Angaben können veraltet sein.</div>
{wetter_html(w)}
<nav><a href="#stadion">🏟️ Stadion</a><a href="#veedel">🎭 Karneval &amp; Vereine</a><a href="#verkehr">🚗 Verkehr &amp; Baustellen</a><a href="#meldungen">📰 Meldungen</a><a href="#schulen">🏫 Schulen</a></nav>"""

    teile = [kopf, banner_html(termine or [])]
    teile.append(abschnitt("stadion", "Termine im RheinEnergieSTADION",
                           stadion_html(termine) if termine is not None else fehler_html("Der Stadion-Kalender"),
                           '<a href="https://www.rheinenergiestadion.de/termine">rheinenergiestadion.de</a>'))
    teile.append(abschnitt("veedel", "Karneval &amp; Vereine im Veedel",
                           karneval_html(kk) if kk is not None else fehler_html("Der Karnevalskalender"),
                           '<a href="https://koelnerkarneval.de/session/veranstaltungen">Sessionskalender Festkomitee Kölner Karneval</a>. '
                           f'Gezeigt werden kommende Termine der nächsten {MONATE_KARNEVAL} Monate, die Junkersdorf oder Müngersdorf betreffen.',
                           leer="Zurzeit keine Termine aus dem Veedel im Sessionskalender."))
    teile.append(abschnitt("verkehr", "Verkehr in und ums Veedel",
                           (karte_html(bs or [], ab) if karte_ok and bs is not None else "") + verkehr_html(vk, ab)
                           + (baustellen_html(bs) if bs is not None else "<h3>Baustellen im Veedel</h3>" + fehler_html("Das Baustellen-Verzeichnis")),
                           '<a href="https://www.stadt-koeln.de/leben-in-koeln/verkehr/verkehrskalender/">Verkehrskalender Stadt Köln</a>, '
                           '<a href="https://www.offenedaten-koeln.de/dataset/baustellen-koeln">Stadt Köln, Offene Daten</a> '
                           '(Datenlizenz Deutschland – Namensnennung – Version 2.0), '
                           '<a href="https://verkehr.autobahn.de">Die Autobahn GmbH des Bundes</a>. Karte: © OpenStreetMap-Mitwirkende'))
    teile.append(abschnitt("meldungen", "Meldungen aus dem Veedel", meldungen_html(meldungen),
                           '<a href="https://www.presseportal.de/blaulicht/nr/12415">Polizei Köln (Presseportal)</a>, '
                           '<a href="https://www.stadt-koeln.de/politik-und-verwaltung/presseservice/">Presseservice Stadt Köln</a>. '
                           f'Gezeigt werden Meldungen der letzten {TAGE_ARCHIV} Tage, die einen Ort aus dem Veedel nennen.',
                           leer=f"In den letzten {TAGE_ARCHIV} Tagen gab es keine Meldung, die das Veedel erwähnt."))
    teile.append(abschnitt("schulen", "Aus den Schulen", schulen_html(sch or []),
                           "Nachrichten-Feeds von " + ", ".join(SCHUL_FEEDS) +
                           f" (Beiträge der letzten {TAGE_SCHULEN} Tage). Die anderen Schulen bieten keinen Feed an."))

    AUSGABE.mkdir(exist_ok=True)
    (AUSGABE / "index.html").write_text(seite(TITEL, "\n".join(teile)), "utf-8")
    if termine:
        (AUSGABE / "stadion.ics").write_text(ics(termine), "utf-8")
    for name in ["impressum", "datenschutz"]:
        quelle = BASIS / "seiten" / f"{name}.html"
        if quelle.exists():
            (AUSGABE / f"{name}.html").write_text(seite(name.capitalize() + " – " + TITEL, quelle.read_text("utf-8")), "utf-8")
    (AUSGABE / ".nojekyll").write_text("")
    print(f"OK: {len(termine or [])} Termine, {len(kk or [])} Karneval, {len(sch or [])} Schule, {len(vk or [])} Stadtverkehr, {len(ab or [])} Autobahn, "
          f"{len(bs or [])} Baustellen, {len(meldungen)} Meldungen")


if __name__ == "__main__":
    main()

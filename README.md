# 🏆 TheRealTournament (TRT)

> Selbstgehosteter Turnierplaner für den **Schulsport** – Klassen spielen klassenweise oder in gemischten Teams gegeneinander. Ein Container, eine SQLite-Datenbank, fertig. 🎒⚽🏀🏐

![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![GHCR](https://img.shields.io/badge/Image-ghcr.io-2088FF?logo=github)
![DB](https://img.shields.io/badge/DB-SQLite-003B57?logo=sqlite)

---

## ✨ Features

| Feature | Beschreibung |
|---|---|
| 🌍 **Turnierformate** | Liga (Jeder gegen Jeden), K.o.-System mit Setzliste & Freilosen, Gruppenphase mit automatischer Finalrunde |
| 👥 **Teams & Klassen** | Teams mit Name, Klasse, Sportart, Farbe, Emoji und **Logo-Upload** 🖼️ |
| 🧮 **Live-Tabellen** | Punkte (konfigurierbar), Tordifferenz, Sortierung nach Regelwerk |
| ⏱️ **Zeitplan** | Automatische Ansetzung: Datum, Startzeit, Spieldauer, mehrere Plätze (Rotation) |
| 📅 **Kalender** | Übersicht aller terminierten Spiele + **iCal-Export (.ics)** für Handy |
| 📄 **PDF-Export** | Spielplan + Tabellen als druckfertiges PDF (A4 quer) |
| ⚙️ **Benutzerverwaltung** | Rollen: 👑 admin · 🧑‍🏫 lehrer · 👀 leser (z. B. für Schüler-Accounts) |
| 🎨 **5 Designs** | 🏟️ Sportplatz · 🌅 Sunset · 🌲 Wald · 🌙 Night · 🌸 Pastell – pro Benutzer gespeichert |
| 🐳 **Docker** | Ein Container, Image via GitHub Action auf `ghcr.io`, arm64-ready (DietPi!) |

---

## 🚀 Schnellstart (Docker)

```bash
docker run -d \
  --name trt \
  -p 8092:8000 \
  -v trt_data:/data \
  -e ADMIN_USER=admin \
  -e ADMIN_PASSWORD=geheim123 \
  --restart unless-stopped \
  ghcr.io/jbkunama1/trt-therealtournament:latest
```

👉 Dann im Browser öffnen: `http://server:8092` und mit `admin / geheim123` einloggen –
**Passwort danach sofort ändern!** 🔑

## 🐙 Portainer-Stack

```yaml
services:
  trt:
    image: ghcr.io/jbkunama1/trt-therealtournament:latest
    container_name: therealtournament
    restart: unless-stopped
    ports:
      - "8092:8000"
    volumes:
      - trt_data:/data          # SQLite-DB + hochgeladene Logos
    environment:
      ADMIN_USER: admin
      ADMIN_PASSWORD: changeme  # nur beim ersten Start relevant
      SEED_DEMO: "true"         # Demo-Teams anlegen (7a-9b 🦁🐯🦅🦈)
      TZ: Europe/Berlin
    networks:
      - higfishNetwork

networks:
  higfishNetwork:
    external: true            # vorhandenes Docker-Netzwerk wiederverwenden

volumes:
  trt_data:
```

> Ohne externes Netzwerk: den `networks`-Block einfach weglassen.

## 🔧 Umgebungsvariablen

| Variable | Standard | Bedeutung |
|---|---|---|
| `ADMIN_USER` | `admin` | Erster Login (wird nur beim **ersten** Start angelegt) |
| `ADMIN_PASSWORD` | `bitte-aendern!` | Initial-Passwort ⚠️ |
| `SEED_DEMO` | `true` | Legt 6 Demo-Teams an (`false` zum Deaktivieren) |
| `DATA_DIR` | `/data` | Speicherort für SQLite (`trt.db`) & Logos (`uploads/`) |
| `TZ` | – | Zeitzone, z. B. `Europe/Berlin` |

## 🔄 Workflow: Image bauen

Jeder Push auf `main` (oder Tag `v1.2.3`) baut automatisch:

- `ghcr.io/jbkunama1/trt-therealtournament:latest`
- `…:sha-<commit>`
- `…:1.2.3` (bei Git-Tags `v*`)

> Hinweis: Das GHCR-Package im eigenen Account ggf. einmal auf **public** stellen,
> damit Portainer ohne Auth ziehen kann (Package Settings → Change visibility).

## 🧑‍🏫 Typischer Ablauf im Unterricht

1. 🧑‍🏫 Lehrer legt Turnier an (z. B. „Winterturnier 8er“, Fußball, Gruppenmodus)
2. 👥 Teams aus den Klassen anlegen (mit Wappentier-Emoji 🦁 + Logo der Klasse)
3. ⚙️ Teams zuweisen → **Spielplan generieren** → ⏱️ Zeitplan setzen
4. 👀 Schüler bekommen `leser`-Accounts und verfolgen alles am Handy 📱
5. 📝 Ergebnisse live eintragen · 📄 PDF aushängen · 📅 .ics ins Handy

## 🗺️ Roadmap / Erweiterungsideen

- [ ] 📣 Öffentliche Live-Ansicht ohne Login (Read-only-Link pro Turnier)
- [ ] 🥉 Spiel um Platz 3 · Doppel-K.o.
- [ ] 🔄 Schweizer System (Chess-Style) für große Gruppen
- [ ] 📱 QR-Code zur öffentlichen Turnierseite
- [ ] 🏅 Urkunden-Generator (PDF) für die Top 3
- [ ] 👶 Pausensport-Modus: spontane Mini-Turniere
- [ ] 🌐 LDAP/OAuth-Anbindung für Schul-Accounts

## 📁 Projektstruktur

```
├── app/
│   ├── main.py            # FastAPI-Backend (API, Turnierlogik, Exporte)
│   └── static/            # Frontend (Vanilla JS, keine Build-Tools)
├── Dockerfile             # python:3.12-slim, läuft auf amd64 + arm64
├── requirements.txt
└── .github/workflows/     # Build → ghcr.io
```

## ⚖️ Lizenz

MIT – freu mich über ⭐ & Feedback!

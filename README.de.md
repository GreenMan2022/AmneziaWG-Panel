# AmneziaWG Panel

**🌐 In anderen Sprachen lesen:**
[🇬🇧 English](README.md) | [🇷🇺 Русский](README.ru.md) | [🇩🇪 Deutsch](README.de.md) | [🇫🇷 Français](README.fr.md) | [🇨🇳 中文](README.zh.md) | [🇯🇵 日本語](README.ja.md) | [🇰🇷 한국어](README.ko.md) | [🇸🇦 العربية](README.ar.md)

Web-Panel zur Verwaltung eines [AmneziaWG](https://github.com/amnezia-vpn/amneziawg) (AWG) VPN-Servers mit Authentifizierung, Ausstellung von Client-Konfigurationen, QR-Codes, Gültigkeitsdauern und einem Detektor für die Weitergabe von Konfigurationen.

- **panel.py** — Web-Panel (nur Python-Standardbibliothek, keine Abhängigkeiten). Standardport `8000`, geheimer Admin-Pfad `/1q2w3e4r` (alles andere liefert 404).
- **panelctl** — CLI-Tool: Hinzufügen/Verlängern/Entfernen von Clients, Status, Statistiken.
- **install.sh** — stellt das gesamte Projekt mit einem Befehl auf einem neuen Server bereit.
- **install_amneziawg.sh** — Installationsprogramm für AmneziaWG 2.0 (nicht-interaktiver Modus unterstützt).
- **connection_limit.sh** — Detektor und Blockierung der Konfigurationsweitergabe (mehrere Geräte mit einem Schlüssel).

## Schnellstart

Auf einem frischen VDS (Ubuntu 24.04 / Debian 12+):

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/GreenMan2022/AmneziaWG-Panel/ panel
cd panel
sudo bash install.sh
```

Die Installation dauert einige Minuten: AmneziaWG wird installiert, zufällige Panel-Geheimnisse werden generiert, die systemd-Dienste `awg-panel` und `awg-connection-limit` werden erstellt. Am Ende gibt das Skript die Panel-Adresse, den Admin-Login und das Passwort aus.

### Optionen von install.sh

| Option | Beschreibung | Standard |
|---|---|---|
| `--port=N` | UDP-Port des AWG-Servers | `443` |
| `--subnet=CIDR` | Tunnel-Subnetz | `10.9.9.1/24` |
| `--route=all\|amnezia\|custom:CIDR` | Routing-Modus | `all` |
| `--preset=default\|mobile` | Verschleierungs-Preset | `mobile` |
| `--no-cps` / `--cps` | Parameter I1 (CPS) ein/aus | `--no-cps` |
| `--skip-awg` | Installiertes AWG unangetastet lassen, nur Panel neu bereitstellen | — |

Beispiel: `sudo bash install.sh --port=51820 --subnet=10.0.0.1/24`

## Verwendung

Admin-Panel: `http://<IP>:8000/1q2w3e4r` (der geheime Pfad kann in `panel.py` geändert werden, Konstante `ADMIN_PATH`).

CLI (als root):

```bash
sudo panelctl status              # Status des Panels und der Dienste
sudo panelctl add <name>          # Client ausstellen (30 Tage)
sudo panelctl extend <name> <tage> # verlängern
sudo panelctl list                # Liste der Clients
sudo panelctl blocked             # wegen Weitergabe blockierte Clients
sudo panelctl remove <name>       # Client entfernen
sudo panelctl config              # Panel-Konfiguration
```

## Sicherheit

- Admin-Passwort und Salts werden bei der Installation **zufällig generiert** und in `/root/awg/panel.env` (chmod 600) gespeichert. Das Panel liest sie aus Umgebungsvariablen (`PANEL_ADMIN_USER`, `PANEL_ADMIN_PASSWORD`, `PANEL_HASH_SALT`, `PANEL_CLIENT_AUTH_SALT`). Ohne Variablen werden eingebaute Werte **nur für die Entwicklung** verwendet — auf einem Produktionsserver dürfen sie nicht eingesetzt werden.
- Das Verzeichnis `/root/awg/` enthält die privaten Schlüssel des Servers und der Clients. Es ist über `.gitignore` von git ausgeschlossen — veröffentlichen Sie es niemals.
- Der Admin-Pfad `/1q2w3e4r` verbirgt die Oberfläche vor Scannern (die Wurzel liefert 404), ersetzt aber kein Passwort: schränken Sie den Zugriff bei Bedarf zusätzlich ein (nginx, Firewall).

## Projektstruktur

```
install.sh               # Bereitstellung auf einem frischen VDS
install_amneziawg.sh     # AmneziaWG-2.0-Installateur (Fork von amneziawg-installer)
panel.py                 # Web-Panel (stdlib Python)
panelctl                 # CLI-Verwaltungstool
connection_limit.sh      # Detektor für Konfigurationsweitergabe
```

## Lizenz

Das Projekt basiert auf [amneziawg-installer](https://github.com/bivlked/amneziawg-installer).

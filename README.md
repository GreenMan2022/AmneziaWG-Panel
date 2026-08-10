# AmneziaWG Panel

**🌐 Read this in other languages:**
[🇬🇧 English](README.md) | [🇷🇺 Русский](README.ru.md) | [🇩🇪 Deutsch](README.de.md) | [🇫🇷 Français](README.fr.md) | [🇨🇳 中文](README.zh.md) | [🇯🇵 日本語](README.ja.md) | [🇰🇷 한국어](README.ko.md) | [🇸🇦 العربية](README.ar.md)

Web panel for managing an [AmneziaWG](https://github.com/amnezia-vpn/amneziawg) (AWG) VPN server with authentication, client config generation, QR codes, expiration dates and a config-sharing detector.

- **panel.py** — web panel (Python standard library only, no dependencies). Default port `8000`, random secret admin path stored in `panel.conf` (`admin_path`, everything else returns 404).
- **panelctl** — CLI tool: add/extend/remove clients, status, whitelist, password change, statistics.
- **install.sh** — deploys the whole project on a new server with a single command.
- **install_amneziawg.sh** — AmneziaWG 2.0 installer (non-interactive mode supported).
- **connection_limit.sh** — config-sharing detector and blocker (multiple devices on a single key).

## Quick Start

On a fresh VDS (Ubuntu 24.04 / Debian 12+):

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/GreenMan2022/AmneziaWG-Panel/ panel
cd panel
sudo bash install.sh
```

Installation takes a few minutes: AmneziaWG gets installed, random panel secrets are generated, the panel port is opened in UFW, a fail2ban jail protects the panel login, dnsmasq provides DNS logs for the `/dns` page, and the `awg-panel` and `awg-connection-limit` systemd services are created. When finished, the script prints the panel address (with a random secret path), admin login and password.

### install.sh options

| Option | Description | Default |
|---|---|---|
| `--port=N` | AWG server UDP port | `443` |
| `--subnet=CIDR` | Tunnel subnet | `10.9.9.1/24` |
| `--route=all\|amnezia\|custom:CIDR` | Routing mode | `all` |
| `--preset=default\|mobile` | Obfuscation preset | `mobile` |
| `--no-cps` / `--cps` | Enable/disable the I1 (CPS) parameter | `--no-cps` |
| `--panel-port=N` | Web panel TCP port | `8000` |
| `--skip-awg` | Leave the installed AWG untouched, redeploy only the panel | — |

Example: `sudo bash install.sh --port=51820 --subnet=10.0.0.1/24`

## Usage

Admin panel: `http://<IP>:<port>/<secret_path>` (port comes from `panel.conf`, secret path is the `admin_path` value, randomly generated during install).

CLI (as root):

```bash
sudo panelctl status              # panel and service status
sudo panelctl add <name>          # create a client (30-day period)
sudo panelctl extend <name> <days> # extend
sudo panelctl list                # client list
sudo panelctl blocked             # blocked for sharing
sudo panelctl remove <name>       # remove a client
sudo panelctl config              # panel config
sudo panelctl whitelist           # list sharing-block exclusions
sudo panelctl whitelist add <name|IP|CIDR>   # add an exclusion
sudo panelctl whitelist remove <entry>       # remove an exclusion
sudo panelctl passwd              # change the admin password
```

## Security

- Admin password and salts are **randomly generated** during installation and stored in `/root/awg/panel.env` (chmod 600). The panel reads them from environment variables (`PANEL_ADMIN_USER`, `PANEL_ADMIN_PASSWORD`, `PANEL_HASH_SALT`, `PANEL_CLIENT_AUTH_SALT`). Without these variables, built-in values are used **for development only** — they must not be used on a production server.
- The `/root/awg/` directory contains the server and client private keys. It is excluded from git via `.gitignore` — never publish it.
- The secret admin path (`admin_path` in `panel.conf`, randomly generated during install) hides the interface from scanners (the root returns 404), but it is not a substitute for a password: additionally restrict access (nginx, firewall) if needed.
- Failed login attempts are written to `/var/log/awg/panel_auth.log`; fail2ban blocks an IP after 5 attempts within 10 minutes (jail `awg-panel`).
- The panel port (`--panel-port`, default 8000) is opened in UFW automatically.

## Project Structure

```
install.sh               # deployment on a fresh VDS
install_amneziawg.sh     # AmneziaWG 2.0 installer (fork of amneziawg-installer)
panel.py                 # web panel (stdlib Python)
panelctl                 # CLI management tool
connection_limit.sh      # config-sharing detector
```

## License

The project is based on [amneziawg-installer](https://github.com/bivlked/amneziawg-installer).

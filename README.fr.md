# AmneziaWG Panel

**🌐 Lire dans d'autres langues :**
[🇬🇧 English](README.md) | [🇷🇺 Русский](README.ru.md) | [🇩🇪 Deutsch](README.de.md) | [🇫🇷 Français](README.fr.md) | [🇨🇳 中文](README.zh.md) | [🇯🇵 日本語](README.ja.md) | [🇰🇷 한국어](README.ko.md) | [🇸🇦 العربية](README.ar.md)

Panneau web de gestion d'un serveur VPN [AmneziaWG](https://github.com/amnezia-vpn/amneziawg) (AWG) avec authentification, délivrance de configurations client, codes QR, dates d'expiration et détecteur de partage de configuration.

- **panel.py** — panneau web (bibliothèque standard Python uniquement, sans dépendances). Port par défaut `8000`, chemin secret d'administration `/1q2w3e4r` (tout le reste renvoie 404).
- **panelctl** — outil CLI : ajout/prolongation/suppression de clients, statut, statistiques.
- **install.sh** — déploie tout le projet sur un nouveau serveur en une seule commande.
- **install_amneziawg.sh** — installateur d'AmneziaWG 2.0 (mode non interactif pris en charge).
- **connection_limit.sh** — détecteur et blocage du partage de configuration (plusieurs appareils avec une seule clé).

## Démarrage rapide

Sur un VDS vierge (Ubuntu 24.04 / Debian 12+) :

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/GreenMan2022/AmneziaWG-Panel/ panel
cd panel
sudo bash install.sh
```

L'installation prend quelques minutes : AmneziaWG est installé, des secrets aléatoires sont générés, les services systemd `awg-panel` et `awg-connection-limit` sont créés. À la fin, le script affiche l'adresse du panneau, le login et le mot de passe administrateur.

### Options d'install.sh

| Option | Description | Défaut |
|---|---|---|
| `--port=N` | Port UDP du serveur AWG | `443` |
| `--subnet=CIDR` | Sous-réseau du tunnel | `10.9.9.1/24` |
| `--route=all\|amnezia\|custom:CIDR` | Mode de routage | `all` |
| `--preset=default\|mobile` | Préréglage d'obfuscation | `mobile` |
| `--no-cps` / `--cps` | Activer/désactiver le paramètre I1 (CPS) | `--no-cps` |
| `--skip-awg` | Ne pas toucher à l'AWG installé, redéployer uniquement le panneau | — |

Exemple : `sudo bash install.sh --port=51820 --subnet=10.0.0.1/24`

## Utilisation

Panneau d'administration : `http://<IP>:8000/1q2w3e4r` (le chemin secret peut être modifié dans `panel.py`, constante `ADMIN_PATH`).

CLI (en tant que root) :

```bash
sudo panelctl status              # statut du panneau et des services
sudo panelctl add <nom>           # délivrer un client (30 jours)
sudo panelctl extend <nom> <jours> # prolonger
sudo panelctl list                # liste des clients
sudo panelctl blocked             # bloqués pour partage
sudo panelctl remove <nom>        # supprimer un client
sudo panelctl config              # configuration du panneau
```

## Sécurité

- Le mot de passe administrateur et les sels sont **générés aléatoirement** à l'installation et stockés dans `/root/awg/panel.env` (chmod 600). Le panneau les lit depuis les variables d'environnement (`PANEL_ADMIN_USER`, `PANEL_ADMIN_PASSWORD`, `PANEL_HASH_SALT`, `PANEL_CLIENT_AUTH_SALT`). Sans variables, des valeurs intégrées sont utilisées **uniquement pour le développement** — elles ne doivent pas être employées sur un serveur de production.
- Le répertoire `/root/awg/` contient les clés privées du serveur et des clients. Il est exclu de git via `.gitignore` — ne le publiez jamais.
- Le chemin d'administration `/1q2w3e4r` masque l'interface aux scanners (la racine renvoie 404), mais ce n'est pas un substitut au mot de passe : restreignez aussi l'accès (nginx, pare-feu) si nécessaire.

## Structure du projet

```
install.sh               # déploiement sur un nouveau VDS
install_amneziawg.sh     # installateur d'AmneziaWG 2.0 (fork d'amneziawg-installer)
panel.py                 # panneau web (stdlib Python)
panelctl                 # outil de gestion CLI
connection_limit.sh      # détecteur de partage de configuration
```

## Licence

Le projet est basé sur [amneziawg-installer](https://github.com/bivlked/amneziawg-installer).

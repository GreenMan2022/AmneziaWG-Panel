# AmneziaWG Panel

**🌐 Read this in other languages:**  
[🇷🇺 Русский](README.ru.md) | [🇩🇪 Deutsch](README.de.md) | [🇪🇸 Español](README.es.md) | [🇫🇷 Français](README.fr.md) | [🇨🇳 中文](README.zh.md)

Веб-панель управления VPN-сервером [AmneziaWG](https://github.com/amnezia-vpn/amneziawg) (AWG) с аутентификацией, выдачей клиентских конфигов, QR-кодов, управлением сроками действия и детектором раздачи конфига.

---

## 📦 Компоненты

| Компонент | Описание |
|-----------|----------|
| **panel.py** | Веб-панель на чистом Python (без зависимостей). Порт `8000`, админ-путь `/1q2w3e4r` (всё остальное — 404) |
| **panelctl** | CLI-инструмент для управления клиентами: добавление, продление, удаление, статус, статистика |
| **install.sh** | Универсальный установщик для быстрого развёртывания на новом сервере |
| **install_amneziawg.sh** | Установщик AmneziaWG 2.0 (форк [amneziawg-installer](https://github.com/bivlked/amneziawg-installer)) |
| **connection_limit.sh** | Детектор и блокировка раздачи конфига (обнаружение нескольких устройств по одному ключу) |

---

## 🚀 Быстрый старт

На чистом VDS (Ubuntu 24.04 / Debian 12+):

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/GreenMan2022/AmneziaWG-Panel/ panel
cd panel
sudo bash install.sh
---

## Установка занимает несколько минут:

    Устанавливается AmneziaWG
    Генерируются случайные секреты панели
    Создаются systemd-сервисы awg-panel и awg-connection-limit

По завершении скрипт выведет адрес панели, логин и пароль администратора.

# AmneziaWG Panel

**🌐 Читать на других языках:**
[🇬🇧 English](README.md) | [🇷🇺 Русский](README.ru.md) | [🇩🇪 Deutsch](README.de.md) | [🇫🇷 Français](README.fr.md) | [🇨🇳 中文](README.zh.md) | [🇯🇵 日本語](README.ja.md) | [🇰🇷 한국어](README.ko.md) | [🇸🇦 العربية](README.ar.md)

Веб-панель управления VPN-сервером [AmneziaWG](https://github.com/amnezia-vpn/amneziawg) (AWG) с аутентификацией, выдачей клиентских конфигов, QR-кодов, сроков действия и детектором раздачи конфига.

- **panel.py** — веб-панель (только стандартная библиотека Python, без зависимостей). Порт по умолчанию `8000`, секретный путь админки `/1q2w3e4r` (всё остальное отдаёт 404).
- **panelctl** — CLI-инструмент: добавление/продление/удаление клиентов, статус, статистика.
- **install.sh** — развёртывание всего проекта на новом сервере одной командой.
- **install_amneziawg.sh** — установщик AmneziaWG 2.0 (неинтерактивный режим поддерживается).
- **connection_limit.sh** — детектор и блокировка раздачи конфига (несколько устройств с одного ключа).

## Быстрый старт

На чистом VDS (Ubuntu 24.04 / Debian 12+):

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/GreenMan2022/AmneziaWG-Panel/ panel
cd panel
sudo bash install.sh
```

Установка занимает несколько минут: ставится AmneziaWG, генерируются случайные секреты панели, открывается порт панели в UFW, ставится fail2ban-джейл на логин панели и dnsmasq для логов DNS, создаются systemd-сервисы `awg-panel` и `awg-connection-limit`. По завершении скрипт выведет адрес панели (со случайным секретным путём), логин и пароль администратора.

### Опции install.sh

| Опция | Описание | По умолчанию |
|---|---|---|
| `--port=N` | UDP-порт сервера AWG | `443` |
| `--subnet=CIDR` | Подсеть туннеля | `10.9.9.1/24` |
| `--route=all\|amnezia\|custom:CIDR` | Режим маршрутизации | `all` |
| `--preset=default\|mobile` | Пресет обфускации | `mobile` |
| `--no-cps` / `--cps` | Вкл/выкл параметр I1 (CPS) | `--no-cps` |
| `--panel-port=N` | TCP-порт веб-панели | `8000` |
| `--skip-awg` | Не трогать установленный AWG, переразвернуть только панель | — |

Пример: `sudo bash install.sh --port=51820 --subnet=10.0.0.1/24`

## Использование

Админ-панель: `http://<IP>:<порт>/<секретный_путь>` (порт из `panel.conf`, секретный путь — значение `admin_path`, генерируется случайно при установке).

CLI (от root):

```bash
sudo panelctl status              # статус панели и сервисов
sudo panelctl add <имя>           # выдать клиента (срок 30 дней)
sudo panelctl extend <имя> <дни>  # продлить
sudo panelctl list                # список клиентов
sudo panelctl blocked             # заблокированные за раздачу
sudo panelctl remove <имя>        # удалить клиента
sudo panelctl config              # конфиг панели
sudo panelctl whitelist           # список исключений из блокировки
sudo panelctl whitelist add <имя|IP|CIDR>   # добавить исключение
sudo panelctl whitelist remove <запись>     # убрать исключение
sudo panelctl passwd              # сменить пароль админа
```

## Безопасность

- Пароль админа и соли **генерируются случайно** при установке и хранятся в `/root/awg/panel.env` (chmod 600). Панель читает их из переменных окружения (`PANEL_ADMIN_USER`, `PANEL_ADMIN_PASSWORD`, `PANEL_HASH_SALT`, `PANEL_CLIENT_AUTH_SALT`). Без переменных используются встроенные значения **только для разработки** — на боевом сервере они не должны применяться.
- Директория `/root/awg/` содержит приватные ключи сервера и клиентов. Она исключена из git через `.gitignore` — никогда не публикуйте её.
- Секретный путь админ-панели (`admin_path` в `panel.conf`, генерируется случайно при установке) скрывает интерфейс от сканеров (корень отдаёт 404), но это не замена паролю: дополнительно ограничьте доступ (nginx, firewall) при необходимости.
- Неудачные попытки логина пишутся в `/var/log/awg/panel_auth.log`, fail2ban блокирует IP после 5 попыток за 10 минут (джейл `awg-panel`).
- Порт панели (`--panel-port`, по умолчанию 8000) открывается в UFW автоматически.

## Структура проекта

```
install.sh               # развёртывание на новом VDS
install_amneziawg.sh     # установщик AmneziaWG 2.0 (форк amneziawg-installer)
panel.py                 # веб-панель (stdlib Python)
panelctl                 # CLI-инструмент управления
connection_limit.sh      # детектор раздачи конфига
```

## Лицензия

Проект основан на [amneziawg-installer](https://github.com/bivlked/amneziawg-installer).

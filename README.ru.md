# AmneziaWG Panel

**🌐 Читать на других языках:**  
[🇬🇧 English](README.md) | [🇩🇪 Deutsch](README.de.md) | [🇪🇸 Español](README.es.md) | [🇫🇷 Français](README.fr.md) | [🇨🇳 中文](README.zh.md)

Веб-панель управления VPN-сервером AmneziaWG (AWG) с аутентификацией, выдачей клиентских конфигов, QR-кодов, сроков действия и детектором раздачи конфига.

### Быстрый старт

На чистом VDS (Ubuntu 24.04 / Debian 12+):

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/GreenMan2022/AmneziaWG-Panel/ panel
cd panel
sudo bash install.sh
```
Установка занимает несколько минут: ставится AmneziaWG, генерируются случайные секреты панели, создаются systemd-сервисы awg-panel и awg-connection-limit.
По завершении скрипт выведет адрес панели, логин и пароль администратора.

Опции install.sh
Опция	Описание	По умолчанию
--port=N	UDP-порт сервера AWG	443
--subnet=CIDR	Подсеть туннеля	10.9.9.1/24
--route=all|amnezia|custom:CIDR	Режим маршрутизации	all
--preset=default|mobile	Пресет обфускации	mobile
--no-cps / --cps	Вкл/выкл параметр I1 (CPS)	--no-cps
--skip-awg	Не трогать установленный AWG, переразвернуть только панель	—

Пример: sudo bash install.sh --port=51820 --subnet=10.0.0.1/24
Использование

Админ-панель: http://<IP>:8000/1q2w3e4r (секретный путь можно изменить в panel.py, константа ADMIN_PATH).

CLI (от root):
bash

sudo panelctl status              # статус панели и сервисов
sudo panelctl add <имя>           # выдать клиента (срок 30 дней)
sudo panelctl extend <имя> <дни>  # продлить
sudo panelctl list                # список клиентов
sudo panelctl blocked             # заблокированные за раздачу
sudo panelctl remove <имя>        # удалить клиента
sudo panelctl config              # конфиг панели

Безопасность

    Пароль админа и соли генерируются случайно при установке и хранятся в /root/awg/panel.env (chmod 600).

    Директория /root/awg/ содержит приватные ключи сервера и клиентов. Никогда не публикуйте её.

    Путь админ-панели /1q2w3e4r скрывает интерфейс от сканеров, но это не замена паролю.

Структура проекта
text

install.sh               # развёртывание на новом VDS
install_amneziawg.sh     # установщик AmneziaWG 2.0
panel.py                 # веб-панель (stdlib Python)
panelctl                 # CLI-инструмент управления
connection_limit.sh      # детектор раздачи конфига

Лицензия

Проект основан на amneziawg-installer.

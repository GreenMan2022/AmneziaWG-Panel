#!/usr/bin/env bash
# =============================================================================
# install.sh — Развёртывание AmneziaWG Panel на новом VDS.
#
# Что делает:
#   1) Устанавливает AmneziaWG 2.0 через install_amneziawg.sh (неинтерактивно);
#   2) Копирует panel.py, panelctl и connection_limit.sh в /root и /root/awg;
#   3) Генерирует случайные секреты панели (пароль админа, соли) -> /root/awg/panel.env;
#   4) Создаёт конфиг панели /root/awg/panel.conf;
#   5) Открывает порт панели в UFW и ставит fail2ban-джейл на её логин;
#   6) Устанавливает dnsmasq для логов DNS (страница /dns в панели);
#   7) Регистрирует и запускает systemd-сервисы (панель + детектор раздачи).
#
# Использование: sudo bash install.sh [ОПЦИИ]
#
# Опции (передают в install_amneziawg.sh, значения по умолчанию — как в "mobile"-сетапе):
#   --port=N        UDP порт сервера (по умолчанию 443)
#   --subnet=N      Подсеть туннеля (по умолчанию 10.9.9.1/24)
#   --route=all|amnezia|custom:CIDR
#   --preset=default|mobile
#   --no-cps|--cps  Управление параметром I1 (по умолчанию --no-cps)
#   --panel-port=N  TCP порт веб-панели (по умолчанию 8000)
#   --skip-awg      Не переустанавливать AmneziaWG (только переразвернуть панель)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
die()         { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWG_DIR="/root/awg"
PANEL_SCRIPT="/root/panel.py"
PANELCTL="/root/panelctl"
CONN_LIMIT_SRC="$DIR/connection_limit.sh"
CONN_LIMIT_DST="$AWG_DIR/connection_limit.sh"
ENV_FILE="$AWG_DIR/panel.env"
CONF_FILE="$AWG_DIR/panel.conf"
SERVICE_NAME="awg-panel"
LIMIT_SERVICE_NAME="awg-connection-limit"

# --- Разбор аргументов -------------------------------------------------------
AWG_PORT=443
AWG_SUBNET="10.9.9.1/24"
ROUTE_FLAG="--route-all"
PRESET_FLAG="--preset=mobile"
CPS_FLAG="--no-cps"
PANEL_PORT=8000
SKIP_AWG=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port=*)  AWG_PORT="${1#*=}" ;;
        --subnet=*) AWG_SUBNET="${1#*=}" ;;
        --route=all)        ROUTE_FLAG="--route-all" ;;
        --route=amnezia)    ROUTE_FLAG="--route-amnezia" ;;
        --route=custom:*)   ROUTE_FLAG="--route-custom=${1#*=}" ;;
        --preset=*) PRESET_FLAG="--preset=${1#*=}" ;;
        --no-cps)   CPS_FLAG="--no-cps" ;;
        --cps)      CPS_FLAG="" ;;
        --panel-port=*) PANEL_PORT="${1#*=}" ;;
        --skip-awg) SKIP_AWG=1 ;;
        -h|--help)
            sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) die "Неизвестный аргумент: $1 (см. --help)" ;;
    esac
    shift
done

# --- Проверки ----------------------------------------------------------------
[[ $EUID -eq 0 ]] || die "Запустите от root: sudo bash install.sh"
[[ -f "$DIR/install_amneziawg.sh" ]] || die "Не найден $DIR/install_amneziawg.sh"
[[ -f "$DIR/panel.py" ]] || die "Не найден $DIR/panel.py"

# --- 1. Установка AmneziaWG --------------------------------------------------
if [[ $SKIP_AWG -eq 1 ]]; then
    log_warn "--skip-awg: пропускаю установку AmneziaWG"
else
    log_info "Устанавливаю AmneziaWG 2.0 (порт=$AWG_PORT, подсеть=$AWG_SUBNET)..."
    bash "$DIR/install_amneziawg.sh" \
        "--port=$AWG_PORT" \
        "--subnet=$AWG_SUBNET" \
        "$ROUTE_FLAG" \
        "$PRESET_FLAG" \
        "$CPS_FLAG" \
        --disallow-ipv6 \
        --yes
fi

mkdir -p "$AWG_DIR"

# --- 2. Развёртывание файлов панели ------------------------------------------
log_info "Развёртываю файлы панели..."
install -m 644 "$DIR/panel.py" "$PANEL_SCRIPT"
install -m 755 "$DIR/panelctl" "$PANELCTL"
if [[ -f "$CONN_LIMIT_SRC" ]]; then
    install -m 700 "$CONN_LIMIT_SRC" "$CONN_LIMIT_DST"
    log_info "Детектор раздачи конфига установлен: $CONN_LIMIT_DST"
else
    log_warn "Не найден $CONN_LIMIT_SRC — детектор раздачи не установлен"
fi

# --- 3. Секреты панели -------------------------------------------------------
if [[ -f "$ENV_FILE" ]]; then
    log_warn "$ENV_FILE уже существует — оставляю текущие секреты"
else
    log_info "Генерирую секреты панели..."
    ADMIN_USER="admin"
    ADMIN_PASS="$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 16)"
    HASH_SALT="$(tr -dc 'a-f0-9' < /dev/urandom | head -c 32)"
    CLIENT_SALT="$(tr -dc 'a-f0-9' < /dev/urandom | head -c 32)"
    umask 177
    cat > "$ENV_FILE" << EOF
# Сгенерировано install.sh — НЕ выкладывайте этот файл и не удаляйте.
# Пароль админа: $ADMIN_PASS
PANEL_ADMIN_USER=$ADMIN_USER
PANEL_ADMIN_PASSWORD=$ADMIN_PASS
PANEL_HASH_SALT=$HASH_SALT
PANEL_CLIENT_AUTH_SALT=$CLIENT_SALT
EOF
    chmod 600 "$ENV_FILE"
    log_success "Пароль администратора панели: $ADMIN_PASS"
    log_warn  "Сохраните его — он больше нигде не будет показан."
fi

# --- 4. Конфиг панели (используется panel.py и panelctl) ---------------------
if [[ ! -f "$CONF_FILE" ]]; then
    cat > "$CONF_FILE" << EOF
# AmneziaWG Panel configuration
host=0.0.0.0
port=$PANEL_PORT
require_auth=true
session_timeout=3600
default_expires=30d
show_qr_codes=true
allow_config_download=true
allow_json_export=true
theme=dark
items_per_page=25
auto_refresh_interval=30
enable_share_links=true
enable_client_notes=true
show_connection_stats=true
EOF
    chmod 600 "$CONF_FILE"
else
    if grep -q '^port=' "$CONF_FILE"; then
        sed -i "s/^port=.*/port=$PANEL_PORT/" "$CONF_FILE"
    else
        echo "port=$PANEL_PORT" >> "$CONF_FILE"
    fi
fi

# --- 4.1 UFW: открыть порт панели --------------------------------------------
if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -q active; then
    log_info "Открываю порт панели ${PANEL_PORT}/tcp в UFW..."
    if ! ufw status 2>/dev/null | grep -q "^${PANEL_PORT}/tcp"; then
        ufw allow "${PANEL_PORT}/tcp" comment "AmneziaWG Panel" >/dev/null 2>&1 \
            && log_success "UFW: разрешён ${PANEL_PORT}/tcp (панель)"
    fi
fi

# --- 4.2 fail2ban: защита логина панели --------------------------------------
if command -v fail2ban-client &>/dev/null; then
    log_info "Настраиваю fail2ban-джейл для панели..."
    mkdir -p /etc/fail2ban/filter.d
    cat > /etc/fail2ban/filter.d/awg-panel.conf << EOF
[Definition]
failregex = Failed login for user .* from <HOST>
ignoreregex =
EOF
    cat > /etc/fail2ban/jail.d/awg-panel.conf << EOF
[awg-panel]
enabled = true
port = $PANEL_PORT
filter = awg-panel
logpath = /var/log/awg/panel_auth.log
maxretry = 5
findtime = 10m
bantime = 1h
banaction = ufw
EOF
    touch /var/log/awg/panel_auth.log
    chmod 600 /var/log/awg/panel_auth.log
    if command -v systemctl &>/dev/null; then
        systemctl restart fail2ban >/dev/null 2>&1 || true
    fi
    log_success "fail2ban: джейл awg-panel активен (макс. 5 попыток / 10 мин)"
fi

# --- 4.3 dnsmasq: логи DNS для страницы /dns ----------------------------------
if ! command -v dnsmasq &>/dev/null; then
    log_info "Устанавливаю dnsmasq (логи DNS для панели)..."
    if command -v apt-get &>/dev/null; then
        DEBIAN_FRONTEND=noninteractive apt-get install -y dnsmasq >/dev/null 2>&1 \
            && log_success "dnsmasq установлен" \
            || log_warn "Не удалось установить dnsmasq — страница /dns будет пустой"
    fi
fi
if command -v dnsmasq &>/dev/null; then
    cat > /etc/dnsmasq.d/awg.conf << EOF
# Создан install.sh: логи DNS для панели (страница /dns).
interface=awg0
bind-interfaces
listen-address=${AWG_SUBNET%/*}
log-queries
log-facility=/var/log/dnsmasq.log
server=1.1.1.1
server=8.8.8.8
EOF
    systemctl restart dnsmasq >/dev/null 2>&1 || true
    log_success "dnsmasq: логи DNS включены (/var/log/dnsmasq.log)"
fi

# --- 5. systemd-сервисы ------------------------------------------------------
log_info "Регистрирую systemd-сервисы..."

cat > "/etc/systemd/system/$SERVICE_NAME.service" << EOF
[Unit]
Description=AmneziaWG Web Panel
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
EnvironmentFile=$ENV_FILE
ExecStart=/usr/bin/python3 $PANEL_SCRIPT
Restart=always
RestartSec=5
StandardOutput=append:/var/log/awg-panel.log
StandardError=append:/var/log/awg-panel.log

[Install]
WantedBy=multi-user.target
EOF

if [[ -f "$CONN_LIMIT_DST" ]]; then
    cat > "/etc/systemd/system/$LIMIT_SERVICE_NAME.service" << EOF
[Unit]
Description=AmneziaWG config-sharing detector and blocker
After=network-online.target awg-quick@awg0.service
Wants=awg-quick@awg0.service

[Service]
Type=simple
ExecStart=$CONN_LIMIT_DST
Restart=on-failure
RestartSec=5
Environment=IFACE=awg0

[Install]
WantedBy=multi-user.target
EOF
fi

mkdir -p /var/log/awg
touch /var/log/awg/whitelist /var/log/awg/limit.log

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
systemctl restart "$SERVICE_NAME"
log_success "Панель запущена: systemctl status $SERVICE_NAME"

if systemctl list-unit-files | grep -q "^$LIMIT_SERVICE_NAME.service"; then
    systemctl enable "$LIMIT_SERVICE_NAME" >/dev/null 2>&1
    systemctl restart "$LIMIT_SERVICE_NAME"
    log_success "Детектор раздачи запущен: systemctl status $LIMIT_SERVICE_NAME"
fi

# --- Итог --------------------------------------------------------------------
sleep 1
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_success "=== Установка завершена ==="
    ADMIN_PATH="$(grep '^admin_path=' "$CONF_FILE" 2>/dev/null | cut -d= -f2 || echo '/1q2w3e4r')"
    echo -e "${GREEN}Админ-панель:${NC} http://$(curl -4 -s ifconfig.me || echo '<IP-сервера>'):${PANEL_PORT}${ADMIN_PATH}"
    echo -e "${GREEN}Логин:${NC}     $(grep PANEL_ADMIN_USER "$ENV_FILE" | cut -d= -f2)"
    echo -e "${GREEN}Пароль:${NC}     $(grep PANEL_ADMIN_PASSWORD "$ENV_FILE" | cut -d= -f2)"
    echo ""
    echo "Управление из CLI:  sudo /root/panelctl status"
    echo "Логи панели:        /var/log/awg-panel.log"
    echo "Секреты:            /root/awg/panel.env (chmod 600)"
else
    die "Сервис $SERVICE_NAME не запустился. Смотрите: journalctl -u $SERVICE_NAME -n 50"
fi

#!/bin/bash
# Детектор раздачи VPN-конфига (несколько устройств с одного ключа).
#
# Принцип: у настоящей раздачи endpoint одного ключа НЕПРЕРЫВНО скачет между
# публичными IP РАЗНЫХ сетей — каждое устройство ре-хендшейкается со своего
# адреса (A->B->A->B...). У одного человека смена внешнего IP тоже возможна
# (мобильный интернет, CGNAT провайдера, переключение Wi-Fi/4G), но это
# короткий всплеск: несколько переходов, после которых адрес стабилизируется
# надолго. Поэтому блокировка срабатывает ТОЛЬКО при сочетании всех признаков:
#
#   1) за окно WINDOW набралось >= TRANSITIONS смен IP;
#   2) из них >= OSCILLATIONS «возвратов» к ранее виденным IP (A->B->A);
#   3) IP принадлежат >= SUBNETS разным /16 сетям (реальные сети, а не один NAT);
#   4) endpoint не стабилизировался: ни один отрезок на одном IP не длился
#      дольше STABLE_MAX секунд (включая «хвост» — время с последней смены);
#   5) признаки подтвердились на >= CONSECUTIVE проверках подряд.
#
# Авто-разблокировка: как только у заблокированного клиента прекратилось
# чередование IP (в окне остался один стабильный адрес) — DROP снимается сам,
# чтобы ложное срабатывание не держало человека в блоке навсегда. После любой
# разблокировки действует грация GRACE, в течение которой повторная блокировка
# не ставится.
#
# Белый список: имена клиентов, публичные IP или CIDR — по одному в строке в
# файле WHITELIST. Такие клиенты/адреса никогда не блокируются.
#
# Конфигурация через ENV:
#   LIMIT_WINDOW=600  LIMIT_TRANSITIONS=10  LIMIT_OSCILLATIONS=5
#   LIMIT_SUBNETS=2  LIMIT_STABLE_MAX=240  LIMIT_CONSECUTIVE=3
#   LIMIT_CHECK_EVERY=15  LIMIT_GRACE=1800

set -u
IFACE="${IFACE:-awg0}"
WINDOW="${LIMIT_WINDOW:-600}"
TRANSITIONS="${LIMIT_TRANSITIONS:-10}"
OSCILLATIONS="${LIMIT_OSCILLATIONS:-5}"
SUBNETS="${LIMIT_SUBNETS:-2}"
STABLE_MAX="${LIMIT_STABLE_MAX:-240}"
CONSECUTIVE="${LIMIT_CONSECUTIVE:-3}"
CHECK_EVERY="${LIMIT_CHECK_EVERY:-15}"
GRACE="${LIMIT_GRACE:-1800}"
SERVER_CONF="${SERVER_CONF:-/etc/amnezia/amneziawg/awg0.conf}"
AWG_DIR="${AWG_DIR:-/root/awg}"
AWG_BIN="${AWG_BIN:-/usr/bin/awg}"

STATE_DIR="/var/log/awg/connstate"
BLOCK_FILE="/var/log/awg/blocked_ips"
WHITELIST="/var/log/awg/whitelist"
LOG_FILE="/var/log/awg/limit.log"

# Один работающий инстанс (защита от дублирующихся сервисов)
exec 9>/var/lock/awg-limit.lock
flock -n 9 || exit 0

mkdir -p "$STATE_DIR" /var/log/awg
touch "$BLOCK_FILE" 2>/dev/null || true
touch "$WHITELIST" 2>/dev/null || true

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

stfile() { echo "$STATE_DIR/${1//\//_}"; }

declare -A CONF_NAME_BY_KEY CONF_IP_BY_KEY CONF_KEY_BY_IP
declare -A NAME_BY_STFILE IP_BY_STFILE KEY_BY_STFILE
declare -A last_seen consecutive logged_already grace_until prev_blocked
WL_NAMES="" WL_IPS=""

# ── Белый список ────────────────────────────────────────────────────────────
load_whitelist() {
    WL_NAMES="" WL_IPS=""
    local line
    while IFS= read -r line; do
        line="${line%%#*}"; line="${line//[[:space:]]/}"
        [ -z "$line" ] && continue
        if [[ "$line" =~ ^[0-9.]+$ ]]; then
            WL_IPS="$WL_IPS ${line}/32"
        elif [[ "$line" =~ ^[0-9.]+/[0-9]+$ ]]; then
            WL_IPS="$WL_IPS $line"
        else
            WL_NAMES="$WL_NAMES $line"
        fi
    done < "$WHITELIST"
}

cidr_match() { # $1=ip $2=cidr → 0 если входит
    local ip="$1" cidr="$2" net pref
    net="${cidr%%/*}"; pref="${cidr##*/}"
    case "$pref" in
        0)  return 0 ;;
        32) [ "$ip" = "$net" ] ;;
        24) [ "${ip%.*}" = "${net%.*}" ] ;;
        16) [ "$(printf '%s' "$ip" | cut -d. -f1-2)" = "$(printf '%s' "$net" | cut -d. -f1-2)" ] ;;
        8)  [ "${ip%%.*}" = "${net%%.*}" ] ;;
        *)  return 1 ;;
    esac
}

in_whitelist() { # $1=имя клиента $2=туннельный ip $3="публичные ip" → 0 если в белом списке
    local name="$1" tip="$2" pip="$3" w p
    for w in $WL_NAMES; do [ "$w" = "$name" ] && return 0; done
    for w in $WL_IPS; do
        cidr_match "$tip" "$w" && return 0
        for p in $pip; do cidr_match "$p" "$w" && return 0; done
    done
    return 1
}

# ── Карта конфига: ключ -> (имя, туннельный IP) и обратно ──────────────────
build_conf_map() {
    CONF_NAME_BY_KEY=() CONF_IP_BY_KEY=() CONF_KEY_BY_IP=()
    NAME_BY_STFILE=() IP_BY_STFILE=() KEY_BY_STFILE=()
    local key name ip st
    while IFS=$'\t' read -r key name ip; do
        [ -z "$key" ] && continue
        st="${key//\//_}"
        CONF_NAME_BY_KEY["$key"]="$name"
        CONF_IP_BY_KEY["$key"]="$ip"
        CONF_KEY_BY_IP["$ip"]="$key"
        NAME_BY_STFILE["$st"]="$name"
        IP_BY_STFILE["$st"]="$ip"
        KEY_BY_STFILE["$st"]="$key"
    done < <(awk '
        $1=="[Peer]" {inp=1; nm=""; key=""; ip=""; next}
        inp && $1=="#_Name" {nm=$3; next}
        inp && $1=="PublicKey" {key=$3; next}
        inp && $1=="AllowedIPs" {
            for(i=3;i<=NF;i++){ gsub(/,/,"",$i); if($i ~ /^10\./) {ip=$i; break} }
            if(key!="" && ip!="") print key"\t"nm"\t"ip
            inp=0
        }
    ' "$SERVER_CONF")
}

# ── Применить сохранённые блокировки (переживает рестарты туннеля/сервера) ──
reapply_blocks() {
    local ip
    while IFS= read -r ip; do
        [ -z "$ip" ] && continue
        iptables -D FORWARD -s "$ip" -j DROP 2>/dev/null
        iptables -I FORWARD 1 -s "$ip" -j DROP 2>/dev/null
    done < "$BLOCK_FILE"
}

remove_block() { # $1=туннельный ip — снять DROP и убрать из списка
    local ip="$1" tmp
    iptables -D FORWARD -s "$ip" -j DROP 2>/dev/null
    iptables -D FORWARD -s "${ip%/*}" -j DROP 2>/dev/null
    tmp="$(mktemp)"
    while IFS= read -r ln; do
        [ "$ln" != "$ip" ] && printf '%s\n' "$ln"
    done < "$BLOCK_FILE" > "$tmp"
    mv "$tmp" "$BLOCK_FILE"
}

block_peer() { # $1=ключ $2=имя $3=туннельный ip $4="признаки" $5="публичные ip"
    local key="$1" name="$2" ip="$3" evidence="$4" pub_ips="$5"
    if [ -z "$ip" ]; then
        log "🔒 БЛОК-НЕ-ВОЗМОЖЕН: клиент $name ($key) раздаёт конфиг, но туннельный IP не найден"
        return
    fi
    if iptables -C FORWARD -s "$ip" -j DROP 2>/dev/null; then
        if [ -z "${logged_already[$key]:-}" ]; then
            log "🔒 $name ($ip) уже заблокирован"
            logged_already[$key]=1
        fi
        return
    fi
    iptables -I FORWARD 1 -s "$ip" -j DROP
    grep -qxF "$ip" "$BLOCK_FILE" 2>/dev/null || echo "$ip" >> "$BLOCK_FILE"
    log "🔒 БЛОК: клиент $name ($ip) раздаёт конфиг [$evidence]. Публичные IP: $pub_ips"
}

# ── Анализ истории endpoint: смены / возвраты / подсети / стабильность ──────
# Возвращает: "смены возвраты /16-сети макс_отрезок стабильность"
analyze_state() { # $1=имя state-файла, $2=prune, $3=now
    local f="$1"
    [ -s "$f" ] || { echo "0 0 0 0 0"; return; }
    awk -v p="$2" -v now="$3" '
        $1 >= p {
            ts=$1; ep=$2
            if (run_start == "") run_start = ts
            if (prev != "" && ep != prev) {
                d = prev_ts - run_start; if (d > max_run) max_run = d
                run_start = ts
                if (ep in seen) osc++
            }
            seen[ep]=1
            split(ep, a, "."); sn = a[1] "." a[2]; subs[sn]=1
            prev = ep; prev_ts = ts; n++
        }
        END {
            if (prev_ts != "" && run_start != "") { d = prev_ts - run_start; if (d > max_run) max_run = d }
            stable = (prev_ts != "" ? now - prev_ts : now - p)
            printf "%d %d %d %d %d\n", n+0, osc+0, length(subs)+0, max_run+0, stable+0
        }
    ' "$f"
}

check_key() { # $1=имя state-файла
    local st="$1" key n osc subs maxrun stable cname tun_ip pub_ips evidence
    key="${KEY_BY_STFILE[$st]:-}"
    [ -z "$key" ] && return
    read -r n osc subs maxrun stable < <(analyze_state "$STATE_DIR/$st" "$prune" "$now")

    if [ "$n" -lt "$TRANSITIONS" ] || [ "$osc" -lt "$OSCILLATIONS" ] || \
       [ "$subs" -lt "$SUBNETS" ] || [ "$stable" -gt "$STABLE_MAX" ] || \
       [ "$maxrun" -gt "$STABLE_MAX" ]; then
        consecutive[$key]=0
        return
    fi

    cname="${NAME_BY_STFILE[$st]:-}"
    tun_ip="${IP_BY_STFILE[$st]:-}"
    pub_ips=$(awk '{print $2}' "$STATE_DIR/$st" 2>/dev/null | sort -u | tr '\n' ' ')
    evidence="${n} смен, ${osc} возвратов, ${subs} /16 сетей за ${WINDOW}с"

    if in_whitelist "$cname" "$tun_ip" "$pub_ips"; then
        log "⏭️ ПРОПУСК: клиент $cname ($key) в белом списке [$evidence]"
        consecutive[$key]=0
        return
    fi
    if [ -n "${grace_until[$key]:-}" ] && [ "$now" -lt "${grace_until[$key]}" ]; then
        consecutive[$key]=0
        return
    fi

    consecutive[$key]=$(( ${consecutive[$key]:-0} + 1 ))
    if [ "${consecutive[$key]}" -ge "$CONSECUTIVE" ]; then
        block_peer "$key" "$cname" "$tun_ip" "$evidence" "$pub_ips"
        consecutive[$key]=0
    else
        log "⚠️ ВНИМАНИЕ: клиент $cname ($key) — непрерывный скачок endpoint [$evidence]. Срабатывание ${consecutive[$key]}/${CONSECUTIVE}, блок при повторе."
    fi
}

# ── Авто-разблокировка: у клиента нет смен IP в окне ────────────────────────
auto_unblock_loop() {
    local tip key name n
    while IFS= read -r tip; do
        [ -z "$tip" ] && continue
        key="${CONF_KEY_BY_IP[$tip]:-}"
        [ -z "$key" ] && continue
        read -r n _ _ _ _ < <(analyze_state "$(stfile "$key")" "$prune" "$now")
        if [ "$n" -eq 0 ]; then
            name="${CONF_NAME_BY_KEY[$key]:-}"
            remove_block "$tip"
            log "🔓 АВТО-РАЗБЛОК: клиент $name ($key, $tip) — endpoint стабилен, подозрение не подтвердилось"
        fi
    done < <(awk '!seen[$0]++' "$BLOCK_FILE" 2>/dev/null)
}

sample_endpoints() {
    "$AWG_BIN" show "$IFACE" endpoints 2>/dev/null
}

reapply_blocks
load_whitelist
log "Сервис запущен (окно=${WINDOW}с, смен=${TRANSITIONS}, возвратов=${OSCILLATIONS}, сетей=${SUBNETS}, стабильно=${STABLE_MAX}с, блок при ${CONSECUTIVE} срабатываниях подряд, грация=${GRACE}с)"

while true; do
    now=$(date +%s)
    prune=$((now - WINDOW))

    build_conf_map
    load_whitelist
    reapply_blocks

    # Фиксируем смены endpoint
    while IFS=$'\t' read -r key ep; do
        [ -z "$key" ] && continue
        ip="${ep%%:*}"
        [ -z "$ip" ] || [ "$ip" = "(none)" ] && continue
        if [ "${last_seen[$key]:-}" != "$ip" ]; then
            echo "$now $ip" >> "$(stfile "$key")"
            last_seen[$key]="$ip"
        fi
    done < <(sample_endpoints)

    # Чистим окно и анализируем каждый клиент
    for f in "$STATE_DIR"/*; do
        [ -f "$f" ] || continue
        awk -v p="$prune" '$1 >= p' "$f" > "$f.tmp" 2>/dev/null && mv "$f.tmp" "$f"
        check_key "$(basename "$f")"
    done

    auto_unblock_loop

    # Грация после разблокировки (админской или автоматической)
    declare -A now_blocked_by_key
    while IFS= read -r tip; do
        [ -z "$tip" ] && continue
        key="${CONF_KEY_BY_IP[$tip]:-}"
        [ -n "$key" ] && now_blocked_by_key["$key"]=1
    done < <(awk '!seen[$0]++' "$BLOCK_FILE" 2>/dev/null)

    for key in "${!prev_blocked[@]}"; do
        if [ -z "${now_blocked_by_key[$key]:-}" ]; then
            grace_until[$key]=$(( now + GRACE ))
            log "🕒 Клиент ${CONF_NAME_BY_KEY[$key]:-} ($key) разблокирован. Грация ${GRACE}с до возможной повторной блокировки."
        fi
    done
    prev_blocked=()
    for key in "${!now_blocked_by_key[@]}"; do
        prev_blocked[$key]=1
    done

    sleep "$CHECK_EVERY"
done

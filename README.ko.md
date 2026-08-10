# AmneziaWG Panel

**🌐 다른 언어로 읽기:**
[🇬🇧 English](README.md) | [🇷🇺 Русский](README.ru.md) | [🇩🇪 Deutsch](README.de.md) | [🇫🇷 Français](README.fr.md) | [🇨🇳 中文](README.zh.md) | [🇯🇵 日本語](README.ja.md) | [🇰🇷 한국어](README.ko.md) | [🇸🇦 العربية](README.ar.md)

[AmneziaWG](https://github.com/amnezia-vpn/amneziawg)(AWG) VPN 서버를 관리하는 웹 패널입니다. 인증, 클라이언트 설정 발급, QR 코드, 만료일 관리, 설정 공유 감지 기능을 제공합니다.

- **panel.py** — 웹 패널(파이썬 표준 라이브러리만 사용, 의존성 없음). 기본 포트 `8000`, 비밀 관리자 경로 `/1q2w3e4r`(그 외에는 모두 404 반환).
- **panelctl** — CLI 도구: 클라이언트 추가/연장/삭제, 상태, 통계.
- **install.sh** — 한 번의 명령으로 새 서버에 전체 프로젝트를 배포합니다.
- **install_amneziawg.sh** — AmneziaWG 2.0 설치 프로그램(비대화형 모드 지원).
- **connection_limit.sh** — 설정 공유 감지 및 차단(하나의 키로 여러 기기).

## 빠른 시작

새 VDS(Ubuntu 24.04 / Debian 12+)에서:

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/GreenMan2022/AmneziaWG-Panel/ panel
cd panel
sudo bash install.sh
```

설치에는 몇 분이 걸립니다: AmneziaWG가 설치되고, 무작위 패널 비밀값이 생성되며, `awg-panel` 및 `awg-connection-limit` systemd 서비스가 만들어집니다. 완료되면 스크립트가 패널 주소, 관리자 로그인 및 비밀번호를 출력합니다.

### install.sh 옵션

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--port=N` | AWG 서버 UDP 포트 | `443` |
| `--subnet=CIDR` | 터널 서브넷 | `10.9.9.1/24` |
| `--route=all\|amnezia\|custom:CIDR` | 라우팅 모드 | `all` |
| `--preset=default\|mobile` | 난독화 프리셋 | `mobile` |
| `--no-cps` / `--cps` | I1 (CPS) 파라미터 켜기/끄기 | `--no-cps` |
| `--skip-awg` | 설치된 AWG는 건드리지 않고 패널만 재배포 | — |

예시: `sudo bash install.sh --port=51820 --subnet=10.0.0.1/24`

## 사용 방법

관리 패널: `http://<IP>:8000/1q2w3e4r`(비밀 경로는 `panel.py`의 `ADMIN_PATH` 상수에서 변경 가능).

CLI(root로 실행):

```bash
sudo panelctl status              # 패널 및 서비스 상태
sudo panelctl add <이름>          # 클라이언트 발급(30일)
sudo panelctl extend <이름> <일수> # 연장
sudo panelctl list                # 클라이언트 목록
sudo panelctl blocked             # 공유로 차단된 클라이언트
sudo panelctl remove <이름>       # 클라이언트 삭제
sudo panelctl config              # 패널 설정
```

## 보안

- 관리자 비밀번호와 솔트는 설치 시 **무작위로 생성**되어 `/root/awg/panel.env`(chmod 600)에 저장됩니다. 패널은 환경 변수(`PANEL_ADMIN_USER`, `PANEL_ADMIN_PASSWORD`, `PANEL_HASH_SALT`, `PANEL_CLIENT_AUTH_SALT`)에서 읽습니다. 변수가 없으면 **개발 전용** 내장 값이 사용됩니다 — 프로덕션 서버에서는 사용하면 안 됩니다.
- `/root/awg/` 디렉터리에는 서버와 클라이언트의 개인 키가 있습니다. `.gitignore`를 통해 git에서 제외되어 있습니다 — 절대 공개하지 마세요.
- 관리자 경로 `/1q2w3e4r`는 스캐너로부터 인터페이스를 숨깁니다(루트는 404 반환). 하지만 비밀번호를 대체하지는 못합니다: 필요 시 추가로 접근을 제한하세요(nginx, 방화벽).

## 프로젝트 구조

```
install.sh               # 새 VDS 배포
install_amneziawg.sh     # AmneziaWG 2.0 설치 프로그램(amneziawg-installer 포크)
panel.py                 # 웹 패널(stdlib Python)
panelctl                 # CLI 관리 도구
connection_limit.sh      # 설정 공유 감지기
```

## 라이선스

이 프로젝트는 [amneziawg-installer](https://github.com/bivlked/amneziawg-installer)를 기반으로 합니다.

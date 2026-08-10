# AmneziaWG Panel

**🌐 阅读其他语言版本：**
[🇬🇧 English](README.md) | [🇷🇺 Русский](README.ru.md) | [🇩🇪 Deutsch](README.de.md) | [🇫🇷 Français](README.fr.md) | [🇨🇳 中文](README.zh.md) | [🇯🇵 日本語](README.ja.md) | [🇰🇷 한국어](README.ko.md) | [🇸🇦 العربية](README.ar.md)

用于管理 [AmneziaWG](https://github.com/amnezia-vpn/amneziawg) (AWG) VPN 服务器的 Web 面板，支持身份验证、客户端配置发放、二维码、有效期管理和配置分享检测。

- **panel.py** — Web 面板（仅使用 Python 标准库，无任何依赖）。默认端口 `8000`，管理后台秘密路径 `/1q2w3e4r`（其他路径均返回 404）。
- **panelctl** — CLI 工具：添加/续期/删除客户端、状态查看、统计。
- **install.sh** — 一条命令在新服务器上部署整个项目。
- **install_amneziawg.sh** — AmneziaWG 2.0 安装程序（支持非交互模式）。
- **connection_limit.sh** — 配置分享检测与封锁（同一密钥多设备使用）。

## 快速开始

在全新 VDS（Ubuntu 24.04 / Debian 12+）上：

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/GreenMan2022/AmneziaWG-Panel/ panel
cd panel
sudo bash install.sh
```

安装需要几分钟：安装 AmneziaWG、生成随机面板密钥、创建 `awg-panel` 和 `awg-connection-limit` systemd 服务。安装完成后，脚本会输出面板地址、管理员用户名和密码。

### install.sh 选项

| 选项 | 说明 | 默认值 |
|---|---|---|
| `--port=N` | AWG 服务器 UDP 端口 | `443` |
| `--subnet=CIDR` | 隧道子网 | `10.9.9.1/24` |
| `--route=all\|amnezia\|custom:CIDR` | 路由模式 | `all` |
| `--preset=default\|mobile` | 混淆预设 | `mobile` |
| `--no-cps` / `--cps` | 启用/禁用 I1 (CPS) 参数 | `--no-cps` |
| `--skip-awg` | 不动已安装的 AWG，仅重新部署面板 | — |

示例：`sudo bash install.sh --port=51820 --subnet=10.0.0.1/24`

## 使用方法

管理后台：`http://<IP>:8000/1q2w3e4r`（可在 `panel.py` 中修改秘密路径，常量 `ADMIN_PATH`）。

CLI（以 root 身份）：

```bash
sudo panelctl status              # 面板和服务状态
sudo panelctl add <名称>          # 发放客户端（有效期 30 天）
sudo panelctl extend <名称> <天数> # 续期
sudo panelctl list                # 客户端列表
sudo panelctl blocked             # 因分享被封锁的客户端
sudo panelctl remove <名称>       # 删除客户端
sudo panelctl config              # 面板配置
```

## 安全性

- 管理员密码和盐值在安装时**随机生成**，存储在 `/root/awg/panel.env`（chmod 600）。面板从环境变量中读取（`PANEL_ADMIN_USER`、`PANEL_ADMIN_PASSWORD`、`PANEL_HASH_SALT`、`PANEL_CLIENT_AUTH_SALT`）。没有这些变量时使用内置值**仅供开发**——生产服务器上不得使用。
- `/root/awg/` 目录包含服务器和客户端私钥。它已通过 `.gitignore` 从 git 中排除——切勿公开该目录。
- 管理后台路径 `/1q2w3e4r` 可对扫描器隐藏界面（根路径返回 404），但不能替代密码：必要时请额外限制访问（nginx、防火墙）。

## 项目结构

```
install.sh               # 在新 VDS 上部署
install_amneziawg.sh     # AmneziaWG 2.0 安装程序（amneziawg-installer 的分支）
panel.py                 # Web 面板（Python 标准库）
panelctl                 # CLI 管理工具
connection_limit.sh      # 配置分享检测器
```

## 许可证

本项目基于 [amneziawg-installer](https://github.com/bivlked/amneziawg-installer)。

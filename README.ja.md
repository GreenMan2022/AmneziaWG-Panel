# AmneziaWG Panel

**🌐 他の言語で読む：**
[🇬🇧 English](README.md) | [🇷🇺 Русский](README.ru.md) | [🇩🇪 Deutsch](README.de.md) | [🇫🇷 Français](README.fr.md) | [🇨🇳 中文](README.zh.md) | [🇯🇵 日本語](README.ja.md) | [🇰🇷 한국어](README.ko.md) | [🇸🇦 العربية](README.ar.md)

[AmneziaWG](https://github.com/amnezia-vpn/amneziawg)（AWG）VPN サーバーを管理する Web パネルです。認証、クライアント設定の発行、QR コード、有効期限の管理、設定共有の検出に対応しています。

- **panel.py** — Web パネル（Python 標準ライブラリのみ、依存関係なし）。デフォルトポート `8000`、シークレット管理パス `/1q2w3e4r`（その他はすべて 404 を返します）。
- **panelctl** — CLI ツール：クライアントの追加・延長・削除、ステータス、統計。
- **install.sh** — 1 つのコマンドで新しいサーバーにプロジェクト全体をデプロイします。
- **install_amneziawg.sh** — AmneziaWG 2.0 インストーラー（非対話モード対応）。
- **connection_limit.sh** — 設定共有の検出とブロック（1 つのキーによる複数デバイス）。

## クイックスタート

新しい VDS（Ubuntu 24.04 / Debian 12+）上で：

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/GreenMan2022/AmneziaWG-Panel/ panel
cd panel
sudo bash install.sh
```

インストールには数分かかります：AmneziaWG のインストール、ランダムなパネルシークレットの生成、systemd サービス `awg-panel` と `awg-connection-limit` の作成が行われます。完了すると、スクリプトはパネルのアドレス、管理者のログインとパスワードを表示します。

### install.sh のオプション

| オプション | 説明 | デフォルト |
|---|---|---|
| `--port=N` | AWG サーバーの UDP ポート | `443` |
| `--subnet=CIDR` | トンネルサブネット | `10.9.9.1/24` |
| `--route=all\|amnezia\|custom:CIDR` | ルーティングモード | `all` |
| `--preset=default\|mobile` | 難読化プリセット | `mobile` |
| `--no-cps` / `--cps` | I1 (CPS) パラメータの有効化/無効化 | `--no-cps` |
| `--skip-awg` | インストール済みの AWG に触れず、パネルだけ再デプロイ | — |

例：`sudo bash install.sh --port=51820 --subnet=10.0.0.1/24`

## 使い方

管理パネル：`http://<IP>:8000/1q2w3e4r`（シークレットパスは `panel.py` の定数 `ADMIN_PATH` で変更できます）。

CLI（root で実行）：

```bash
sudo panelctl status              # パネルとサービスのステータス
sudo panelctl add <名前>          # クライアントを発行（有効期間 30 日）
sudo panelctl extend <名前> <日数> # 延長
sudo panelctl list                # クライアント一覧
sudo panelctl blocked             # 共有でブロックされたクライアント
sudo panelctl remove <名前>       # クライアントを削除
sudo panelctl config              # パネル設定
```

## セキュリティ

- 管理者パスワードとソルトはインストール時に**ランダムに生成**され、`/root/awg/panel.env`（chmod 600）に保存されます。パネルは環境変数（`PANEL_ADMIN_USER`、`PANEL_ADMIN_PASSWORD`、`PANEL_HASH_SALT`、`PANEL_CLIENT_AUTH_SALT`）から読み取ります。変数がない場合は**開発専用**の組み込み値が使われます — 本番サーバーでは使用しないでください。
- `/root/awg/` ディレクトリにはサーバーとクライアントの秘密鍵が含まれています。`.gitignore` で git から除外されています — 絶対に公開しないでください。
- 管理パス `/1q2w3e4r` はスキャナーからインターフェースを隠します（ルートは 404 を返します）が、パスワードの代わりにはなりません：必要に応じてアクセスを追加制限してください（nginx、ファイアウォール）。

## プロジェクト構成

```
install.sh               # 新しい VDS へのデプロイ
install_amneziawg.sh     # AmneziaWG 2.0 インストーラー（amneziawg-installer のフォーク）
panel.py                 # Web パネル（stdlib Python）
panelctl                 # CLI 管理ツール
connection_limit.sh      # 設定共有検出器
```

## ライセンス

このプロジェクトは [amneziawg-installer](https://github.com/bivlked/amneziawg-installer) に基づいています。

# AmneziaWG Panel

**🌐 اقرأ بلغات أخرى:**
[🇬🇧 English](README.md) | [🇷🇺 Русский](README.ru.md) | [🇩🇪 Deutsch](README.de.md) | [🇫🇷 Français](README.fr.md) | [🇨🇳 中文](README.zh.md) | [🇯🇵 日本語](README.ja.md) | [🇰🇷 한국어](README.ko.md) | [🇸🇦 العربية](README.ar.md)

لوحة ويب لإدارة خادم VPN [AmneziaWG](https://github.com/amnezia-vpn/amneziawg) (AWG) مع المصادقة، وإصدار إعدادات العملاء، ورموز QR، وتواريخ الانتهاء، وكاشف مشاركة الإعدادات.

- **panel.py** — لوحة الويب (مكتبة بايثون القياسية فقط، بدون تبعيات). المنفذ الافتراضي `8000`، المسار السري للوحة الإدارة `/1q2w3e4r` (كل ما عداه يعيد 404).
- **panelctl** — أداة سطر الأوامر: إضافة/تمديد/حذف العملاء، الحالة، الإحصائيات.
- **install.sh** — نشر المشروع كاملاً على خادم جديد بأمر واحد.
- **install_amneziawg.sh** — مثبّت AmneziaWG 2.0 (يدعم الوضع غير التفاعلي).
- **connection_limit.sh** — كاشف ومانع مشاركة الإعدادات (عدة أجهزة بمفتاح واحد).

## البدء السريع

على VDS جديد (Ubuntu 24.04 / Debian 12+):

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/GreenMan2022/AmneziaWG-Panel/ panel
cd panel
sudo bash install.sh
```

يستغرق التثبيت بضع دقائق: يتم تثبيت AmneziaWG، وتوليد أسرار عشوائية للوحة، وإنشاء خدمتي systemd `awg-panel` و`awg-connection-limit`. عند الانتهاء، يطبع السكربت عنوان اللوحة واسم مستخدم المدير وكلمة المرور.

### خيارات install.sh

| الخيار | الوصف | الافتراضي |
|---|---|---|
| `--port=N` | منفذ UDP لخادم AWG | `443` |
| `--subnet=CIDR` | الشبكة الفرعية للنفق | `10.9.9.1/24` |
| `--route=all\|amnezia\|custom:CIDR` | وضع التوجيه | `all` |
| `--preset=default\|mobile` | إعداد التمويه | `mobile` |
| `--no-cps` / `--cps` | تشغيل/إيقاف المعامل I1 (CPS) | `--no-cps` |
| `--skip-awg` | عدم لمس AWG المثبّت، إعادة نشر اللوحة فقط | — |

مثال: `sudo bash install.sh --port=51820 --subnet=10.0.0.1/24`

## الاستخدام

لوحة الإدارة: `http://<IP>:8000/1q2w3e4r` (يمكن تغيير المسار السري في `panel.py`، الثابت `ADMIN_PATH`).

سطر الأوامر (بصلاحية root):

```bash
sudo panelctl status              # حالة اللوحة والخدمات
sudo panelctl add <الاسم>         # إصدار عميل (مدة 30 يوم)
sudo panelctl extend <الاسم> <أيام> # التمديد
sudo panelctl list                # قائمة العملاء
sudo panelctl blocked             # المحظورون بسبب المشاركة
sudo panelctl remove <الاسم>      # حذف عميل
sudo panelctl config              # إعدادات اللوحة
```

## الأمان

- كلمة مرور المدير والأملاح **تُولَّد عشوائياً** عند التثبيت وتُخزَّن في `/root/awg/panel.env` (chmod 600). تقرأها اللوحة من متغيرات البيئة (`PANEL_ADMIN_USER`، `PANEL_ADMIN_PASSWORD`، `PANEL_HASH_SALT`، `PANEL_CLIENT_AUTH_SALT`). بدون المتغيرات تُستخدم القيم المدمجة **للتطوير فقط** — لا يجوز استخدامها على خادم الإنتاج.
- يحتوي دليل `/root/awg/` على المفاتيح الخاصة للخادم والعملاء. وهو مستثنى من git عبر `.gitignore` — لا تنشره أبداً.
- المسار السري للوحة `/1q2w3e4r` يخفي الواجهة عن الماسحات (الجذر يعيد 404)، لكنه لا يغني عن كلمة المرور: قيّد الوصول إضافياً عند الحاجة (nginx، جدار الحماية).

## بنية المشروع

```
install.sh               # النشر على VDS جديد
install_amneziawg.sh     # مثبّت AmneziaWG 2.0 (فرع من amneziawg-installer)
panel.py                 # لوحة الويب (مكتبة بايثون القياسية)
panelctl                 # أداة إدارة سطر الأوامر
connection_limit.sh      # كاشف مشاركة الإعدادات
```

## الترخيص

المشروع مبني على [amneziawg-installer](https://github.com/bivlked/amneziawg-installer).

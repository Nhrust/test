# 08 · Графика: свой путь или путь zen

База готова ([06 · Комфортный TTY](06-tty.md)). Дальше два пути, выбирай один.

| Путь | Что получишь |
|---|---|
| **Свой путь** | любая среда из пакетов, настраиваешь сам. Консоль и Ly из главы 06 ни с чем не конфликтуют |
| ★ **Путь zen** | Niri, панель, меню, блокировка, звук, тема и мои настройки консоли из репозитория одним скриптом. Итог повторяет мой ноутбук |

> Команды этой главы написаны для bash. Если ты уже в fish, открой `bash --norc` и выполняй там.

## 1. Свой путь: среды и минимум

**Wiki:** [Desktop environment](https://wiki.archlinux.org/title/Desktop_environment) · [Wayland](https://wiki.archlinux.org/title/Wayland) · [PipeWire](https://wiki.archlinux.org/title/PipeWire) · [XDG Desktop Portal](https://wiki.archlinux.org/title/XDG_Desktop_Portal)

| Среда | Пакеты | Комментарий |
|---|---|---|
| GNOME | `gnome` | всё включено; сессия появится в Ly |
| KDE Plasma | `plasma-meta konsole dolphin` | тоже в Ly |
| Hyprland | `hyprland xdg-desktop-portal-hyprland foot waybar` | тайловая, больше ручной настройки |
| sway | `sway foot waybar` | как i3 на Wayland |
| Niri без zen | `niri xwayland-satellite foot waybar` | прокручиваемые колонки |

Общее для любой Wayland-среды, если её нет в наборе:

- звук: `pipewire pipewire-pulse wireplumber`;
- порталы: `xdg-desktop-portal-gtk` (и портал своей среды), агент polkit;
- шрифты (`ttf-jetbrains-mono-nerd`), Bluetooth (`bluez bluez-utils`), `brightnessctl`;
- видеодрайвер: `mesa` и `vulkan-radeon` (AMD), `mesa` и `vulkan-intel` (Intel), `nvidia-open` (NVIDIA).

Если драйвер нужен раньше времени (красивее ввод пароля), добавь модуль (`amdgpu`, `i915`) в `MODULES` файла `/etc/mkinitcpio.conf` и пересобери `mkinitcpio -P`.

## 2. Путь zen: что приносит репозиторий

- **Niri** с логикой пар окон и стеков (демон `zen-autowidth`), горячие клавиши, изменение размера.
- **Waybar, Rofi, mako, gtklock**: панель, меню, уведомления, блокировка в одной палитре.
- **Меню zen:** сеть, точка доступа, звук, питание, буфер обмена, мониторы, приложения.
- **Ly и Limine** в цветах темы, **палитра консоли** (та же, что в [главе 06](06-tty.md#палитра-консоли), но генерируется из общей темы), мои настройки **fish, tmux, neovim, btop, fastfetch**, тема GTK/Qt и курсор. Для neovim `deploy.sh` ещё клонирует плагин автопарных скобок `mini.pairs` с GitHub (если не вышло, nvim работает без него).
- Системные настройки: pacman, makepkg, logind, sleep, NetworkManager, nftables (с правилами точки доступа и Tailscale), sshd, zram.

Всё ставится поверх базы из глав 01–06. Скрипт можно запускать повторно.

## 3. Профиль машины

Файлы, зависящие от железа (твой UUID LUKS в параметрах ядра, хуки initramfs, микрокод), лежат в `hosts/<имя-машины>/`. **Без профиля `deploy.sh` не запустится:** он ищет каталог с тем же именем, что `/etc/hostname`, и останавливается с ошибкой.

> **Не используй чужой профиль.** Профиль `hosts/zen` взят с моего ноутбука: в нём мой UUID раздела и правила под моё железо. Применённый на другой машине, он собьёт параметры ядра, и система не загрузится. Всегда создавай свой.

```
git clone https://github.com/Nhrust/zen ~/Projects/zen
cd ~/Projects/zen
cat /etc/hostname                                   # имя каталога должно совпасть с этим
mkdir -p hosts/archbox/etc/kernel
cp /etc/kernel/cmdline    hosts/archbox/etc/kernel/cmdline
cp /etc/mkinitcpio.conf   hosts/archbox/etc/mkinitcpio.conf
printf '%s\n' amd-ucode snapper snap-pac > hosts/archbox/packages.txt
```

`archbox` замени на своё имя, а `amd-ucode` на `intel-ucode` при необходимости. Для ext4 и XFS убери `snapper` и `snap-pac`.

**Из чего состоит мой профиль** и что ставить на своей машине:

| Файл в `hosts/<имя>/` | У меня | Что указать тебе |
|---|---|---|
| `etc/kernel/cmdline` | параметры ядра с моим UUID LUKS | свой `cmdline` из [главы 03](03-system.md#6-параметры-ядра) |
| `etc/mkinitcpio.conf` | `MODULES=(amdgpu asus_nb_wmi)`, `FILES=(…81-asus-kbd-backlight.rules)` и мои хуки | свои хуки; модуль видеодрайвера (`amdgpu`, `i915`); остальное под твоё железо |
| `etc/modprobe.d/cfg80211.conf` | `ieee80211_regdom=RU` | код своей страны ([глава 05](05-first-boot.md#правила-wi-fi-для-твоей-страны)) |
| `etc/hosts` | моё имя машины | своё имя ([глава 03](03-system.md#4-вход-в-систему-время-локаль-имя)) |
| `etc/snapper/configs/root` и `etc/conf.d/snapper` | мои лимиты снимков | свои лимиты ([глава 05](05-first-boot.md#2-сеть-и-службы)) |
| `etc/udev/rules.d/81-asus-kbd-backlight.rules` | подсветка клавиатуры ASUS | не нужен, если не ASUS |
| `packages.txt`, `system-services.txt` | `amd-ucode`, `sof-firmware`, `snapper`, `snap-pac` и мои личные утилиты; таймеры Snapper | свой микрокод и нужные пакеты |
| `home/.config/zen/zen.conf` | мой город для погоды, локаль, контакт | свой город и локаль |
| `home/.local/state/zen/displays.json` | режимы моих мониторов | не нужен, сгенерируется |

> **Язык и единицы.** Панель, меню и погода берут язык и единицы из `~/.config/zen/zen.conf`, строка `locale = ru_RU.UTF-8` в секции `[general]`. Если оставить пусто, берётся системная локаль: при `LANG=en_US.UTF-8` температура показывается в градусах Фаренгейта. После правки перезапусти панель: `pkill -USR2 -x waybar`. Язык самих приложений (Nautilus и др.) задаёт `LANG` в `/etc/locale.conf`: для русского `LANG=ru_RU.UTF-8`, затем выйди и войди заново.

> **Эти файлы личные.** В `cmdline` лежит UUID раздела. Если форкаешь репозиторий, держи профиль своей машины в приватной копии или в `.gitignore` ([приложение B](B-privacy.md)).

## 4. deploy.sh

```
cd ~/Projects/zen
sudo snapper -c root create -d "before zen"       # только Btrfs: точка отката
./deploy.sh --dry-run                            # показывает, что будет сделано, ничего не меняя
./deploy.sh
```

| Шаг | Что происходит |
|---|---|
| Пакеты | списки `packages/base.txt`, `desktop.txt`, `extra.txt` и пакеты профиля машины |
| Файлы | `etc/` и `usr/local/` в систему, `home/` в домашний каталог; общие файлы, затем профиль машины поверх; прежние версии в `~/.local/state/zen/backup-<дата>/` |
| Курсор | скачивается Bibata-Modern-Classic |
| Службы | включаются системные и пользовательские службы, перезапускается `zen-autowidth` |
| Сборка | пересобирается initramfs при необходимости, применяется тема (`zen apply`): палитра, Limine, консоль, GTK/Qt, foot, tmux |

Отдельно переприменить тему: `zen apply`. После первого запуска перезагрузись и выбери в Ly сессию **niri**. Если снимков нет (ext4, XFS), сделай резервную копию настроек вручную.

## 5. Проверка и откат

```
systemctl --user status zen-autowidth
niri msg version
journalctl --user -u zen-autowidth -n 30
sudo snapper -c root create -d "zen deployed"     # только Btrfs
```

| Клавиши | Действие |
|---|---|
| Mod+Alt+стрелки | изменить размер пары окон, фокус остаётся на паре |
| Mod+[ / ] | втянуть окно в соседнюю колонку (стек); ширина запоминается и возвращается |
| Mod+K | caffeine (не гасить экран) |

Остальное: `~/.config/niri/config.kdl` (секции Main, Utilities, Menu, Monitor, Audio, Network). Если логика окон не обновилась: `systemctl --user restart zen-autowidth.service`. Диагностика: `zen doctor`.

**Откат.** Прежние версии файлов лежат в `~/.local/state/zen/backup-*`. На Btrfs откатить файлы можно снимком: `sudo snapper -c root list`, затем `sudo snapper -c root undochange N..M`. После отката `/boot` и `/usr` образ UKI нужно пересобрать (см. [приложение A](A-recovery.md)).

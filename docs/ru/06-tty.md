# 06 · Комфортный TTY

Теперь у тебя рабочая текстовая система ([05 · Первая загрузка](05-first-boot.md)). Дальше делаем её удобной: консоль, оболочка, редактор, инструменты, файрвол, вход. Ничего из этого не требует репозитория или скриптов. Мои полные настройки (neovim с плагином, темы, графика) придут в [главе 08](08-zen.md) и заменят скромные версии отсюда, старые уйдут в резервную копию.

Команды выполняй от обычного пользователя через `sudo`.

## 1. Консоль: шрифт и раскладка

**Wiki:** [Linux console](https://wiki.archlinux.org/title/Linux_console) · [Fonts](https://wiki.archlinux.org/title/Linux_console#Fonts)

Шрифт уже в `/etc/vconsole.conf`. Подбери размер под экран и сохрани:

```
setfont ter-v24n
sudoedit /etc/vconsole.conf          # FONT=ter-v24n
sudo mkinitcpio -P                   # хук sd-vconsole копирует шрифт в initramfs
```

### Палитра консоли

Консоль Linux показывает 16 цветов, но каждый из них можно задать любым 24-битным RGB-значением. Это делается без скриптов и репозитория: файл с 16 строками `#rrggbb` и команда `setvtrgb` (пакет `kbd`, он уже есть в системе). Ниже моя палитра: порядок стандартный (0 чёрный, 1 красный, 2 зелёный, 3 жёлтый, 4 синий, 5 пурпурный, 6 голубой, 7 серый, затем те же восемь ярких). Свою палитру подставь так же, по одному цвету на строку.

`/etc/zen/console.vtrgb`:

```
#0b0b0b
#f7a692
#8ed09c
#ebb077
#bdb3fa
#f3a3bb
#69cee6
#dedede
#555555
#ffd1c0
#bfeacd
#f8d8b3
#e1d7ff
#ffced8
#b2e8fa
#ffffff
```

```
sudo mkdir -p /etc/zen
sudoedit /etc/zen/console.vtrgb          # впиши 16 строк
sudo setvtrgb /etc/zen/console.vtrgb     # применяется сразу, в текущей консоли
```

Чтобы палитра применялась при каждой загрузке, нужна служба. `/etc/systemd/system/zen-console.service`:

```
[Unit]
Description=Zen console palette
Documentation=man:setvtrgb(8)
DefaultDependencies=no
After=systemd-vconsole-setup.service
Before=getty-pre.target sysinit.target shutdown.target
Conflicts=shutdown.target
ConditionPathExists=/etc/zen/console.vtrgb

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/setvtrgb /etc/zen/console.vtrgb

[Install]
WantedBy=sysinit.target
```

```
sudo systemctl enable --now zen-console.service
```

Всего у темы **24 цвета**: 16 стандартных и 8 приглушённых (`dim0`…`dim7`). Консоль Linux умеет только 16, поэтому в `console.vtrgb` их ровно 16. Приглушённые нужны терминалу `foot` в графике ([глава 08](08-zen.md)). Мои приглушённые: `#030303 #c57670 #6e9e63 #be7e51 #8488cb #bd7598 #2ca0ac #bebebe`.

Запрос пароля LUKS остаётся в стандартных цветах: палитра применяется после загрузки ядра и initramfs. В [главе 08](08-zen.md) этот же файл создаётся из общей темы командой `zen apply`, и цвета в консоли, Limine, Waybar и остальном совпадают.

## 2. Оболочка

**Wiki:** [Command-line shell](https://wiki.archlinux.org/title/Command-line_shell) · [Fish](https://wiki.archlinux.org/title/Fish) · [Zsh](https://wiki.archlinux.org/title/Zsh)

Выбор и сравнение: [глава 00](00-stack.md#оболочка). Оболочка root остаётся `bash`: так надёжнее для восстановления.

### ★ fish из `.bashrc`

Login-оболочка остаётся bash (надёжная основа и вход для восстановления), а работаешь ты в fish. Так советует ArchWiki. Вариант `chsh -s /usr/bin/fish` проще, но fish становится и login-оболочкой, и скрипты, которые ждут POSIX, могут ломаться.

```
sudo pacman -S --needed fish
```

Добавь в конец `~/.bashrc` (стандартный файл Arch с алиасами и `PS1` оставь как есть):

```
if [[ $- == *i* ]]
then
	exec fish
fi
```

Условие `$- == *i*` пропускает только интерактивную оболочку, поэтому скрипты и `bash -c` не затрагиваются. Обратная сторона: интерактивный `bash`, запущенный из fish, тоже сразу превратится в fish. Чтобы получить bash, пиши `bash --norc`.

Вариант с защитой от этого (форма с ArchWiki, дополненная проверкой родителя):

```
if [[ $(ps --no-header --pid=$PPID --format=comm) != "fish" && -z ${BASH_EXECUTION_STRING} && ${SHLVL} == 1 ]]
then
	shopt -q login_shell && LOGIN_OPTION='--login' || LOGIN_OPTION=''
	exec fish $LOGIN_OPTION
fi
```

Здесь `bash` из fish открывает настоящий bash. Выбери один из двух вариантов; ★ — первый, он короче.

> Синтаксис fish другой: статус последней команды `$status`, а не `$?`; переменные `set -x VAR значение`; подстановка `(cmd)`, а присваивание `VAR=значение` перед командой не работает. Команды этого гайда написаны для bash: если нужно, открой `bash --norc` и выполняй там.

### zsh

```
sudo pacman -S --needed zsh zsh-completions zsh-autosuggestions zsh-syntax-highlighting
chsh -s /usr/bin/zsh
```

Без `~/.zshrc` при первом запуске откроется мастер настройки, поэтому создай минимальный файл:

```
HISTFILE=~/.zsh_history
HISTSIZE=10000
SAVEHIST=10000
setopt SHARE_HISTORY HIST_IGNORE_DUPS
autoload -Uz compinit && compinit
source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh   # последним
```

### bash

Ничего не меняй. Для подсказок поставь `bash-completion`.

## 3. Пакеты и pacman

**Wiki:** [pacman](https://wiki.archlinux.org/title/Pacman) · [Tips and tricks](https://wiki.archlinux.org/title/Pacman/Tips_and_tricks) · [Reflector](https://wiki.archlinux.org/title/Reflector) · [makepkg](https://wiki.archlinux.org/title/Makepkg)

```
sudo pacman -S --needed pacman-contrib reflector
```

`/etc/pacman.conf`: раскомментируй или добавь в секции `[options]`, остальное оставь как есть:

```
Color
VerbosePkgLists
ParallelDownloads = 5
ILoveCandy
```

`/etc/makepkg.conf`:

```
MAKEFLAGS="-j$(( ($(nproc) + 1) / 2 ))"
```

Сборка AUR-пакетов использует половину ядер: системой можно пользоваться во время сборки. Для очистки кэша пакетов:

```
sudo systemctl enable --now paccache.timer
```

Обновление: `sudo pacman -Syu`. Если загрузка медленная, обнови зеркала ([глава 01](01-prepare.md#4-сеть-и-зеркала)).

## 4. Инструменты

```
sudo pacman -S --needed tmux btop fastfetch bat yazi \
  trash-cli unzip zip 7zip usbutils exfatprogs ntfs-3g ntfsprogs less
```

| Инструмент | Для чего | Ссылки |
|---|---|---|
| tmux | панели и вкладки в TTY, сессия живёт при выходе | [Tmux](https://wiki.archlinux.org/title/Tmux) |
| btop | монитор системы | |
| fastfetch | сводка о системе | |
| bat, yazi | просмотр файлов и файловый менеджер в консоли | |
| trash-cli | корзина вместо `rm` | |
| unzip zip 7zip | архивы | |
| exfatprogs ntfs-3g ntfsprogs | флешки и диски других ОС | [File systems](https://wiki.archlinux.org/title/File_systems) |

### Устройства и службы (яркость, звук, Bluetooth, печать, питание)

Всё это можно сделать сразу, не дожидаясь первой загрузки: `pacman` и `systemctl enable` работают и в chroot.

```
sudo pacman -S --needed brightnessctl \
  pipewire pipewire-alsa pipewire-audio pipewire-pulse wireplumber alsa-utils \
  bluez bluez-utils cups power-profiles-daemon upower
sudo systemctl enable bluetooth.service power-profiles-daemon.service upower.service
```

| Пакеты | Зачем |
|---|---|
| `brightnessctl` | яркость экрана и подсветки из командной строки |
| `pipewire` `pipewire-alsa` `pipewire-audio` `pipewire-pulse` `wireplumber` `alsa-utils` | звук: сервер, совместимость с ALSA и PulseAudio, менеджер сессий, `alsamixer` |
| `sof-firmware` | прошивки звука Intel/AMD (SOF): без них на многих новых ноутбуках звука нет, хотя `pipewire` работает. Если `wpctl status` показывает только Dummy Output, поставь его |
| `bluez` `bluez-utils` | Bluetooth и `bluetoothctl` |
| `cups` | печать |
| `power-profiles-daemon` | профили питания (экономия, баланс, производительность) |
| `upower` | состояние батареи для программ и действие при критическом заряде |

У меня **включены** `bluetooth`, `power-profiles-daemon` и `upower`. `cups` установлен, но служба не включена: если нужен принтер, добавь `cups.service` в команду `enable`. `NetworkManager-dispatcher.service` включается сам вместе с `NetworkManager` (шаг «Сеть и службы» главы 05).

**Пользовательские службы звука.** В моей системе `pipewire`, `pipewire-pulse`, `wireplumber` и их сокеты включены. Пакеты, скорее всего, включают их сами, но надёжнее включить явно. В chroot пользовательского сеанса нет, поэтому `systemctl --user` не сработает: используй `--global`, он включает службы для всех пользователей:

```
sudo systemctl --global enable pipewire.socket pipewire-pulse.socket wireplumber.service
```

Эти команды `--user` и `--global` выполняются **без `sudo`**: с `sudo` они обращаются к системному менеджеру и пишут `Unit pipewire.service does not exist`, а `systemctl --user` под `sudo` не находит сеанс пользователя. Имя службы `wireplumber.service` (не `wireplumber@.service`).

То же после первого входа, уже без chroot, от обычного пользователя (`--now` ещё и запускает):

```
systemctl --user enable --now pipewire.socket pipewire-pulse.socket wireplumber.service
systemctl --user is-enabled pipewire.socket pipewire-pulse.socket wireplumber.service
```

Остальные мои пользовательские службы (`waybar`, `zen-idle`, `zen-battery`, `zen-cliphist`, `zen-kanshi` и другие) относятся к графике: их включает `deploy.sh` в [главе 08](08-zen.md) из списка `lists/user-services.txt`.

### Панель tmux: сеть и батарея

Справа в строке tmux у меня стоит `WiFi | BAT 87% | Wed 11.11 20:12`. Состояние сети пишет **диспетчер NetworkManager**: скрипт, который NetworkManager запускает при каждой смене состояния, кладёт слово (`LAN`, `WiFi`, `LAN+WiFi`, `Offline`) в `/run/zen-network-status` и просит tmux обновить строку. Батарею читает сам модуль из `/sys`. Права важны: NetworkManager запускает только файлы, принадлежащие root и не доступные на запись другим.

Диспетчер, `/etc/NetworkManager/dispatcher.d/net-status`:

```
#!/bin/sh

# Update on network state changes
case "${2:-}" in
    up|down|reapply|connectivity-change) ;;
    *) exit 0 ;;
esac

# Read NetworkManager state once per event
devices=$(LC_ALL=C /usr/bin/nmcli -t -f TYPE,STATE device status 2>/dev/null) || exit 0

lan=0
wifi=0

printf '%s\n' "$devices" | grep -qx 'ethernet:connected' && lan=1
printf '%s\n' "$devices" | grep -qx 'wifi:connected' && wifi=1

if [ "$lan" -eq 1 ] && [ "$wifi" -eq 1 ]; then
    network="LAN+WiFi"
elif [ "$lan" -eq 1 ]; then
    network="LAN"
elif [ "$wifi" -eq 1 ]; then
    network="WiFi"
else
    network="Offline"
fi

# Do nothing if the status has not changed
old=$(cat /run/zen-network-status 2>/dev/null)
[ "$old" = "$network" ] && exit 0

# Atomically update the cached status
tmp=$(mktemp /run/.zen-network.XXXXXX) || exit 1
printf '%s\n' "$network" > "$tmp"
chmod 644 "$tmp"
mv -f "$tmp" /run/zen-network-status

# Refresh attached tmux clients of every user
for socket in /tmp/tmux-*/default; do
    [ -S "$socket" ] || continue
    user=$(/usr/bin/stat -c %U "$socket") || continue
    /usr/bin/runuser -u "$user" -- /usr/bin/tmux -S "$socket" list-clients -F '#{client_name}' 2>/dev/null |
    while IFS= read -r client; do
        [ -n "$client" ] || continue
        /usr/bin/runuser -u "$user" -- /usr/bin/tmux -S "$socket" refresh-client -S -t "$client" >/dev/null 2>&1
    done
done
```

```
sudo chown root:root /etc/NetworkManager/dispatcher.d/net-status
sudo chmod 755 /etc/NetworkManager/dispatcher.d/net-status
```

Модуль для tmux, `~/.local/lib/zen/bar/tmux` (создай каталоги: `mkdir -p ~/.local/lib/zen/bar`):

```
#!/bin/sh

network=$(cat /run/zen-network-status 2>/dev/null)
[ -n "$network" ] || network="Off"

battery="BAT --"

for bat in /sys/class/power_supply/BAT*; do
    [ -r "$bat/capacity" ] || continue

    level=$(cat "$bat/capacity")
    battery="BAT ${level}%"

    if [ "$(cat "$bat/status")" = "Charging" ]; then
        battery="${battery}+"
    fi

    break
done

printf '%s | %s\n' "$network" "$battery"
```

```
chmod +x ~/.local/lib/zen/bar/tmux
```

Если ты в chroot, создай файл в `/home/user/.local/lib/zen/bar/tmux` и верни владельца: `chown -R user:user /home/user/.local`. Слово про сеть появится после первой смены состояния сети (при первой загрузке NetworkManager это делает сам); до этого панель показывает `Off`.

### Редактор

Редактор уже установлен в [главе 03](03-system.md). Сделай его основным: `/etc/environment`

```
EDITOR=nvim
SUDO_EDITOR=nvim
```

Для `nano` или `vim` пиши своё имя. Мои настройки neovim приходят вместе с [главой 08](08-zen.md). Для nano минимум в `~/.nanorc`: `set linenumbers`, `set mouse`.

### Сокращения

**fish** (`~/.config/fish/conf.d/abbrs.fish`):

```
abbr -a -- n nvim
abbr -a -- ff fastfetch
abbr -a -- cls clear
abbr -a -- up 'sudo pacman'
abbr -a -- s sudo
abbr -a -- nv sudoedit
abbr -a -- b btop
abbr -a -- sp 'sudo snapper -c root'     # только Btrfs
```

Это именно *abbr*, а не alias: при пробеле сокращение раскрывается в полную команду, и в истории остаётся настоящее имя.

Файловый менеджер `yazi` с переходом в выбранный каталог при выходе, `~/.config/fish/functions/y.fish` (команда `y`):

```
function y
    set tmp (mktemp -t "yazi-cwd.XXXXXX")
    command yazi $argv --cwd-file="$tmp"

    if read -z cwd < "$tmp"
        and test "$cwd" != "$PWD"
        and test -d "$cwd"
        builtin cd -- "$cwd"
    end

    command rm -f -- "$tmp"
end
```

**zsh или bash** (`~/.zshrc` или `~/.bashrc`):

```
alias n=nvim
alias ff=fastfetch
alias up='sudo pacman'
alias b=btop
alias sp='sudo snapper -c root'          # только Btrfs
```

### tmux

Строка состояния моя: справа сеть, батарея, день недели, дата и время. Модуль и диспетчер описаны выше. `~/.tmux.conf`:

```
set -g status on
set -g status-interval 15
set -g status-right-length 60
set -g status-right '#($HOME/.local/lib/zen/bar/tmux) | %a %d.%m %H:%M'
```

Если не хочешь модуль сети и батареи, оставь `set -g status-right '%a %d.%m %H:%M'`. Мышь и другие настройки я не включаю: по желанию добавь `set -g mouse on`.

## 5. Файрвол

**Wiki:** [nftables](https://wiki.archlinux.org/title/Nftables) · [Simple stateful firewall](https://wiki.archlinux.org/title/Simple_stateful_firewall) · [Security: Firewalls](https://wiki.archlinux.org/title/Security#Firewalls)

| Вариант | За | Против |
|---|---|---|
| ★ **nftables** | прозрачно, одна служба, ничего лишнего | правила правишь сам |
| **ufw** | простые команды (`ufw allow 22`) | дополнительный слой над nftables или iptables |
| **firewalld** | зоны, динамические правила | тяжелее, нужен D-Bus |

Пакет `nftables` уже стоит из `pacstrap`. **По умолчанию оставь файл `/etc/nftables.conf` как есть:** это простой файрвол с состоянием от самого пакета. Входящее запрещено по умолчанию, разрешены ответы на твои соединения, loopback и ICMP, а также SSH на порту 22. Исходящее не ограничивается. Точный текст зависит от версии пакета, посмотри его: `cat /etc/nftables.conf`. Включение:

```
sudo nft -c -f /etc/nftables.conf          # проверка синтаксиса, ничего не применяет
sudo systemctl enable --now nftables.service
sudo nft list ruleset
```

Служба `nftables.service` одноразовая: она загружает правила и завершается, поэтому `systemctl status` показывает `inactive (dead)`, а в логе `Finished Netfilter Tables`. Это нормально. Работают ли правила, проверяет `sudo nft list table inet filter`.

### Пример: мой файл (SSH по Tailscale)

Это пример, как открыть порт SSH только для своей сети Tailscale, а не для всех. Он нужен только если ты включаешь SSH-сервер (шаг 6) и Tailscale. Мой файл построен на файле пакета; порт **укажи свой** (тот же, что в `sshd`).

```
#!/usr/bin/nft -f
destroy table inet filter
table inet filter {
  chain input {
    type filter hook input priority filter
    policy drop

    ct state invalid drop comment "early drop of invalid connections"
    ct state {established, related} accept comment "allow tracked connections"
    iif lo accept comment "allow from loopback"

    iifname "tailscale0" tcp dport <порт-ssh> accept comment "ssh только через Tailscale"

    meta l4proto { icmp, icmpv6 } accept comment "allow icmp"
    #tcp dport <порт-ssh> accept comment "ssh отовсюду (вместо строки выше)"
    pkttype host limit rate 5/second counter reject with icmpx type admin-prohibited
    counter
  }
  chain forward {
    type filter hook forward priority filter
    policy drop
  }
}
```

`destroy table` удаляет только *свою* таблицу `inet filter` и пересоздаёт её: чужие таблицы (NetworkManager, Docker) остаются нетронутыми, в отличие от `flush ruleset`. Если позже включишь службу, слушающую порт (SSH, веб-сервер), открой нужный порт в цепочке `input`, иначе доступа не будет. В главе 08 мой полный файл ещё содержит правила точки доступа; в этом примере их нет.

## 6. SSH и Tailscale (по желанию)

**Wiki:** [OpenSSH](https://wiki.archlinux.org/title/OpenSSH) · [SSH keys](https://wiki.archlinux.org/title/SSH_keys) · [Tailscale](https://wiki.archlinux.org/title/Tailscale)

Клиент (`openssh`) ставится с пакетом, а сервер `sshd` включается отдельно.

| Вариант | Что это |
|---|---|
| **Только клиент** | ты подключаешься к другим машинам, а к твоей никто. Дальше ничего делать не нужно |
| ★ **Сервер, доступный только через Tailscale** | сервер включён, но порт открыт в файрволе только для интерфейса Tailscale: снаружи его не видно |
| **Сервер для локальной сети** | порт открыт для всех интерфейсов (строка `tcp dport <порт> accept`) |

`/etc/ssh/sshd_config.d/50-hardening.conf` (порт и пользователя **укажи свои**: у меня нестандартный порт и один пользователь):

```
Port <порт>
PermitRootLogin no
AllowUsers <пользователь>
PubkeyAuthentication yes
PasswordAuthentication yes
KbdInteractiveAuthentication no
MaxAuthTries 3
X11Forwarding no
```

Когда проверишь вход по ключу, поставь `PasswordAuthentication no`. Порт выбери любой свободный. В файрволе (шаг 5) добавь строку для этого порта.

```
sudo systemctl enable --now sshd
sudo pacman -S --needed tailscale
sudo systemctl enable --now tailscaled
sudo tailscale up
```

`tailscale up` печатает ссылку для входа в твой аккаунт Tailscale. После этого машина доступна по SSH с других твоих устройств через сеть Tailscale.

## 7. Менеджер входа Ly

**Wiki:** [Ly](https://wiki.archlinux.org/title/Ly) · [Display manager](https://wiki.archlinux.org/title/Display_manager)

Ly это минимальный менеджер входа прямо на TTY. Нужен, чтобы вход выглядел одинаково и для консоли, и для любой графики. Пока в системе нет графических сессий, он предлагает пункт **shell**. Если Ly не нужен, пропусти шаг и входи через getty.

```
sudo pacman -S --needed ly
sudo systemctl disable getty@tty2.service
sudo systemctl enable ly@tty2.service
sudo reboot
```

На tty1 остаётся обычный getty как запасной вход, на tty2 открывается Ly. Имя службы зависит от версии пакета: на ArchWiki оно описано как `ly.service`, у новых версий это `ly@tty2.service`; проверь `systemctl list-unit-files 'ly*'` и включай то, что есть. Настройки в `/etc/ly/config.ini`. Ly сбрасывает палитру консоли при запуске, поэтому в `/etc/ly/startup.sh` (он выполняется до входа) у меня добавлен блок, который заново применяет цвета из файла выше; без этого после Ly палитра вернулась бы к стандартной. Блок для вставки в конец файла:

```
if [ "$TERM" = "linux" ] && [ -r /etc/zen/console.vtrgb ]; then
	i=0
	while read -r c; do
		printf "\033]P%x%s" ${i} "${c#\#}"
		i=$(( i + 1 ))
	done < /etc/zen/console.vtrgb

	clear # убирает артефакты фона после смены цветов
fi
```

Мои значения (имена ключей зависят от версии пакета, сверься с файлом):

```
animation = none
clock = %a %d.%m %H:%M
hide_version_string = true
hibernate_cmd = systemctl hibernate
hibernate_key = F4
input_len = 34
```

Красивый вид и палитру добавит [глава 08](08-zen.md).

## 8. Критерий «база готова»

- Система грузится (с запросом пароля LUKS, если шифрование) и открывает твою оболочку.
- Работают сеть (`nmcli`), обновления (`sudo pacman -Syu`), zram и дисковый swap.
- Установлены tmux, btop, fastfetch, yazi; шрифт и раскладка консоли правильные.
- Файрвол включён: `sudo nft list ruleset` показывает `policy drop` во входящей цепочке.
- Только Btrfs: есть снимок «base ok», а `snap-pac` делает пары снимков при обновлениях.

Это и есть база: она одинаково воспроизводится на любой машине и годится как отправная точка для любой графической среды. Дальше: [07 · Дополнения](07-extras.md) или графика ([08 · Путь zen](08-zen.md)).

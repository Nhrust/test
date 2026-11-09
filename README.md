# zen

A dark, minimal Arch Linux desktop on Niri: one palette everywhere, Rofi menus
for everyday tasks, a thin Waybar panel, a themed boot chain (Limine, Ly) and
lock screen (gtklock). [Русская версия](README.ru.md)

## Layout

| Path | What |
|---|---|
| `home/` | files for `$HOME`: Niri, Waybar, Rofi, mako, gtklock, foot, fish, tmux, Neovim, Qt/GTK theme, the zen scripts |
| `etc/`, `usr/local/` | system files: pacman, makepkg, logind, sleep, UPower, NetworkManager, nftables, sshd (port 9728, only your user), Ly, zram, hooks |
| `usr/local/share/zen/templates/` | colour templates of system files: the console palette, the boot menu (`efi/limine.conf`) |
| `tools/` | for working on the theme, not installed: `kvantum-svg.py` derives the Kvantum template |
| `hosts/NAME/` | what differs per machine: kernel command line, initramfs modules, hardware rules, snapshots, packages, place and monitors |
| `packages/` | package lists: `base`, `desktop`, `extra` |
| `lists/` | services to enable |
| `po/` | translations of the scripts (gettext) |
| `deploy.sh` | applies everything to an installed system |

## Where things go in `$HOME`

| Path | What |
|---|---|
| `~/.local/bin/` | commands you run or bind: `zen-center` (notifications, calendar, weather), `zen-displays`, `zen-network` (Wi-Fi, Ethernet, Tailscale, settings of each network, a hotspot while Wi-Fi stays connected), `zen-audio` (player, outputs, inputs, levels, applications, Bluetooth), `zen-clipboard`, `zen-power`, `zen-lock`, `zen-step`, and `zen` for maintenance (`zen apply`, `zen diff`, `zen doctor`, `zen gtklock`) |
| `~/.local/lib/zen/` | internals: `bar/` (Waybar and tmux modules), background helpers, the shared `zen.py` and `zen.sh` |
| `~/.local/share/zen/` | data: the gtklock module source and `templates/` — files that carry the palette (mako, GTK, gtklock, Qt, KDE, Kvantum, foot, Niri borders) |
| `~/.config/zen/zen.conf` | your settings |
| `~/.local/state/zen/` | what the menus remember: monitor modes, pinned clipboard entries |
| `zen-*.service` | user services: `zen-idle`, `zen-caffeine`, `zen-autowidth`, `zen-battery`, `zen-cliphist`, `zen-kanshi`, `zen-menu-close` |

## Panel and keys

| Where | Left click | Right click | Wheel |
|---|---|---|---|
| player | pause | next track; middle: previous | seek ±5 s |
| clock, bell | notifications, calendar, weather | do not disturb on/off; middle: clear all | — |
| weather | notifications, calendar, weather | refresh now | — |
| brightness, caffeine | displays | caffeine on/off | brightness |
| volume | sound | mute | volume |
| network | network | Wi-Fi on/off | — |
| muted microphone | unmute | — | — |
| profile, battery | power | next power profile | — |

Mod+Space apps · Mod+Shift+A notifications · Mod+V clipboard · Mod+P displays ·
Mod+N network · Mod+M sound · Mod+L lock · Ctrl+Shift+Esc btop. Inside a menu, Alt+1… or the
icons on top open the other menus.

## Deploy

On a fresh system installed by the guide (docs follow), as your user:

```sh
git clone https://github.com/Nhrust/zen && cd zen
cp -r hosts/zen hosts/$(cat /etc/hostname)   # then edit it for this machine
./deploy.sh --dry-run                            # see every step first
./deploy.sh
```

`deploy.sh` installs the packages, copies the files (every replaced file is
saved to `~/.local/state/zen/backup-<date>/`), removes what older versions installed
(`lists/removed.txt`), builds the translations, writes the colours with
`zen apply`, sets the cursor, enables the services, rebuilds the boot image
when its inputs changed and builds the gtklock module when gtklock changed.

The system runs from the copies, not from the repository. To change
something, edit it in the repository and run `./deploy.sh --no-packages`;
`zen diff` lists what was changed on the system since, so it can be carried
back.

## Tests

`tests/run` checks the menus, the panel modules, `zen apply` and a dry run of
`deploy.sh` against stand-in programs (`tests/mock.py`), in a temporary home
folder; nothing on the system is touched. Needs Python 3 and `msgfmt`.

## Settings

`~/.config/zen/zen.conf` (example in `home/.config/zen/zen.conf.example`):
locale for the zen scripts, weather location and contact, the palette and
the terminal colours. Language, units, first weekday and 12/24-hour time
follow the locale.

## Colours

One palette in `zen.conf` paints everything. `zen apply` renders it into
Rofi and Waybar variables and into the templates: mako, GTK 3/4, gtklock,
Qt (qt5ct, qt6ct, Kvantum, KDE colour scheme), foot, Niri window borders,
the console of every tty (`/etc/zen/console.vtrgb`, set at boot by
`zen-console.service` and by Ly) and the Limine boot menu. Mako, Waybar and
the console reload at once; other programs pick the colours up on restart.

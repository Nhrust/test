# zen

A dark, minimal Arch Linux desktop on Niri: one palette everywhere, Rofi menus
for everyday tasks, a thin Waybar panel, a themed boot chain (Limine, Ly) and
lock screen (gtklock). [Русская версия](README.ru.md)

## Layout

| Path | What |
|---|---|
| `home/` | files for `$HOME`: Niri, Waybar, Rofi, mako, gtklock, foot, fish, tmux, Neovim, Qt/GTK theme, the zen scripts |
| `etc/`, `usr/local/` | system files: pacman, makepkg, logind, sleep, UPower, NetworkManager, nftables, sshd (port 9728, only your user), Ly, zram, hooks |
| `efi/limine.conf` | boot menu |
| `hosts/NAME/` | what differs per machine: kernel command line, initramfs modules, hardware rules, snapshots, packages, place and monitors |
| `packages/` | package lists: `base`, `desktop`, `extra` |
| `lists/` | services to enable |
| `po/` | translations of the scripts (gettext) |
| `deploy.sh` | applies everything to an installed system |

## Where things go in `$HOME`

| Path | What |
|---|---|
| `~/.local/bin/` | commands you run or bind: `zen-center` (notifications, calendar, weather), `zen-displays`, `zen-clipboard`, `zen-power`, `zen-lock`, `zen-step`, and `zen` for maintenance (`zen apply`, `zen gtklock`) |
| `~/.local/lib/zen/` | internals: `bar/` (Waybar and tmux modules), background helpers, the shared `zen.py` and `zen.sh` |
| `~/.local/share/zen/` | data: the gtklock module source, the terminal palette (`terminal.vtrgb`) |
| `~/.config/zen/zen.conf` | your settings |
| `~/.local/state/zen/` | what the menus remember: monitor modes, pinned clipboard entries |
| `zen-*.service` | user services: `zen-idle`, `zen-caffeine`, `zen-autowidth`, `zen-battery`, `zen-cliphist`, `zen-kanshi`, `zen-menu-close` |

## Deploy

On a fresh system installed by the guide (docs follow), as your user:

```sh
git clone https://github.com/Nhrust/zen && cd zen
cp -r hosts/zen hosts/$(cat /etc/hostname)   # then edit it for this machine
./deploy.sh --dry-run                            # see every step first
./deploy.sh
```

`deploy.sh` installs the packages, copies the files (every replaced file is
saved to `~/zen-deploy-backup-<date>/`), builds the translations, palette and
cursor, enables the services, rebuilds the boot image when its inputs changed
and builds the gtklock module.

## Settings

`~/.config/zen/zen.conf` (example in `home/.config/zen/zen.conf.example`):
locale for the zen scripts, weather location and contact, and the palette.
Language, units, first weekday and 12/24-hour time follow the locale.
Run `zen apply` after changing it.

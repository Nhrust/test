# zen

Тёмный минималистичный рабочий стол Arch Linux на Niri: одна палитра везде,
меню Rofi для повседневных задач, тонкая панель Waybar, оформленная цепочка
загрузки (Limine, Ly) и экран блокировки (gtklock). [English](README.md)

## Устройство репозитория

| Путь | Что |
|---|---|
| `home/` | файлы для `$HOME`: Niri, Waybar, Rofi, mako, gtklock, foot, fish, tmux, Neovim, тема Qt/GTK, скрипты zen |
| `etc/`, `usr/local/` | системные файлы: pacman, makepkg, logind, sleep, UPower, NetworkManager, nftables, sshd (порт 9728, вход только вашему пользователю), Ly, zram, хуки |
| `efi/limine.conf` | меню загрузки |
| `hosts/ИМЯ/` | то, что отличается между машинами: строка ядра, модули initramfs, правила железа, снимки, пакеты, город и мониторы |
| `packages/` | списки пакетов: `base`, `desktop`, `extra` |
| `lists/` | сервисы, которые включаются |
| `po/` | переводы скриптов (gettext) |
| `deploy.sh` | раскладывает всё на установленную систему |

## Что где лежит в `$HOME`

| Путь | Что |
|---|---|
| `~/.local/bin/` | команды, которые запускаешь сам или по бинду: `zen-center` (уведомления, календарь, погода), `zen-displays`, `zen-clipboard`, `zen-power`, `zen-lock`, `zen-step` и служебная `zen` (`zen palette`, `zen gtklock`) |
| `~/.local/lib/zen/` | внутренности: `bar/` (модули Waybar и tmux), фоновые помощники, общие `zen.py` и `zen.sh` |
| `~/.local/share/zen/` | данные: исходник модуля gtklock, палитра консоли (`terminal.vtrgb`) |
| `~/.config/zen/zen.conf` | твои настройки |
| `~/.local/state/zen/` | что запоминают меню: режимы мониторов, закреплённые записи буфера |
| `zen-*.service` | пользовательские сервисы: `zen-idle`, `zen-caffeine`, `zen-autowidth`, `zen-battery`, `zen-cliphist`, `zen-kanshi`, `zen-menu-close` |

## Развёртывание

На свежей системе, установленной по гайду (гайды будут в `docs/`), от своего пользователя:

```sh
git clone https://github.com/Nhrust/zen && cd zen
cp -r hosts/zenbook hosts/$(cat /etc/hostname)   # и поправить под эту машину
./deploy.sh --dry-run                            # сначала посмотреть каждый шаг
./deploy.sh
```

`deploy.sh` ставит пакеты, копирует файлы (каждый заменяемый файл сохраняется
в `~/zen-deploy-backup-<дата>/`), собирает переводы, палитру и курсор, включает
сервисы, пересобирает образ загрузки, если поменялось то, из чего он собирается,
и собирает модуль gtklock.

## Настройки

`~/.config/zen/zen.conf` (пример — `home/.config/zen/zen.conf.example`):
локаль для скриптов zen, город и контакт для погоды, палитра. Язык, единицы,
первый день недели и 12/24-часовое время берутся из локали. После смены
палитры — `zen palette`.

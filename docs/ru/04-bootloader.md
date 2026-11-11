# 04 · Загрузчик

Всё ещё внутри chroot ([03 · Система](03-system.md)). Выбор и сравнение: [глава 00](00-stack.md#загрузчик). Здесь по каждому загрузчику два пути: **UKI** (образ уже собран на ESP) и **классика** (ядро и initramfs в `/boot`).

**Wiki:** [Arch boot process](https://wiki.archlinux.org/title/Arch_boot_process) · [Unified kernel image](https://wiki.archlinux.org/title/Unified_kernel_image) · [Limine](https://wiki.archlinux.org/title/Limine) · [systemd-boot](https://wiki.archlinux.org/title/Systemd-boot) · [GRUB](https://wiki.archlinux.org/title/GRUB) · [efibootmgr](https://wiki.archlinux.org/title/Unified_Extensible_Firmware_Interface#efibootmgr)

| Загрузчик | UKI | Классика | ESP монтируется в |
|---|---|---|---|
| ★ Limine | да | да, ядро на ESP | `/efi` (UKI), `/boot` (классика) |
| systemd-boot | да | да, ядро на ESP | `/efi` (UKI), `/boot` (классика) |
| GRUB | через `chainloader` | да | `/efi` (UKI), `/boot` (классика) |
| EFISTUB | да | да, ядро на ESP | `/efi` (UKI), `/boot` (классика) |

Классический путь требует ESP в `/boot`, и решать это надо **ещё в главе 02**: ESP должна быть смонтирована в `/mnt/boot` до `pacstrap`, иначе ядро окажется в корне, а не на ESP. Если ты уже поставил систему с ESP в `/efi`, выбери UKI или начни монтирование заново. В командах ниже для классики замени `/efi` на `/boot`.

Эта глава проверялась по ArchWiki, но не прогонялась установкой. Особенно это касается GRUB и классических путей: перед использованием сверь с вики.

## ★ Limine

Limine кладёт один файл `BOOTX64.EFI` на ESP, а конфиг `limine.conf` лежит в корне ESP. Копия в стандартный путь `EFI/BOOT` спасёт, если прошивка потеряет запись.

```
mkdir -p /efi/EFI/arch-limine /efi/EFI/BOOT
install -Dm644 /usr/share/limine/BOOTX64.EFI /efi/EFI/arch-limine/BOOTX64.EFI
install -Dm644 /usr/share/limine/BOOTX64.EFI /efi/EFI/BOOT/BOOTX64.EFI
efibootmgr --create --disk /dev/nvme0n1 --part 1 \
  --label "Arch Linux (Limine)" --loader '\EFI\arch-limine\BOOTX64.EFI' --unicode
```

`--part 1` это номер ESP на диске (подставь свой, если не первый).

### UKI

`/efi/limine.conf`:

```
timeout: 5
default_entry: 1
editor_enabled: no
terse: yes
quiet: yes
interface_help_hidden: yes

/Arch Linux
    protocol: efi
    path: boot():/EFI/Linux/arch-linux.efi

/Arch Linux LTS
    protocol: efi
    path: boot():/EFI/Linux/arch-linux-lts.efi
```

Проверь, что файл на месте и читается: `ls -l /efi/limine.conf && cat /efi/limine.conf`. Limine ищет конфиг сначала рядом со своим EFI-файлом, потом в корне, `/boot`, `/limine` и `/boot/limine` каждого раздела диска. Если ESP смонтирована не в `/efi`, или файл лежит в `/boot/limine.conf` на зашифрованном корне, меню будет пустым: загрузчик читает только FAT.

Блок LTS нужен, только если ставил запасное ядро. `editor_enabled: no` запрещает правку параметров ядра из меню, `terse` и `quiet` убирают шум при запуске, `interface_help_hidden` прячет подсказки по клавишам. Цвета меню и надпись добавит [глава 08](08-zen.md).

### Классика

```
/Arch Linux
    protocol: linux
    path: boot():/vmlinuz-linux
    cmdline: <строка из /etc/kernel/cmdline>
    module_path: boot():/initramfs-linux.img
```

Здесь `boot()` это раздел, где лежит ядро: Limine читает FAT, а зашифрованный корень не прочтёт, поэтому ядро и образ должны лежать на ESP (смонтированной в `/boot`).

### Обновление вместе с пакетом

Pacman-хук копирует новый загрузчик после обновления пакета: `/etc/pacman.d/hooks/99-limine-efi.hook`

```
[Trigger]
Operation = Install
Operation = Upgrade
Type = Package
Target = limine

[Action]
When = PostTransaction
Exec = /usr/bin/install -Dm644 /usr/share/limine/BOOTX64.EFI /efi/EFI/arch-limine/BOOTX64.EFI
```

(Копию в `EFI/BOOT` хук не обновляет; при желании добавь вторую команду.)

## systemd-boot

systemd-boot читает только FAT, поэтому UKI и ядро должны лежать на ESP.

```
bootctl --esp-path=/efi install
bootctl --esp-path=/efi status
systemctl enable systemd-boot-update.service
```

`/efi/loader/loader.conf`:

```
timeout 3
console-mode max
editor no
```

`editor no` запрещает правку параметров ядра из меню: иначе любой у клавиатуры мог бы запустить систему с `init=/bin/sh`.

### UKI

Ничего больше не нужно: systemd-boot сам находит образы в `EFI/Linux` на ESP.

### Классика

ESP смонтирована в `/boot` (`bootctl install` без `--esp-path`). Запись `/boot/loader/entries/arch.conf`:

```
title   Arch Linux
linux   /vmlinuz-linux
initrd  /initramfs-linux.img
options <строка из /etc/kernel/cmdline>
```

Отдельная строка `initrd` для микрокода не нужна: хук `microcode` кладёт его внутрь initramfs.

## GRUB

**Wiki:** [GRUB](https://wiki.archlinux.org/title/GRUB)

```
pacman -S --needed grub          # если не ставил в pacstrap
```

> GRUB плохо дружит с шифрованным `/boot` на LUKS2: он умеет только PBKDF2, а `cryptsetup` по умолчанию создаёт argon2id. Самый простой путь, который описан ниже: держать ядро на ESP (классика) или запускать UKI.

### UKI (через chainloader)

```
grub-install --target=x86_64-efi --efi-directory=/efi --bootloader-id=GRUB
```

GRUB загружает только свой `grub.cfg`, а UKI запускает как обычный EFI-файл. Узнай UUID ESP (`blkid /dev/nvme0n1p1`) и добавь запись в `/etc/grub.d/40_custom`:

```
menuentry "Arch Linux (UKI)" {
    insmod part_gpt
    insmod fat
    insmod chain
    search --no-floppy --fs-uuid --set=root <UUID-ESP>
    chainloader /EFI/Linux/arch-linux.efi
}
```

Отключи автогенерацию записей для ядер (в `/boot` на зашифрованном корне GRUB их всё равно не прочтёт) и собери конфиг:

```
chmod -x /etc/grub.d/10_linux
grub-mkconfig -o /boot/grub/grub.cfg
```

Запись для LTS делается копией блока с `arch-linux-lts.efi`.

### Классика

ESP смонтирована в `/boot`, ядра лежат на ней:

```
grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=GRUB
```

В `/etc/default/grub` впиши параметры ядра из главы 03:

```
GRUB_CMDLINE_LINUX="rd.luks.name=<UUID-LUKS>=cryptlvm rd.lvm.lv=vg0/root root=/dev/vg0/root rootflags=subvol=/@ resume=/dev/vg0/swap"
```

(`rw` GRUB добавляет сам; `quiet` и `loglevel` уже есть в `GRUB_CMDLINE_LINUX_DEFAULT`.) Затем:

```
grub-mkconfig -o /boot/grub/grub.cfg
```

Проверь в `/boot/grub/grub.cfg`, что строка `linux` содержит нужные параметры.

## EFISTUB (без загрузчика)

Прошивка сама запускает UKI по записи в NVRAM.

```
efibootmgr --create --disk /dev/nvme0n1 --part 1 \
  --label "Arch Linux" --loader '\EFI\Linux\arch-linux.efi' --unicode
efibootmgr --create --disk /dev/nvme0n1 --part 1 \
  --label "Arch Linux LTS" --loader '\EFI\Linux\arch-linux-lts.efi' --unicode
efibootmgr -v
```

Порядок загрузки меняется командой `efibootmgr -o <номера через запятую>`. Меню выбора ядра придётся открывать из прошивки.

**Запасной вход.** Копия образа в стандартном пути спасает, если прошивка потеряет записи:

```
mkdir -p /efi/EFI/BOOT
cp /efi/EFI/Linux/arch-linux.efi /efi/EFI/BOOT/BOOTX64.EFI
```

Копия устаревает при обновлении ядра. Чтобы она обновлялась сама, `/etc/pacman.d/hooks/99-uki-fallback.hook`:

```
[Trigger]
Operation = Install
Operation = Upgrade
Type = Package
Target = linux

[Action]
When = PostTransaction
Exec = /usr/bin/cp /efi/EFI/Linux/arch-linux.efi /efi/EFI/BOOT/BOOTX64.EFI
```

Классика через EFISTUB: ядро и initramfs на ESP, запись с параметрами:

```
efibootmgr --create --disk /dev/nvme0n1 --part 1 --label "Arch Linux" \
  --loader '\vmlinuz-linux' --unicode '<строка из /etc/kernel/cmdline> initrd=\initramfs-linux.img'
```

## Проверка

```
efibootmgr -v                 # запись и путь к загрузчику (Limine, GRUB, EFISTUB)
ls -lh /efi/EFI/Linux         # UKI на месте
```

Если записи нет в меню прошивки, запусти запасной `\EFI\BOOT\BOOTX64.EFI`.

Дальше: пользователь, сеть, swap и первая загрузка, глава 05.

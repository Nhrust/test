# 03 · Система

Установка пакетов, Snapper (для Btrfs), fstab, базовая настройка в chroot, initramfs и UKI. Предыдущий шаг: [02 · Разметка](02-partition.md).

Примеры значений (`/dev/nvme0n1`, `archbox`, `nvim`…): [01 · Подготовка, шаг 5](01-prepare.md#5-значения-в-командах).

## 1. pacstrap

**Wiki:** [Install essential packages](https://wiki.archlinux.org/title/Installation_guide#Install_essential_packages)

★ команда целиком (LUKS, LVM, Btrfs, Limine, запасное ядро). Редактор `neovim` ставится сразу, чтобы всё дальше править в chroot именно им:

```
pacstrap -K /mnt base base-devel linux linux-lts linux-headers linux-lts-headers linux-firmware \
  amd-ucode mkinitcpio cryptsetup lvm2 btrfs-progs snapper dosfstools efibootmgr limine \
  sudo neovim man-db man-pages texinfo less git gettext \
  networkmanager nftables openssh zram-generator pacman-contrib reflector terminus-font
```

Под свой выбор поменяй список:

| Выбор | Что сделать с командой |
|---|---|
| процессор Intel | `amd-ucode` на `intel-ucode` |
| не нужны заголовки ядра (для DKMS-модулей) | убери `linux-headers linux-lts-headers` |
| без SSH-сервера | убери `openssh` (клиент тоже в нём) |
| без запасного ядра | убери `linux-lts linux-lts-headers` |
| без шифрования | убери `cryptsetup` |
| без LVM | убери `lvm2` |
| ext4 | убери `btrfs-progs snapper` |
| XFS | замени `btrfs-progs snapper` на `xfsprogs` |
| другой загрузчик | `limine` замени на `grub` (GRUB) или убери (systemd-boot, EFISTUB) |
| без swap в ОЗУ | убери `zram-generator` |
| другой редактор | `neovim` замени на `vim` или `nano` |
| zsh вместо fish | добавь `zsh` (подробнее в главе 06) |

Что это за пакеты:

| Пакеты | Зачем |
|---|---|
| `base linux linux-firmware` | система, ядро, прошивки |
| `linux-lts` | запасное ядро: если свежее сломает загрузку, загрузишься с него |
| `amd-ucode` (или `intel-ucode`), `mkinitcpio` | микрокод процессора, сборка initramfs и UKI |
| `efibootmgr dosfstools` | записи UEFI, FAT |
| `networkmanager` | сеть установленной системы |
| `sudo`, `neovim`, `git`, `base-devel`, `gettext` | работа, редактор, сборка пакетов |
| `man-db man-pages texinfo less` | справка |
| `nftables openssh` | файрвол и SSH (глава 06) |
| `pacman-contrib reflector` | `paccache`, зеркала |
| `linux-headers linux-lts-headers` | заголовки для модулей DKMS |
| `zram-generator terminus-font` | сжатый swap, шрифт консоли |

## 2. Snapper до fstab (только Btrfs)

**Wiki:** [Snapper](https://wiki.archlinux.org/title/Snapper)

Пропусти этот раздел для ext4 и XFS. Устройство корня (`/dev/vg0/root`) замени по таблице из [главы 02](02-partition.md), если у тебя другая схема. Snapper при создании конфига делает вложенный подтом `.snapshots` внутри `@`. Нужен отдельный `@snapshots` рядом, чтобы откат `@` не уничтожил снимки. Поэтому конфиг создаётся **сейчас**, до `genfstab`, подтом переезжает, и fstab сразу получит правильную запись. `snap-pac` в chroot не ставим: его хук падает без работающего Snapper (поставим после первой загрузки).

```
arch-chroot /mnt snapper --no-dbus -c root create-config /
mkdir /btrfs-top
mount -o subvolid=5 /dev/vg0/root /btrfs-top
mv /btrfs-top/@/.snapshots /btrfs-top/@snapshots
umount /btrfs-top; rmdir /btrfs-top
mkdir /mnt/.snapshots
mount -o subvol=@snapshots,compress=zstd:3 /dev/vg0/root /mnt/.snapshots
chmod 750 /mnt/.snapshots
```

Эта же схема на ArchWiki на уже работающей системе: размонтировать и удалить каталог `/.snapshots`, выполнить `snapper -c root create-config /`, затем смонтировать `@snapshots` на `/.snapshots` (через fstab) и поставить права 750.

## 3. fstab

**Wiki:** [fstab](https://wiki.archlinux.org/title/Fstab)

Файл создаётся сейчас, а проверяется и правится уже в chroot (шаг 4): `neovim` стоит в системе, в live-среде его нет.

```
genfstab -U /mnt > /mnt/etc/fstab
cat /mnt/etc/fstab
```

Что проверить в шаге 4:

- у swap (если есть) добавь `pri=10`: zram получит 100 и будет использоваться первым;
- у ESP остаются `fmask=0077,dmask=0077`;
- для Btrfs есть пять записей: `@`, `@home`, `@var_log`, `@var_cache`, `@snapshots`;
- `genfstab` копирует параметры текущего монтирования: `ssd`, `space_cache=v2`, номер подтома. Оставляй их. `discard=async` появится только если диск сообщает о поддержке TRIM: поверх LUKS без `allow-discards` (мой случай) его не будет, и это нормально (см. [главу 07](07-extras.md#1-trim-через-luks)).

Пример для ★ (UUID у каждого свои, не публикуй их):

```
UUID=<root>  /            btrfs  rw,relatime,compress=zstd:3,subvol=/@           0 0
UUID=<root>  /home        btrfs  rw,relatime,compress=zstd:3,subvol=/@home       0 0
UUID=<root>  /var/log     btrfs  rw,relatime,compress=zstd:3,subvol=/@var_log    0 0
UUID=<root>  /var/cache   btrfs  rw,relatime,compress=zstd:3,subvol=/@var_cache  0 0
UUID=<root>  /.snapshots  btrfs  rw,relatime,compress=zstd:3,subvol=/@snapshots  0 0
UUID=<esp>   /efi         vfat   rw,relatime,fmask=0077,dmask=0077               0 2
UUID=<swap>  none         swap   defaults,pri=10                                 0 0
```

## 4. Вход в систему: время, локаль, имя

**Wiki:** [Configure the system](https://wiki.archlinux.org/title/Installation_guide#Configure_the_system) · [Locale](https://wiki.archlinux.org/title/Locale) · [Keyboard configuration](https://wiki.archlinux.org/title/Linux_console/Keyboard_configuration) · [Console fonts](https://wiki.archlinux.org/title/Linux_console#Fonts)

```
arch-chroot /mnt
```

Дальше всё внутри chroot.

### Минимальный конфиг neovim

Чтобы редактировать удобно сразу, создай минимальный конфиг (он взят из моего: номера строк, отступы по 4 пробела, возврат курсора на прежнее место). Мой полный конфиг с плагинами придёт в [главе 08](08-zen.md).

```
mkdir -p /root/.config/nvim
cat > /root/.config/nvim/init.lua <<'LUA'
vim.opt.number = true

vim.opt.tabstop = 4
vim.opt.shiftwidth = 4
vim.opt.softtabstop = 4
vim.opt.expandtab = true

vim.opt.termguicolors = false

-- вернуть курсор на место, где закрыл файл
vim.api.nvim_create_autocmd("BufReadPost", {
  callback = function(args)
    local ft = vim.bo[args.buf].filetype
    if ft == "gitcommit" or ft == "gitrebase" then return end
    local mark = vim.api.nvim_buf_get_mark(args.buf, '"')
    if mark[1] > 0 and mark[1] <= vim.api.nvim_buf_line_count(args.buf) then
      pcall(vim.api.nvim_win_set_cursor, 0, mark)
    end
  end,
})
LUA
```

Если выбрал `nano` или `vim`, этот шаг пропусти и дальше пиши свой редактор.

### fstab

```
nvim /etc/fstab
```

Правки: см. шаг 3 (`pri=10` у swap, `fmask/dmask` у ESP).

### Время, локаль, имя

```
ln -sf /usr/share/zoneinfo/Europe/Moscow /etc/localtime
hwclock --systohc
nvim /etc/locale.gen                 # раскомментируй en_US.UTF-8 UTF-8 и, если нужна, свою (у меня ещё ru_RU.UTF-8 UTF-8)
locale-gen
echo archbox > /etc/hostname
```

`/etc/hosts` (замени `archbox` на своё имя машины):

```
127.0.0.1        localhost
::1              localhost
127.0.0.1        archbox.localdomain archbox
```

`/etc/locale.conf`:

```
LANG=en_US.UTF-8
```

`/etc/vconsole.conf`:

```
KEYMAP=us
FONT=ter-v20n
```

★ Язык системы английский (проще искать ошибки), русская локаль сгенерирована для приложений. Файл `vconsole.conf` читает хук `sd-vconsole`: шрифт и раскладка работают уже на запросе пароля. `ter-v16n` мельче, `ter-v24n` и `ter-v32n` для HiDPI.

## 5. initramfs

**Wiki:** [mkinitcpio](https://wiki.archlinux.org/title/Mkinitcpio) · [Kernel parameters](https://wiki.archlinux.org/title/Kernel_parameters)

Используется initramfs на systemd (хук `systemd` вместо `udev`): он даёт запрос пароля, `sd-vconsole` и возобновление из гибернации без отдельного хука `resume`. Хуки зависят от схемы:

| Схема | HOOKS |
|---|---|
| только LUKS (ext4, XFS) | `(base systemd autodetect microcode modconf kms keyboard sd-vconsole block sd-encrypt filesystems fsck)` |
| LUKS + LVM (★) | `(base systemd autodetect microcode modconf kms keyboard sd-vconsole block sd-encrypt lvm2 filesystems fsck)` |
| LVM без шифрования | `(base systemd autodetect microcode modconf kms keyboard sd-vconsole block lvm2 filesystems fsck)` |
| без шифрования и LVM | `(base systemd autodetect microcode modconf kms keyboard sd-vconsole block filesystems fsck)` |

Отредактируй строку `HOOKS=` в `/etc/mkinitcpio.conf`; там же, по желанию, строку `MODULES=`:

```
nvim /etc/mkinitcpio.conf
```

**Модули** зависят от железа. Видеодрайвер, загруженный заранее, делает красивее запрос пароля: `MODULES=(amdgpu)` для AMD, `MODULES=(i915)` для Intel, для NVIDIA и остального оставь пусто. В моём профиле ещё `asus_nb_wmi` и `FILES=(/etc/udev/rules.d/81-asus-kbd-backlight.rules)`: это под мой ноутбук ASUS, тебе они не нужны.

Порядок важен: сначала `sd-vconsole`, потом `sd-encrypt` (открывает LUKS), после него `lvm2` (активирует тома), затем `filesystems`.

> Для LVM в systemd-initramfs ArchWiki называет хук `sd-lvm2`, а у меня стабильно работает `lvm2`. Это не проверено в VM: если загрузка не находит тома, замени `lvm2` на `sd-lvm2` и пересобери образ.

## 6. Параметры ядра

Файл `/etc/kernel/cmdline` содержит **одну строку**. UUID берём у **LUKS-раздела** (не у файловой системы внутри него): `cryptsetup luksUUID /dev/nvme0n1p2`. Если шифрования и LVM нет, нужен UUID корня: `blkid /dev/nvme0n1p2`.

Строка собирается из частей:

| Часть | Когда |
|---|---|
| `rd.luks.name=<UUID-LUKS>=cryptlvm` | есть LUKS |
| `rd.lvm.lv=vg0/root` и `rd.lvm.lv=vg0/swap` | есть LVM (вторая только при swap-томе) |
| `root=/dev/vg0/root` | LVM |
| `root=/dev/mapper/cryptlvm` | LUKS без LVM |
| `root=UUID=<UUID-ROOT>` | без LUKS и LVM |
| `rootflags=subvol=/@` | Btrfs |
| `rw` | всегда |
| `resume=/dev/vg0/swap` | гибернация через swap-том |
| `quiet loglevel=3` и остальные тихие | всегда (по желанию) |

Готовые примеры:

**★** (LUKS, LVM, Btrfs, гибернация):

```
rd.luks.name=<UUID-LUKS>=cryptlvm rd.lvm.lv=vg0/root rd.lvm.lv=vg0/swap root=/dev/vg0/root rootflags=subvol=/@ rw resume=/dev/vg0/swap quiet loglevel=3 systemd.show_status=error rd.systemd.show_status=error rd.udev.log_level=3
```

**LUKS, ext4:**

```
rd.luks.name=<UUID-LUKS>=cryptlvm root=/dev/mapper/cryptlvm rw quiet loglevel=3
```

**LUKS, LVM, ext4:**

```
rd.luks.name=<UUID-LUKS>=cryptlvm rd.lvm.lv=vg0/root root=/dev/vg0/root rw quiet loglevel=3
```

**Без шифрования и LVM:**

```
root=UUID=<UUID-ROOT> rw quiet loglevel=3
```

Создай файл и впиши свою строку:

```
nvim /etc/kernel/cmdline
```

`quiet loglevel=3 …show_status=error` убирают шум загрузки, для отладки удали их. Пароль в параметры не пишется никогда. Необязательно добавить `rd.luks.options=discard` для TRIM через LUKS (компромисс описан в главе 07).

## 7. Образы: UKI или классика

**Wiki:** [Unified kernel image](https://wiki.archlinux.org/title/Unified_kernel_image)

Выбор в [главе 00](00-stack.md#формат-ядра).

### ★ UKI

UKI склеивает ядро, initramfs и параметры в один файл на ESP; загрузчик просто запускает его.

`/etc/mkinitcpio.d/linux.preset`:

```
ALL_kver="/boot/vmlinuz-linux"
PRESETS=('default')

default_uki="/efi/EFI/Linux/arch-linux.efi"
default_options="--cmdline /etc/kernel/cmdline"
```

Если ставил запасное ядро, `/etc/mkinitcpio.d/linux-lts.preset`:

```
ALL_kver="/boot/vmlinuz-linux-lts"
PRESETS=('default')

default_uki="/efi/EFI/Linux/arch-linux-lts.efi"
default_options="--cmdline /etc/kernel/cmdline"
```

Формат файла зависит от версии пакета, не заменяй чужой файл вслепую: сверь с тем, что лежит в системе.

```
mkdir -p /efi/EFI/Linux
mkinitcpio -P
rm -f /boot/initramfs-linux*.img            # образы, которые pacstrap собрал по старым пресетам
ls -lh /efi/EFI/Linux/ /boot
```

В `/boot` остаются только `vmlinuz-*`: из них собирается UKI.

### Классика

Оставь образ в `/boot` и убери fallback. `/etc/mkinitcpio.d/linux.preset`:

```
ALL_kver="/boot/vmlinuz-linux"
PRESETS=('default')

default_image="/boot/initramfs-linux.img"
```

То же для `linux-lts` (`vmlinuz-linux-lts`, `initramfs-linux-lts.img`). Параметры ядра тогда задаются в конфиге загрузчика (глава 04), а `/etc/kernel/cmdline` не используется. Образы собираются командой `mkinitcpio -P`.

Дальше: загрузчик, глава 04.

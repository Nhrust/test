# 05 · Пользователь, сеть, swap и первая загрузка

Всё ещё в chroot ([04 · Загрузчик](04-bootloader.md)); в конце выходим и перезагружаемся. Примеры значений: [01 · Подготовка, шаг 5](01-prepare.md#5-значения-в-командах).

## 1. Пользователь и sudo

**Wiki:** [Users and groups](https://wiki.archlinux.org/title/Users_and_groups) · [sudo](https://wiki.archlinux.org/title/Sudo)

```
passwd
useradd -m -G wheel -s /bin/bash user
passwd user
EDITOR=nvim visudo           # раскомментируй строку: %wheel ALL=(ALL:ALL) ALL
```

Оболочка пока `bash`: другую подключим в главе 06, чтобы не остаться без рабочего входа. Если ставил `nano` или `vim`, пиши свой редактор в `EDITOR=`.

Минимальный конфиг neovim из [главы 03](03-system.md#минимальный-конфиг-neovim) нужен и пользователю:

```
mkdir -p /home/user/.config
cp -r /root/.config/nvim /home/user/.config/
chown -R user:user /home/user/.config
```

## 2. Сеть и службы

**Wiki:** [NetworkManager](https://wiki.archlinux.org/title/NetworkManager) · [systemd-resolved](https://wiki.archlinux.org/title/Systemd-resolved) · [systemd-timesyncd](https://wiki.archlinux.org/title/Systemd-timesyncd) · [systemd-networkd](https://wiki.archlinux.org/title/Systemd-networkd)

| Вариант | За | Против |
|---|---|---|
| ★ **NetworkManager + systemd-resolved** | Wi-Fi и VPN удобно из `nmcli`, DNS отдельной службой | тяжелее |
| **systemd-networkd + iwd** | легче, нет лишнего демона | Wi-Fi и VPN настраиваются руками; для серверов |

```
systemctl enable NetworkManager systemd-resolved systemd-timesyncd
```

`/etc/NetworkManager/conf.d/dns.conf`:

```
[main]
dns=systemd-resolved
```

`/etc/resolv.conf` заменяется ссылкой **после выхода из chroot** (в chroot файл занят): это шаг 5 этой главы.

**Службы по файловой системе.**

```
systemctl enable fstrim.timer                                     # только если TRIM разрешён (глава 07); у меня не включён, потому что поверх LUKS он выключен
systemctl enable snapper-timeline.timer snapper-cleanup.timer     # только Btrfs со Snapper
```

Только Btrfs: первый снимок «чистой системы» (в chroot):

```
snapper --no-dbus -c root create --description "Initial configured system"
```

Сколько снимков хранить, задаёт `/etc/snapper/configs/root` (создан в главе 03). У меня стоят такие значения, остальные по умолчанию:

```
NUMBER_CLEANUP="yes"
NUMBER_MIN_AGE="3600"
NUMBER_LIMIT="50"
NUMBER_LIMIT_IMPORTANT="10"
TIMELINE_CREATE="yes"
TIMELINE_CLEANUP="yes"
TIMELINE_MIN_AGE="3600"
TIMELINE_LIMIT_HOURLY="6"
TIMELINE_LIMIT_DAILY="4"
TIMELINE_LIMIT_WEEKLY="2"
TIMELINE_LIMIT_MONTHLY="1"
TIMELINE_LIMIT_QUARTERLY="0"
TIMELINE_LIMIT_YEARLY="0"
EMPTY_PRE_POST_CLEANUP="yes"
EMPTY_PRE_POST_MIN_AGE="3600"
```

Меньше снимков занимают меньше места; подбери числа под свой диск.

### Правила Wi-Fi для твоей страны

Без этого карта работает по самым строгим мировым правилам: не запускает точку доступа на 5 ГГц и только слушает этот диапазон. Нужны пакет `wireless-regdb` и код страны:

```
pacman -S --needed wireless-regdb
```

`/etc/modprobe.d/cfg80211.conf` (код страны **укажи свой**: у меня `RU`, `US`, `DE` и так далее):

```
options cfg80211 ieee80211_regdom=RU
```

## 3. Swap

**Wiki:** [Zram](https://wiki.archlinux.org/title/Zram) · [Swap](https://wiki.archlinux.org/title/Swap) · [Power management/Suspend and hibernate](https://wiki.archlinux.org/title/Power_management/Suspend_and_hibernate)

Выбор: [глава 00](00-stack.md#4-swap). Если взят swap-том, он уже создан и смонтирован (глава 02), ему нужен только `pri=10` в fstab (глава 03).

### zram (★ и вариант «только zram»)

`/etc/systemd/zram-generator.conf`:

```
[zram0]
zram-size = min(ram / 2, 8192)
compression-algorithm = zstd
swap-priority = 100
```

Приоритет 100 против 10 у дискового swap: сначала используется zram.

### Swap-файл (вместо тома)

Не создавай swap-том в главе 02, если выбрал файл.

**ext4 или XFS:**

```
mkswap -U clear --size 16G --file /swapfile
echo '/swapfile none swap defaults,pri=10 0 0' >> /etc/fstab
swapon /swapfile
```

**Btrfs:** swap-файл должен лежать в подтоме без сжатия и CoW; для этого его создаёт специальная команда.

```
mount -o subvolid=5 /dev/vg0/root /mnt           # корневой уровень, если ещё не смонтирован
btrfs subvolume create /mnt/@swap
umount /mnt
mkdir /swap
mount -o subvol=@swap /dev/vg0/root /swap
btrfs filesystem mkswapfile --size 16g --uuid clear /swap/swapfile
echo '/dev/vg0/root /swap btrfs subvol=@swap 0 0' >> /etc/fstab
echo '/swap/swapfile none swap defaults,pri=10 0 0' >> /etc/fstab
```

Гибернация через swap-файл дополнительно требует в параметрах ядра `resume=UUID=<UUID-корня>` и `resume_offset=<смещение>` вместо `resume=/dev/vg0/swap`. Смещение: `filefrag -v /swapfile` (ext4, первое значение физического смещения) или `btrfs inspect-internal map-swapfile -r /swap/swapfile` (Btrfs). Подробности: wiki «Power management/Suspend and hibernate». Эти шаги я не прогонял.

### Гибернация и кнопки

Для гибернации нужен дисковый swap не меньше ОЗУ и параметр `resume=` (в ★ он уже в cmdline; отдельный хук `resume` не нужен, потому что в initramfs стоит `systemd`).

`/etc/systemd/logind.conf`:

```
[Login]
HandlePowerKey=hibernate
HandleLidSwitch=lock
HandleLidSwitchExternalPower=lock
HandleLidSwitchDocked=lock
PowerKeyIgnoreInhibited=yes
```

`/etc/systemd/sleep.conf`:

```
[Sleep]
AllowHibernation=yes
HibernateMode=shutdown
HibernateOnACPower=yes
```

Кнопка питания усыпляет на диск, крышка только блокирует экран (блокировку обеспечивает графическая часть: до неё крышка ничего не делает). Без гибернации оставь значения по умолчанию.

## 4. Проверка перед выходом

```
mkinitcpio -P
ls -lh /efi/EFI/Linux        # или /boot для классики
efibootmgr -v                # если загрузчик создаёт запись
```

Если что-то не так, исправляй здесь, в chroot: после перезагрузки это будет труднее.

## 5. Первая загрузка

**Wiki:** [Reboot](https://wiki.archlinux.org/title/Installation_guide#Reboot)

```
exit                                                            # из chroot
ln -sf ../run/systemd/resolve/stub-resolv.conf /mnt/etc/resolv.conf
umount -R /mnt
swapoff /dev/vg0/swap          # если был дисковый swap
vgchange -an vg0               # если был LVM
cryptsetup close cryptlvm      # если было шифрование
reboot
```

Достань флешку. Ожидаемый порядок: прошивка → загрузчик → UKI → запрос пароля LUKS → приглашение входа. Войди как обычный пользователь и проверь:

```
nmcli device wifi connect "<SSID>" --ask       # Wi-Fi
lsblk -f; findmnt -R /; swapon --show
resolvectl status | head
efibootmgr
sudo snapper -c root list                      # Btrfs
sudo pacman -S --needed snap-pac               # Btrfs: снимки до и после каждой операции pacman
sudo pacman -Syu
```

> **Проверь:** пароль LUKS спрашивается один раз; есть сеть; `swapon --show` показывает zram (приоритет 100) и дисковый swap (10). Снимок виден в `snapper list`: сделай ещё один, `sudo snapper -c root create -d "base ok"`.

База готова. Дальше: [06 · Комфортный TTY](06-tty.md) (оболочка, редактор, инструменты, файрвол, Ly).

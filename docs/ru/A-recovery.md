# A · Восстановление

**Wiki:** [chroot](https://wiki.archlinux.org/title/Chroot) · [dm-crypt: Backup and restore](https://wiki.archlinux.org/title/Dm-crypt/Device_encryption#Backup_and_restore)

Загрузись с флешки (как в [главе 01](01-prepare.md)) и зайди в установленную систему через chroot.

## 1. Вход в систему из live-среды

Команды зависят от схемы. Устройство корня: `/dev/vg0/root` при LVM, `/dev/mapper/cryptlvm` при одном LUKS, раздел при остальных.

**★ LUKS, LVM, Btrfs:**

```
cryptsetup open /dev/nvme0n1p2 cryptlvm
vgchange -ay vg0
mount -o subvol=@ /dev/vg0/root /mnt
mount --mkdir -o subvol=@home /dev/vg0/root /mnt/home
mount --mkdir -o subvol=@var_log /dev/vg0/root /mnt/var/log
mount --mkdir -o subvol=@var_cache /dev/vg0/root /mnt/var/cache
mount --mkdir -o subvol=@snapshots /dev/vg0/root /mnt/.snapshots
mount --mkdir /dev/nvme0n1p1 /mnt/efi
arch-chroot /mnt
```

**Другие схемы:**

- Без Btrfs: корень монтируется простым `mount <устройство-корня> /mnt`, подтома и `.snapshots` не нужны.
- Без LUKS: пропусти `cryptsetup open`. Без LVM: пропусти `vgchange -ay vg0`.
- ESP монтируется в `/mnt/efi` (UKI) или `/mnt/boot` (классика).

## 2. Пересобрать образ (UKI)

После отката снимка Btrfs, неудачного обновления ядра или правки параметров ядра:

```
mkinitcpio -P
ls -lh /efi/EFI/Linux
```

Если используется Secure Boot, образ нужно заново подписать (`sbctl sign-all`); для GRUB и Limine файлы загрузчика обновляются по главе 04.

**Откат снимка и UKI.** При откате `@` ядро и модули возвращаются к старой версии, а UKI на ESP остаётся новым (оба, включая LTS): версии расходятся, и часть модулей не загрузится. Запасное ядро тут не помогает, оно откатывается вместе с корнем. Правильное лечение: загрузись с флешки и пересобери образы командой выше, она соберёт UKI из того ядра, которое лежит в откатанной системе.

## 3. Если не грузится после обновления

Выбери в меню загрузчика запасное ядро (LTS): оно подходит, если сломал обновление свежего ядра. Если ломается initramfs, сверь хуки ([глава 03, шаг 5](03-system.md#5-initramfs)) и UUID в параметрах ядра (шаг 6).

## 4. Копия заголовка LUKS

Если заголовок LUKS повреждён, без его копии данные не вернуть. Сделай копию и храни её **вне этого диска** и не публикуй:

```
sudo cryptsetup luksHeaderBackup /dev/nvme0n1p2 --header-backup-file luks-header.img
```

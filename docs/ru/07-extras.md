# 07 · Дополнения

Необязательные модули поверх базы ([06 · Комфортный TTY](06-tty.md)). Каждый можно взять отдельно; для связки Secure Boot + TPM2 порядок ниже важен.

**Что из этого у меня.** Из этой главы в моей системе есть только `restic` для копий и обслуживание снимков (лимиты в [главе 05](05-first-boot.md)). TRIM через LUKS, Secure Boot, TPM2, AUR-помощник, `btrfs scrub`, `reflector.timer` и `fwupd` у меня не включены: это варианты для тех, кому они нужны, без пометки ★.

> Подробности по Secure Boot и TPM2 я сверял с ArchWiki, но на живой машине не прогонял. Оба модуля могут сделать систему незагружаемой при ошибке: перед ними убедись, что у тебя есть флешка с Arch и пароль LUKS.

## 1. TRIM через LUKS

**Wiki:** [dm-crypt/Specialties](https://wiki.archlinux.org/title/Dm-crypt/Specialties) · [dm-crypt/System configuration](https://wiki.archlinux.org/title/Dm-crypt/System_configuration) · [Solid state drive](https://wiki.archlinux.org/title/Solid_state_drive)

По умолчанию TRIM через LUKS выключен: так решили разработчики device-mapper, потому что он раскрывает, какие блоки свободны, и этого может хватить, чтобы определить файловую систему. Без TRIM SSD медленнее и быстрее изнашивается. Если утечка тебя не беспокоит, TRIM включают.

| | За | Против |
|---|---|---|
| **Включить** | скорость и ресурс SSD; снимает проблему устаревшего заголовка LUKS | раскрывается карта занятых блоков |
| **Не включать** | карта блоков скрыта | SSD работает хуже; не подходит, если нужна скрытность шифрования |

Для LUKS2 флаг записывается в заголовок и работает во всех сценариях:

```
sudo cryptsetup --allow-discards --persistent refresh cryptlvm
sudo cryptsetup luksDump /dev/nvme0n1p2 | grep Flags      # должно быть allow-discards
```

Альтернатива для `sd-encrypt`: добавить `rd.luks.options=discard` в `/etc/kernel/cmdline` и пересобрать UKI (`sudo mkinitcpio -P`).

Одного разрешения мало: освобождённые блоки надо сообщать диску. Для ext4 и XFS это `fstrim.timer` (включён в [главе 05](05-first-boot.md)), для Btrfs `discard=async` (появляется в параметрах монтирования только после разрешения TRIM через LUKS и перезагрузки). Проверка: `sudo fstrim -av`.

У меня TRIM через LUKS не включён: в списке служб нет `fstrim.timer`, а в параметрах монтирования корня нет `discard=async`.

## 2. Secure Boot (sbctl)

**Wiki:** [Unified Extensible Firmware Interface/Secure Boot](https://wiki.archlinux.org/title/Unified_Extensible_Firmware_Interface/Secure_Boot)

Secure Boot проверяет подписи загрузчика и ядра. Он нужен, если важно, чтобы никто не подменил загрузочные файлы (а значит, и для честной TPM2-разблокировки). Он удобнее всего с UKI: подписывается один файл.

| Загрузчик | Сложность |
|---|---|
| **systemd-boot** | проще всего: подписывается сам загрузчик и UKI |
| **GRUB** | отдельная схема, см. вики GRUB |
| **Limine** | дополнительно нужно закрепить хеш конфига (`limine enroll-config`), см. документацию Limine; в гайде не описано |
| **EFISTUB** | подписывается только UKI |

Порядок (ниже для UKI и systemd-boot или EFISTUB):

1. Поставь `sbctl` и переведи прошивку в **Setup Mode** (в настройках прошивки сотри или сбрось ключи Secure Boot; способ зависит от производителя, см. `man sbctl`).
2. Загрузись в Linux и проверь: `sudo sbctl status` (ожидается Secure Boot выключен, Setup Mode включён).
3. Создай и загрузи свои ключи:

   ```
   sudo sbctl create-keys
   sudo sbctl enroll-keys -m
   ```

   `-m` оставляет ключи Microsoft: без них на части машин не стартуют прошивки устройств (option ROM) и можно получить неработающее устройство. Если рядом Windows, ключи Microsoft нужны всегда. На некоторых ноутбуках добавляют ещё `-f`, чтобы сохранить ключи производителя.
4. Подпиши загрузочные файлы (`-s` запоминает файл, чтобы пересоздавать подпись автоматически):

   ```
   sudo sbctl verify                                        # что не подписано
   sudo sbctl sign -s /efi/EFI/Linux/arch-linux.efi
   sudo sbctl sign -s /efi/EFI/Linux/arch-linux-lts.efi     # если есть запасное ядро
   sudo sbctl sign -s /efi/EFI/systemd/systemd-bootx64.efi  # systemd-boot
   sudo sbctl sign -s /efi/EFI/BOOT/BOOTX64.EFI
   ```

5. Перезагрузись, включи Secure Boot в прошивке и проверь `sudo sbctl status`.

`sbctl` ставит pacman-хук, который заново подписывает запомненные файлы при обновлении ядра и загрузчика. Служба `systemd-boot-update` обновляет загрузчик только после перезагрузки, и хук этого не видит: подписывай файл в `/usr/lib/systemd/boot/efi/` по вики.

> Поставь пароль на настройки прошивки: иначе любой с физическим доступом выключит Secure Boot. Удаление ключей Microsoft может сделать устройства неработающими.

## 3. TPM2-разблокировка LUKS

**Wiki:** [systemd-cryptenroll](https://wiki.archlinux.org/title/Systemd-cryptenroll) · [Trusted Platform Module](https://wiki.archlinux.org/title/Trusted_Platform_Module)

TPM2 хранит ключ и отдаёт его, только если загрузочная цепочка не изменилась. Тогда пароль LUKS при штатной загрузке не нужен (но остаётся запасным).

| | За | Против |
|---|---|---|
| **TPM2** | не вводишь пароль при каждой загрузке | при ошибке настройки или смене прошивки можно потерять доступ без пароля; защищает слабее, чем пароль, если не добавить PIN |
| **Только пароль** (★) | просто и надёжно | вводишь пароль |

Условия:

- Secure Boot включён и в пользовательском режиме (шаг 2). Иначе привязка к PCR 7 разрешит подменённой загрузке получить ключ.
- Привязка к PCR 7 ломается, если меняются сертификаты прошивки: например при обновлении через `fwupd` или смене ключей Secure Boot. Держи пароль LUKS под рукой.

```
sudo systemd-cryptenroll /dev/nvme0n1p2 --tpm2-device=auto --tpm2-pcrs=7
sudo cryptsetup luksDump /dev/nvme0n1p2        # в списке токенов должен появиться systemd-tpm2
```

Для надёжности добавь PIN: `--tpm2-with-pin=yes` (используй уникальный PIN: он запрашивается до проверки измерений). Вики упоминает привязку к `7+11` (PCR 11 связан с UKI); такая привязка жёстче, и после обновления образа её, вероятно, придётся регистрировать заново.

Чтобы initramfs использовал TPM2, добавь в `/etc/kernel/cmdline`:

```
rd.luks.options=tpm2-device=auto
```

и пересобери образ: `sudo mkinitcpio -P`. Нужен пакет `tpm2-tss`. Эту часть я не проверял на живой системе: если разблокировка не срабатывает, сверься с вики dm-crypt/System configuration. Перерегистрация: `systemd-cryptenroll /dev/nvme0n1p2 --wipe-slot=tpm2 --tpm2-device=auto --tpm2-pcrs=7`.

## 4. AUR

**Wiki:** [AUR helpers](https://wiki.archlinux.org/title/AUR_helpers) · [Arch User Repository](https://wiki.archlinux.org/title/Arch_User_Repository)

AUR — пакеты, собранные сообществом. Их ставит не pacman из официальных репозиториев, а сборка по `PKGBUILD`, написанному неизвестным человеком: **читай `PKGBUILD` перед сборкой**.

| Вариант | За | Против |
|---|---|---|
| **Вручную** (`git clone`, `makepkg -si`) | видно каждый шаг, ничего лишнего | нет автоматических обновлений |
| **paru** | удобно, показывает PKGBUILD для просмотра | собирается из Rust (есть `paru-bin`) |
| **yay** | распространён, проще | меньше возможностей просмотра |

```
sudo pacman -S --needed base-devel git
git clone https://aur.archlinux.org/paru-bin.git
cd paru-bin
less PKGBUILD
makepkg -si
```

Дальше: `paru -S <пакет>` и `paru -Syu` (обновляет и официальные пакеты, и AUR). Бинарные пакеты (`…-bin`) не собираются из исходников: это быстрее, но доверяешь автору.

У меня из AUR только браузер `zen-browser-bin`; `deploy.sh` его не ставит, потому что берёт пакеты из официальных репозиториев. Поставь вручную как выше, затем сделай браузером по умолчанию: `xdg-settings set default-web-browser zen.desktop`.

## 5. Обслуживание

### Btrfs

**Wiki:** [Btrfs](https://wiki.archlinux.org/title/Btrfs) · [Snapper](https://wiki.archlinux.org/title/Snapper)

```
sudo systemctl enable --now btrfs-scrub@-.timer       # раз в месяц проверка контрольных сумм корня
sudo btrfs filesystem usage /
```

Сколько снимков хранить, задают лимиты в `/etc/snapper/configs/root`; мои значения в [главе 05](05-first-boot.md#2-сеть-и-службы).

> **Откат снимка и UKI.** При откате `@` ядро и модули возвращаются к старой версии, а UKI на ESP остаётся новым, и версии расходятся. После отката загрузись с флешки и пересобери образ: `mkinitcpio -P` из chroot (запасное ядро не поможет, оно откатывается вместе с корнем; см. [приложение A](A-recovery.md)).

### Снимки не бэкап

Снимки лежат на том же диске: если он умрёт или будет украден, пропадут и они. Для настоящей копии нужна отдельная: внешний диск или другая машина. Инструменты: ★ `restic` (у меня; шифрованные копии с дедупликацией), `borg` (похоже на restic), `btrbk` (отправка снимков Btrfs на другой диск). Сравнение: [Synchronization and backup programs](https://wiki.archlinux.org/title/Synchronization_and_backup_programs).

### Зеркала и прошивки (по желанию, у меня не включено)

```
sudo systemctl enable --now reflector.timer          # зеркала по расписанию, настройки в /etc/xdg/reflector/reflector.conf
sudo pacman -S --needed fwupd
sudo fwupdmgr refresh && sudo fwupdmgr get-updates
```

Прошивки обновляются через `fwupd`: с включённым TPM2 (шаг 3) это может изменить PCR 7, поэтому до обновления убедись, что помнишь пароль LUKS.

Дальше: графика, [08 · Путь zen](08-zen.md).

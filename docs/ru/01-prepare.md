# 01 · Подготовка

Образ, флешка, live-среда, сеть и переменные установки. Выбор стека сделан в [главе 00](00-stack.md). Ссылки **Wiki** ведут в ArchWiki: это первоисточник, гайд его не заменяет.

> Все команды выполняются от root в live-среде, пока не сказано иное. **Диск будет стёрт.** Если на нём есть другая ОС, не трогай чужие разделы и ESP (глава 02, «Рядом с другой ОС»).

## 1. Образ и проверка

**Wiki:** [Installation guide: Acquire an installation image](https://wiki.archlinux.org/title/Installation_guide#Acquire_an_installation_image)

Образ берётся только с archlinux.org/download: через magnet-ссылку (торрент проверяет части сам) или с зеркала. Файл подписи `.sig` бери **с официальной страницы**, не с произвольного зеркала.

```
gpg --verify archlinux-YYYY.MM.DD-x86_64.iso.sig archlinux-YYYY.MM.DD-x86_64.iso
sha256sum archlinux-YYYY.MM.DD-x86_64.iso
b2sum archlinux-YYYY.MM.DD-x86_64.iso
```

Ожидается `Good signature`, а отпечаток ключа должен совпасть с опубликованным на странице загрузки. Предупреждение «ключ не доверенный» само по себе не означает подделку, но отпечаток сверить нужно. Если ключа нет, его получают по WKD (команда есть на странице загрузки).

> Не продолжай, если подпись не проверяется, отпечаток другой или сумма не совпадает: удали файлы и скачай заново.

## 2. Запись на флешку

**Wiki:** [USB flash installation medium](https://wiki.archlinux.org/title/USB_flash_installation_medium)

Запись идёт на **весь диск флешки**, не на раздел, и стирает всё на ней. Образ Arch это готовый образ диска: форматировать флешку заранее не нужно.

| Вариант | Когда |
|---|---|
| ★ **`dd` на Linux** | проверяемый, ничего лишнего |
| **Windows**: Rufus в режиме «DD-образ» | нет Linux под рукой |
| **Ventoy** | несколько ISO на одной флешке |

```
lsblk -o NAME,PATH,SIZE,MODEL,TRAN,TYPE,FSTYPE,MOUNTPOINTS     # флешка: TRAN=usb, размер, модель
sudo umount /dev/sdX1                                           # размонтируй все её разделы
```

Сначала только показываем, что собираемся сделать, и перепроверяем:

```
ISO="$HOME/Downloads/archlinux-YYYY.MM.DD-x86_64.iso"
USB=/dev/sdX
printf 'ISO: %s\nUSB: %s\n' "$ISO" "$USB"
ls -lh "$ISO"
lsblk -o NAME,PATH,SIZE,MODEL,TRAN,TYPE,MOUNTPOINTS "$USB"
```

`/dev/sdX1` это раздел, использовать нельзя; буквальный `X` тоже. Только потом:

```
sudo dd if="$ISO" of="$USB" bs=4M status=progress oflag=sync
sync
sudo eject "$USB"
```

Ошибка в `of=` стирает другой накопитель без вопросов. Не вынимай флешку до возврата приглашения.

## 3. Загрузка live-среды

**Wiki:** [Boot the live environment](https://wiki.archlinux.org/title/Installation_guide#Boot_the_live_environment) · [Verify the boot mode](https://wiki.archlinux.org/title/Installation_guide#Verify_the_boot_mode)

Открой меню загрузки прошивки и выбери флешку с пометкой UEFI. Официальный ISO не грузится с включённым Secure Boot: на время установки отключи его (ключи прошивки не удаляй). В меню выбери *Arch Linux install medium*: откроется root-оболочка, устанавливаемой системы ещё нет.

Гайд описывает **только UEFI**.

```
cat /sys/firmware/efi/fw_platform_size     # 64 = UEFI x64; файла нет = загрузились в BIOS, перезагрузись в UEFI
loadkeys us                                # раскладка (список: localectl list-keymaps)
setfont ter-v20n                           # крупнее, если экран HiDPI
timedatectl set-ntp true
lsblk -o NAME,PATH,SIZE,MODEL,TRAN,TYPE,FSTYPE,MOUNTPOINTS
```

Запиши точную модель целевого накопителя. Если диска не видно, не размечай «похожий»: проверь режим контроллера (AHCI/RAID) в прошивке.

## 4. Сеть и зеркала

**Wiki:** [Connect to the internet](https://wiki.archlinux.org/title/Installation_guide#Connect_to_the_internet) · [iwd](https://wiki.archlinux.org/title/Iwd) · [Mirrors](https://wiki.archlinux.org/title/Mirrors) · [Reflector](https://wiki.archlinux.org/title/Reflector)

| Вариант | Как |
|---|---|
| **Ethernet** | обычно поднимается сам |
| ★ **Wi-Fi через `iwctl`** | ниже |
| **Телефон по USB** | USB-модем в телефоне даёт сетевой интерфейс |

```
iwctl
[iwd]# device list
[iwd]# station wlan0 scan
[iwd]# station wlan0 get-networks
[iwd]# station wlan0 connect "<SSID>"
[iwd]# exit
```

```
ip link
ping -c3 archlinux.org
```

Сеть live-среды не переносится в установленную систему: её настраивают отдельно (глава 05). Если сети нужны прокси, captive portal или статический адрес, настрой это сначала.

**Зеркала.** Пакеты берутся из `/etc/pacman.d/mirrorlist`, список копируется в новую систему. Обычно хватает того, что в образе. Если качает медленно:

```
reflector --country <СТРАНА> --protocol https --latest 20 --sort rate --save /etc/pacman.d/mirrorlist
```

## 5. Значения в командах

Дальше в гайде команды написаны с **примерами значений**: диск `/dev/nvme0n1` (разделы `/dev/nvme0n1p1` и `/dev/nvme0n1p2`), машина `archbox`, пользователь `user`, пояс `Europe/Moscow`. Подставляй свои и вводи команды руками: так видно, что именно происходит с диском. Всё, что надо взять из системы (UUID и подобное), записано в угловых скобках: `<UUID-LUKS>`.

| Что | Как узнать | Заметка |
|---|---|---|
| Диск | `lsblk` | `/dev/sda` (разделы `sda1`, `sda2`) или `/dev/nvme0n1` (разделы `nvme0n1p1`, `nvme0n1p2`: у NVMe и MMC добавляется `p`) |
| Пояс | `timedatectl list-timezones` | например `Europe/Moscow` |
| Микрокод | процессор AMD или Intel | пакет `amd-ucode` или `intel-ucode` |
| Размер ESP | — | `1G` хватает для двух UKI и загрузчика |
| Размер swap | — | не меньше ОЗУ для гибернации; нужен только если swap отдельным томом |
| Редактор | — | в примерах `nvim`; если выбрал другой, пиши его (`nano`, `vim`) |

Дальше: [02 · Разметка](02-partition.md).

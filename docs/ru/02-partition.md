# 02 · Разметка и файловые системы

Диск собирается слоями снизу вверх: **раздел → (LUKS) → (LVM) → файловая система**. Скобки означают, что слой необязательный. Выбор и аргументы за и против: [глава 00](00-stack.md). Примеры значений: [01 · Подготовка, шаг 5](01-prepare.md#5-значения-в-командах).

Главная линия в блоках ★: LUKS → LVM → Btrfs. Для другого выбора пропусти ненужные слои и подставь устройство корня из таблицы.

| Схема | Устройство корня (на нём создаётся файловая система) |
|---|---|
| LUKS + LVM (★) или LVM без шифрования | `/dev/vg0/root` |
| Только LUKS | `/dev/mapper/cryptlvm` |
| Ничего (без шифрования и LVM) | `/dev/nvme0n1p2` |

Эту таблицу держи перед глазами: от неё зависят шаги 5 и 6.

## 1. Осмотр диска

**Wiki:** [dm-crypt/Drive preparation](https://wiki.archlinux.org/title/Dm-crypt/Drive_preparation) · [SSD memory cell clearing](https://wiki.archlinux.org/title/Solid_state_drive/Memory_cell_clearing)

```
lsblk -o NAME,SIZE,MODEL,TYPE,FSTYPE,MOUNTPOINTS /dev/nvme0n1
fdisk -l /dev/nvme0n1
```

Убедись по модели и размеру, что это именно тот диск.

| Вариант | Что делать |
|---|---|
| ★ **Чистая установка на весь диск** | таблица создаётся заново, старое пропадает |
| **Рядом с другой ОС** | не пересоздавай таблицу и не форматируй существующий ESP: смонтируй его в `/efi`, а под систему добавь раздел в свободном месте. Резервная копия обязательна. Шаги `wipefs`, `g` и `mkfs.fat` ниже пропусти |

Только для чистой установки на весь диск: убери старые подписи файловых систем, чтобы они не конфликтовали.

```
wipefs -a /dev/nvme0n1
```

Для LUKS можно ещё перезаписать диск случайными данными. Это медленно и нужно только если важно скрыть, сколько места занято; см. wiki «Drive preparation».

## 2. Разметка (fdisk)

**Wiki:** [fdisk](https://wiki.archlinux.org/title/Fdisk) · [Partition the disks](https://wiki.archlinux.org/title/Installation_guide#Partition_the_disks) · [EFI system partition](https://wiki.archlinux.org/title/EFI_system_partition)

GPT и два раздела: **ESP** и один раздел под всё остальное. В нём, смотря по выбору, будет LUKS, LVM или сразу файловая система. Остальное делится уже внутри (LVM, подтома), поэтому ничего больше на диске не нужно. Swap отдельным разделом не делаем: при LVM это том, при других схемах swap-файл или zram (глава 05).

```
fdisk /dev/nvme0n1
```

| В fdisk | Что делает |
|---|---|
| `g` | новая GPT (на диске с другой ОС этот шаг пропусти) |
| `n`, Enter, Enter, `+1G` | раздел 1 (ESP) |
| `t`, `uefi` | тип «EFI System». Номер раздела fdisk не спросит: он пока единственный |
| `n`, Enter, Enter, Enter | раздел 2 на остаток диска |
| `t`, `2`, `L`, выбери *Linux LUKS* | необязательно, при шифровании: подпись для порядка. По умолчанию *Linux filesystem* тоже работает |
| `t`, `2`, `lvm` | необязательно, если LVM без шифрования: тип «Linux LVM» |
| `p` | проверь таблицу |
| `w` | записать. До `w` диск не тронут (`q` выйти без записи) |

То же без диалога (чистая установка):

```
fdisk /dev/nvme0n1 <<EOF
g
n
1

+1G
t
uefi
n
2


w
EOF
lsblk -f /dev/nvme0n1
mkfs.fat -F 32 -n ESP /dev/nvme0n1p1
```

Размер ESP: 1 GiB хватает для двух UKI (каждый 100–200 МиБ) и загрузчика. Для systemd-boot с классическими ядрами нужно больше (ядра лежат на ESP), см. [главу 00](00-stack.md#ограничения-сочетаний).

## 3. Слой LUKS (необязательно)

**Wiki:** [dm-crypt](https://wiki.archlinux.org/title/Dm-crypt) · [Encrypting an entire system](https://wiki.archlinux.org/title/Dm-crypt/Encrypting_an_entire_system)

Решение принято в [главе 00](00-stack.md#2-шифрование). Без шифрования пропусти шаг.

```
cryptsetup luksFormat --type luks2 /dev/nvme0n1p2
cryptsetup open /dev/nvme0n1p2 cryptlvm
```

Имя `cryptlvm` одно во всех схемах: оно попадёт в параметры ядра. Пароль запомни: без него данные не прочитать. ESP остаётся незашифрованным, прошивка должна его читать.

## 4. Слой LVM (необязательно)

**Wiki:** [LVM](https://wiki.archlinux.org/title/LVM)

Решение: [глава 00](00-stack.md#lvm). Первая команда берёт то, что получилось на прошлом шаге: `/dev/mapper/cryptlvm` при LUKS, иначе раздел `/dev/nvme0n1p2`.

```
pvcreate /dev/mapper/cryptlvm
vgcreate vg0 /dev/mapper/cryptlvm
lvcreate -L 32G -n swap vg0           # swap-том для гибернации; размер не меньше ОЗУ (у меня 32G при 16 ГБ ОЗУ)
lvcreate -l 100%FREE -n root vg0
mkswap -L SWAP /dev/vg0/swap
```

LVM без swap-тома: пропусти строки `lvcreate … swap` и `mkswap`. Если для swap выбран файл, он создаётся уже в установленной системе (глава 05).

## 5. Файловая система корня

**Wiki:** [File systems](https://wiki.archlinux.org/title/File_systems) · [Btrfs](https://wiki.archlinux.org/title/Btrfs)

Выбери одну. Устройство корня — из таблицы вверху главы. Сравнение: [глава 00](00-stack.md#файловая-система-корня).

### ★ Btrfs

```
mkfs.btrfs -L ROOT /dev/vg0/root
mount /dev/vg0/root /mnt
for s in @ @home @var_log @var_cache; do btrfs subvolume create /mnt/$s; done
umount /mnt
```

Подтома: `@` (корень), `@home` (личные данные: откат системы их не трогает), `@var_log` и `@var_cache` (логи и кэш не попадают в снимки). Пятый, `@snapshots`, появится в главе 03 вместе с настройкой Snapper.

### ext4

```
mkfs.ext4 -L ROOT /dev/vg0/root
```

### XFS

```
mkfs.xfs -L ROOT /dev/vg0/root
```

XFS нельзя уменьшить, снимков у неё нет.

## 6. Монтирование

**Wiki:** [Mount the file systems](https://wiki.archlinux.org/title/Installation_guide#Mount_the_file_systems) · [Btrfs: mounting subvolumes](https://wiki.archlinux.org/title/Btrfs#Mounting_subvolumes)

**★ Btrfs:**

```
mount -o subvol=@,compress=zstd:3 /dev/vg0/root /mnt
mount --mkdir -o subvol=@home,compress=zstd:3      /dev/vg0/root /mnt/home
mount --mkdir -o subvol=@var_log,compress=zstd:3   /dev/vg0/root /mnt/var/log
mount --mkdir -o subvol=@var_cache,compress=zstd:3 /dev/vg0/root /mnt/var/cache
```

`compress=zstd:3` экономит место почти бесплатно для процессора.

**ext4 или XFS:**

```
mount /dev/vg0/root /mnt
```

**Общее для всех схем:** ESP и swap.

```
mount --mkdir -o fmask=0077,dmask=0077 /dev/nvme0n1p1 /mnt/efi
swapon /dev/vg0/swap                 # если создавал swap-том
```

ESP монтируется с `fmask/dmask 0077`: обычные пользователи не читают загрузочный раздел. Если выбраны systemd-boot и классические ядра, смонтируй ESP в `/mnt/boot`, а не в `/mnt/efi` (глава 04).

Проверка:

```
lsblk -f /dev/nvme0n1
findmnt -R /mnt
```

Дальше: [03 · Система](03-system.md).

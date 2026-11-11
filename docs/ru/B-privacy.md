# B · Что нельзя публиковать

Перед публикацией своих конфигов (репозиторий, форум, чат) проверь, что в них нет личного.

- Пароли (LUKS, пользователь, root), ключи, токены, почта.
- UUID разделов и томов (`blkid`, `luksUUID`), готовые `fstab` и `cmdline`.
- Имя машины и пользователя, если они выдают личность.
- Данные Wi-Fi и `/etc/NetworkManager/system-connections`.
- Заголовок LUKS и его копии.
- Резервные копии `backup-*`, истории bash, zsh и fish.

Быстрая проверка на UUID:

```
grep -rE '[0-9a-f]{8}-[0-9a-f]{4}-' .
```

Профиль машины в репозитории zen (`hosts/<имя>/`) содержит UUID: держи его в приватной копии или добавь в `.gitignore`.

## Источники

- ArchWiki: [Installation guide](https://wiki.archlinux.org/title/Installation_guide), [dm-crypt](https://wiki.archlinux.org/title/Dm-crypt), [LVM](https://wiki.archlinux.org/title/LVM), [Btrfs](https://wiki.archlinux.org/title/Btrfs), [Snapper](https://wiki.archlinux.org/title/Snapper)
- [UKI](https://wiki.archlinux.org/title/Unified_kernel_image), [mkinitcpio](https://wiki.archlinux.org/title/Mkinitcpio), [Limine](https://wiki.archlinux.org/title/Limine), [systemd-boot](https://wiki.archlinux.org/title/Systemd-boot), [GRUB](https://wiki.archlinux.org/title/GRUB)
- [Fish](https://wiki.archlinux.org/title/Fish), [Zsh](https://wiki.archlinux.org/title/Zsh), [nftables](https://wiki.archlinux.org/title/Nftables), [Ly](https://wiki.archlinux.org/title/Ly), [Zram](https://wiki.archlinux.org/title/Zram), [Suspend and hibernate](https://wiki.archlinux.org/title/Power_management/Suspend_and_hibernate)

Команды сверяй с ArchWiki: пакеты, хуки и имена служб иногда меняются.

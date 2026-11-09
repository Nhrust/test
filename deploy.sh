#!/bin/sh
# deploy.sh — apply the zen configuration to an installed Arch system.
#
#   ./deploy.sh [--dry-run] [--host NAME] [--no-packages]
#
# Order: packages → home files → /etc and /usr/local files → files that older
# versions installed (lists/removed.txt) → translations → zen apply (colours,
# console and boot menu) → cursor → services → initramfs/UKI if needed →
# gtklock module.
# Common files come first, then hosts/NAME overrides them. Every file that is
# replaced is copied to ~/.local/state/zen/backup-<date>/ first (or $ZEN_BACKUP),
# and new files are listed in created.txt there.
set -eu

ROOT=$(cd "$(dirname "$0")" && pwd)
DRY=
HOST=$(cat /etc/hostname 2>/dev/null || hostname)
PACKAGES=1
while [ $# -gt 0 ]; do
	case $1 in
		--dry-run) DRY=1 ;;
		--host) HOST=$2; shift ;;
		--no-packages) PACKAGES= ;;
		*) sed -n '2,10p' "$0"; exit 1 ;;
	esac
	shift
done
H="$ROOT/hosts/$HOST"
if [ ! -d "$H" ]; then
	echo "no hosts/$HOST — create it (copy hosts/zen as an example) or pass --host"
	ls "$ROOT/hosts"
	exit 1
fi
BACKUP=${ZEN_BACKUP:-"${XDG_STATE_HOME:-$HOME/.local/state}/zen/backup-$(date +%Y%m%d-%H%M%S)"}
REBUILD=$(mktemp)
LOCALES=$(mktemp)
SSHD=$(mktemp)
RELOAD=$(mktemp)
trap 'rm -f "$REBUILD" "$LOCALES" "$SSHD" "$RELOAD"' EXIT

say() { printf '%s\n' "$*"; }
run() { say "+ $*"; [ -n "$DRY" ] || "$@"; }

lines() { cat "$@" 2>/dev/null | sed 's/#.*//; /^[[:space:]]*$/d'; }

# 1. packages
if [ -n "$PACKAGES" ]; then
	pkgs=$(lines "$ROOT"/packages/*.txt "$H/packages.txt" | sort -u)
	# shellcheck disable=SC2086
	run sudo pacman -S --needed $pkgs
fi

# 2. files
place() {
	src=$1 dst=$2 sudo=$3
	tmp=
	if grep -qE '@(HOME|USER)@' "$src" 2>/dev/null; then
		tmp=$(mktemp)
		sed "s|@HOME@|$HOME|g; s|@USER@|$(id -un)|g" "$src" > "$tmp"
		src=$tmp
	fi
	if $sudo test -e "$dst" && $sudo cmp -s "$src" "$dst"; then
		[ -z "$tmp" ] || rm -f "$tmp"
		return 0
	fi
	case $dst in
		/etc/sudoers)
			if ! sudo visudo -cf "$src" >/dev/null; then
				say "! $dst: syntax check failed, skipped"; return 0
			fi ;;
		/etc/kernel/cmdline|/etc/mkinitcpio.conf|/etc/mkinitcpio.d/*|/etc/vconsole.conf|/etc/udev/rules.d/*)
			echo 1 > "$REBUILD" ;;
		/etc/locale.gen)
			echo 1 > "$LOCALES" ;;
		"$HOME/.config/waybar/"*)
			echo waybar >> "$RELOAD" ;;
		"$HOME/.config/mako/"*)
			echo mako >> "$RELOAD" ;;
	esac
	if $sudo test -e "$dst"; then
		run $sudo mkdir -p "$BACKUP$(dirname "$dst")"
		run $sudo cp -p "$dst" "$BACKUP$dst"
	elif [ -z "$DRY" ]; then
		mkdir -p "$BACKUP"
		printf '%s\n' "$dst" >> "$BACKUP/created.txt"
	fi
	mode=$(stat -c %a "$1")
	[ "$dst" = /etc/sudoers ] && mode=440
	run $sudo install -D -m "$mode" "$src" "$dst"
	[ -z "$tmp" ] || rm -f "$tmp"
	case $dst in
		/etc/ssh/*)
			[ -z "$DRY" ] || return 0
			if sudo sshd -t; then
				echo 1 > "$SSHD"
			else
				say "! $dst: sshd -t failed, change reverted"
				if [ -e "$BACKUP$dst" ]; then sudo cp -p "$BACKUP$dst" "$dst"; else sudo rm -f "$dst"; fi
			fi ;;
	esac
}

tree() {
	base=$1 target=$2 sudo=$3
	[ -d "$base" ] || return 0
	(cd "$base" && find . -type f) | sort | while read -r f; do
		place "$base/${f#./}" "$target/${f#./}" "$sudo"
	done
}

# made by the user first, so sudo-created subfolders never lock it
[ -n "$DRY" ] || mkdir -p "$BACKUP"
tree "$ROOT/home" "$HOME" ""
tree "$H/home" "$HOME" ""
tree "$ROOT/etc" /etc sudo
tree "$H/etc" /etc sudo
tree "$ROOT/usr/local" /usr/local sudo
tree "$H/usr/local" /usr/local sudo
[ ! -s "$LOCALES" ] || run sudo locale-gen

# files earlier versions installed and this one does not
for f in $(lines "$ROOT/lists/removed.txt"); do
	# entries name home files as ~/path
	# shellcheck disable=SC2088
	case $f in "~/"*) f="$HOME/${f#\~/}" ;; esac
	sudo=
	case $f in "$HOME"/*) ;; *) sudo=sudo ;; esac
	$sudo test -e "$f" || continue
	run $sudo mkdir -p "$BACKUP$(dirname "$f")"
	run $sudo mv "$f" "$BACKUP$f"
	run $sudo rmdir -p --ignore-fail-on-non-empty "$(dirname "$f")" 2>/dev/null || true
done

STATE="${XDG_STATE_HOME:-$HOME/.local/state}/zen"
run mkdir -p "$STATE"
[ -n "$DRY" ] || { printf '%s\n' "$ROOT" > "$STATE/repo"; printf '%s\n' "$HOST" > "$STATE/host"; }

# 3. translations, colours, cursor
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
for po in "$ROOT"/po/*.po; do
	lang=$(basename "$po" .po)
	run mkdir -p "$DATA/locale/$lang/LC_MESSAGES"
	run msgfmt -o "$DATA/locale/$lang/LC_MESSAGES/zen.mo" "$po"
done
[ -e "${XDG_CONFIG_HOME:-$HOME/.config}/zen/zen.conf" ] ||
	run cp "${XDG_CONFIG_HOME:-$HOME/.config}/zen/zen.conf.example" "${XDG_CONFIG_HOME:-$HOME/.config}/zen/zen.conf"
run "$HOME/.local/bin/zen" apply

CURSOR=Bibata-Modern-Classic
CURSOR_URL=https://github.com/ful1e5/Bibata_Cursor/releases/download/v2.0.7/$CURSOR.tar.xz
CURSOR_SHA=7d3495864e5bbef02f5e77de760b2905903b63c71495a78ef6306d19a3b556d8
if [ ! -d "$DATA/icons/$CURSOR" ]; then
	t=$(mktemp)
	run curl -fsSL -o "$t" "$CURSOR_URL"
	if [ -z "$DRY" ] && [ "$(sha256sum "$t" | cut -d' ' -f1)" != "$CURSOR_SHA" ]; then
		say "! cursor archive checksum mismatch, skipped"
	else
		run mkdir -p "$DATA/icons"
		run tar -xf "$t" -C "$DATA/icons"
	fi
	rm -f "$t"
fi
run gsettings set org.gnome.desktop.interface cursor-theme "$CURSOR"
if command -v fish >/dev/null; then
	# fish_add_path returns 1 when the path is already there
	run fish -c 'fish_add_path -U ~/.local/bin' || true
fi

# 4. services
enable_units() {
	scope=$1; shift
	for unit in $(lines "$@"); do
		if [ "$scope" = user ]; then
			check="systemctl --user cat $unit" act="systemctl --user enable $unit"
		else
			check="systemctl cat ${unit%%@*}@.service" act="sudo systemctl enable $unit"
			[ "${unit#*@}" = "$unit" ] && check="systemctl cat $unit"
		fi
		if $check >/dev/null 2>&1; then
			# shellcheck disable=SC2086
			run $act
		else
			say "- $unit: not installed, skipped"
		fi
	done
}
run systemctl --user daemon-reload
run sudo systemctl daemon-reload
enable_units user "$ROOT/lists/user-services.txt" "$H/user-services.txt"
enable_units system "$ROOT/lists/system-services.txt" "$H/system-services.txt"
if grep -qx 'ly@tty2.service' "$ROOT/lists/system-services.txt"; then
	run sudo systemctl disable getty@tty2.service
fi

# 5. boot image and lock screen module
[ ! -s "$REBUILD" ] || run sudo mkinitcpio -P
# running programs pick up their new configs
! grep -qx waybar "$RELOAD" || run pkill -USR2 -x waybar || true
! grep -qx mako "$RELOAD" || run makoctl reload || true
[ ! -s "$SSHD" ] || run sudo systemctl try-reload-or-restart sshd.service
run "$HOME/.local/bin/zen" gtklock || say "! gtklock module not built; run: zen gtklock"

rmdir "$BACKUP" 2>/dev/null || true
[ ! -d "$BACKUP" ] || say "replaced files: $BACKUP"
say "done; log out and back in to start the session"

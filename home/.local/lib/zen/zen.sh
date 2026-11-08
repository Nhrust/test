# Sourced by the zen shell scripts: locale from zen.conf and gettext domain.
ZEN_CONF="${XDG_CONFIG_HOME:-$HOME/.config}/zen/zen.conf"
zen_locale=$(sed -n '/^\[general\]/,/^\[/s/^locale *= *//p' "$ZEN_CONF" 2>/dev/null | head -n 1)
if [ -n "$zen_locale" ]; then
	export LC_ALL="$zen_locale" LANGUAGE="${zen_locale%%.*}"
fi
export TEXTDOMAIN=zen TEXTDOMAINDIR="${XDG_DATA_HOME:-$HOME/.local/share}/locale"
command -v gettext >/dev/null || gettext() { printf '%s' "$1"; }

zen_battery() {
	for b in /sys/class/power_supply/*; do
		[ "$(cat "$b/type" 2>/dev/null)" = Battery ] && { echo "$b"; return 0; }
	done
	return 1
}

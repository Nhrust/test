"""Common code for the zen scripts: settings, palette, translations, locale."""
import configparser
import gettext
import locale
import os
import re
import subprocess
import time
from pathlib import Path

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp")
CONFIG = CONFIG_HOME / "zen" / "zen.conf"

PALETTE = {
    "bg": "#0b0b0b",
    "fg": "#dedede",
    "muted": "#bebebe",
    "line": "#555555",
    "accent": "#bdb3fa",
    "critical": "#f3a3bb",
    "error": "#f7a692",
    "info": "#69cee6",
    "success": "#8ed09c",
    "warning": "#ebb077",
    "deep": "#030303",
    "bar": "#000000",
    "inactive": "#2e2e2e",
}

# The 16 terminal colours and 8 dim ones. A name in place of a colour takes
# that role from [palette], so changing the palette changes the terminal too.
TERMINAL = {
    "color0": "bg", "color1": "error", "color2": "success", "color3": "warning",
    "color4": "accent", "color5": "critical", "color6": "info", "color7": "fg",
    "color8": "line", "color9": "#ffd1c0", "color10": "#bfeacd", "color11": "#f8d8b3",
    "color12": "#e1d7ff", "color13": "#ffced8", "color14": "#b2e8fa", "color15": "#ffffff",
    "dim0": "deep", "dim1": "#c57670", "dim2": "#6e9e63", "dim3": "#be7e51",
    "dim4": "#8488cb", "dim5": "#bd7598", "dim6": "#2ca0ac", "dim7": "muted",
}

DEFAULTS = {
    "general": {"locale": ""},
    "weather": {"location": "", "name": "", "contact": ""},
    "palette": PALETTE,
    "terminal": TERMINAL,
}


def settings():
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";",))
    cfg.read_dict(DEFAULTS)
    cfg.read(CONFIG, encoding="utf-8")
    return cfg


def _apply_locale():
    """[general] locale overrides the system locale for the zen scripts only.
    Child processes (Rofi, locale -k) inherit it through the environment."""
    wanted = settings().get("general", "locale").strip()
    if wanted:
        os.environ["LC_ALL"] = wanted
        os.environ["LANGUAGE"] = wanted.split(".")[0]
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass


_apply_locale()
_translation = gettext.translation("zen", localedir=str(DATA_HOME / "locale"), fallback=True)
_ = _translation.gettext
ngettext = _translation.ngettext


def palette():
    """The named roles of [palette]."""
    cfg = settings()
    return {key: cfg.get("palette", key).strip() for key in PALETTE}


def colors():
    """[palette] roles and [terminal] colours together, every value #rrggbb."""
    cfg = settings()
    out = palette()
    for key in TERMINAL:
        value = cfg.get("terminal", key).strip()
        out[key] = out.get(value, value)
    return out


_TOKEN = re.compile(r"\{\{\s*([a-z0-9]+)(?:\|([a-z]+)(?::([0-9a-f]{2}))?)?\s*\}\}")


def render(text, values=None):
    """Fill {{name}} in a template: #rrggbb, {{name|hex}} rrggbb,
    {{name|rgb}} r,g,b, {{name|argb:AA}} #AArrggbb, {{name|rgba:AA}} #rrggbbAA."""
    values = values or colors()

    def sub(m):
        key, fmt, alpha = m.groups()
        if key not in values:
            raise KeyError(f"unknown colour {{{{{key}}}}}")
        h = values[key].lstrip("#").lower()
        if fmt is None:
            return "#" + h
        if fmt == "hex":
            return h
        if fmt == "rgb":
            return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))
        if fmt == "argb":
            return "#" + (alpha or "ff") + h
        if fmt == "rgba":
            return "#" + h + (alpha or "ff")
        raise KeyError(f"unknown format {fmt}")
    return _TOKEN.sub(sub, text)


def run(*cmd, **kwargs):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", "")


def _locale_keyword(category, keyword):
    out = run("locale", "-k", category).stdout
    for line in out.splitlines():
        if line.startswith(keyword + "="):
            return line.split("=", 1)[1].strip('"')
    return None


def first_weekday():
    """0 = Monday … 6 = Sunday, from LC_TIME (first_weekday and week-1stday)."""
    first = _locale_keyword("LC_TIME", "first_weekday")
    base = _locale_keyword("LC_TIME", "week-1stday")
    try:
        first = int(first)
        weekday_of_base = time.strptime(base, "%Y%m%d").tm_wday
    except (TypeError, ValueError):
        return 0
    return (weekday_of_base + first - 1) % 7


def metric():
    """LC_MEASUREMENT: 1 — metric, 2 — US customary."""
    return _locale_keyword("LC_MEASUREMENT", "measurement") != "2"


def twelve_hour():
    fmt = _locale_keyword("LC_TIME", "t_fmt") or ""
    return "%I" in fmt or "%r" in fmt or "%l" in fmt


def clock(when):
    return when.strftime("%I:%M %p").lstrip("0") if twelve_hour() else when.strftime("%H:%M")


def hour(when):
    """Short time for narrow columns: 15:00 or 3 PM."""
    return when.strftime("%I %p").lstrip("0") if twelve_hour() else when.strftime("%H:%M")


def month_name(month, year):
    """Stand-alone month name for a heading (%OB where the locale has it)."""
    stamp = time.struct_time((year, month, 1, 0, 0, 0, 0, 1, -1))
    name = time.strftime("%OB", stamp)
    return name if name and not name.startswith("%") else time.strftime("%B", stamp)


def weekday_names():
    """Short weekday names, Monday first, two characters each for the grid."""
    names = []
    for day in range(7):
        stamp = time.struct_time((2024, 1, 1 + day, 0, 0, 0, day, 1 + day, -1))
        names.append(time.strftime("%a", stamp)[:2])
    return names


def language():
    """Two-letter language code of LC_MESSAGES, e.g. "ru"; "en" for C/POSIX."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            code = value.split(":")[0].split("_")[0].split(".")[0]
            return "en" if code in ("C", "POSIX") else code
    return "en"

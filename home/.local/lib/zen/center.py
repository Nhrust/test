"""zen-center — notifications, calendar and weather in one Rofi menu.

  zen-center          open the menu (a second call closes it)
  zen-center dnd      Waybar module: unread count; a crossed bell while do-not-disturb is on,
                      a bell when notifications went to the history unseen
  zen-center seen ID  keep a notification out of the list and the count (mako runs it on a click)
  zen-center dnd toggle   switch do-not-disturb on or off
  zen-center clear    remove all notifications
  zen-center fetch    download the weather into the cache (at most every 90 s)
"""
import calendar
import datetime as dt
import functools
import html
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import zen
from zen import _, run


def N_(text):
    return text

SELF = os.path.realpath(sys.argv[0])
THEME = zen.CONFIG_HOME / "rofi/center.rasi"
CACHE = zen.RUNTIME / "zen-center-weather.json"
ERROR = zen.RUNTIME / "zen-center-weather.err"
HIDDEN = zen.RUNTIME / "zen-center-hidden.json"
READ = zen.RUNTIME / "zen-center-read.json"
CACHE_TTL = 15 * 60
DND = "do-not-disturb"
DND_SIGNAL = 11
COLS = 26
CAL_W = 23
WRAP = 27

COLOR = zen.palette()
ACCENT, MUTED, LINE, CRITICAL = COLOR["accent"], COLOR["muted"], COLOR["line"], COLOR["critical"]
METRIC = zen.metric()

BELL = "\U000F009A"
BELL_OFF = "\U000F009B"
WIND, DROP, SUNRISE, SUNSET = "\U000F059D", "\U000F058E", "\U000F059C", "\U000F059B"
SUN, MOON, PARTLY, PARTLY_NIGHT = "\U000F0599", "\U000F0594", "\U000F0595", "\U000F0F31"
CLOUD, FOG, RAIN, POUR = "\U000F0590", "\U000F0591", "\U000F0597", "\U000F0596"
SNOW, SLEET, THUNDER = "\U000F0598", "\U000F067F", "\U000F0593"

WWO_CODES = {
    PARTLY: {116}, CLOUD: {119, 122}, FOG: {143, 248, 260},
    RAIN: {176, 263, 266, 293, 296, 353}, POUR: {299, 302, 305, 308, 356, 359},
    SNOW: {179, 227, 230, 323, 326, 329, 332, 335, 338, 368, 371},
    SLEET: {182, 185, 281, 284, 311, 314, 317, 320, 350, 362, 365, 374, 377},
    THUNDER: {200, 386, 389, 392, 395},
}

# WorldWeatherOnline condition codes (wttr.in) and their descriptions; the
# text is translated with gettext like the rest of the interface.
CONDITIONS = {
    113: N_("clear"), 116: N_("partly cloudy"), 119: N_("cloudy"), 122: N_("overcast"),
    143: N_("mist"), 176: N_("patchy rain"), 179: N_("patchy snow"), 182: N_("patchy sleet"),
    185: N_("patchy freezing drizzle"), 200: N_("thundery outbreaks"), 227: N_("blowing snow"),
    230: N_("blizzard"), 248: N_("fog"), 260: N_("freezing fog"), 263: N_("patchy light drizzle"),
    266: N_("light drizzle"), 281: N_("freezing drizzle"), 284: N_("heavy freezing drizzle"),
    293: N_("patchy light rain"), 296: N_("light rain"), 299: N_("moderate rain at times"),
    302: N_("moderate rain"), 305: N_("heavy rain at times"), 308: N_("heavy rain"),
    311: N_("light freezing rain"), 314: N_("heavy freezing rain"), 317: N_("light sleet"),
    320: N_("heavy sleet"), 323: N_("patchy light snow"), 326: N_("light snow"),
    329: N_("patchy moderate snow"), 332: N_("moderate snow"), 335: N_("patchy heavy snow"),
    338: N_("heavy snow"), 350: N_("ice pellets"), 353: N_("light rain shower"),
    356: N_("heavy rain shower"), 359: N_("torrential rain shower"), 362: N_("light sleet showers"),
    365: N_("heavy sleet showers"), 368: N_("light snow showers"), 371: N_("heavy snow showers"),
    374: N_("light ice pellet showers"), 377: N_("heavy ice pellet showers"),
    386: N_("light rain with thunder"), 389: N_("heavy rain with thunder"),
    392: N_("light snow with thunder"), 395: N_("heavy snow with thunder"),
}

INIT, SELECT, DELETE, WIPE, ESC, LEFT, RIGHT, TAB, PREV_M, NEXT_M = 0, 1, 3, 11, 12, 13, 14, 15, 17, 18


def option(key, value):
    sys.stdout.write(f"\0{key}\x1f{value}\n")


def refresh_bar():
    run("pkill", f"-RTMIN+{DND_SIGNAL}", "-x", "waybar")


# weather

def weather():
    try:
        cached = json.loads(CACHE.read_text())
    except (OSError, ValueError):
        cached = None
    if cached and "current_condition" not in cached.get("data", {}):
        cached = None
    ttl = CACHE_TTL if cached and cached.get("met") else 300
    if not cached or time.time() - cached.get("fetched", 0) >= ttl:
        subprocess.Popen([sys.executable, SELF, "fetch"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    return cached


def get_json(url, headers, wait):
    import gzip
    import urllib.request
    req = urllib.request.Request(url, headers={**headers, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=wait) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return json.loads(raw)


def place():
    """Configured location, or empty to let wttr.in locate by IP address."""
    return zen.settings().get("weather", "location").strip()


def agent():
    contact = zen.settings().get("weather", "contact").strip()
    return f"zen {contact}".strip()


def coordinates(data):
    area = (data.get("nearest_area") or [{}])[0]
    try:
        return round(float(area["latitude"]), 2), round(float(area["longitude"]), 2)
    except (KeyError, TypeError, ValueError):
        return None


def fetch():
    lock = zen.RUNTIME / "zen-center-fetch.lock"
    try:
        if time.time() - lock.stat().st_mtime < 90:
            return 0
    except OSError:
        pass
    lock.touch()
    errors = []
    try:
        data = met = None
        from urllib.parse import quote
        where = quote(place())
        try:
            data = get_json(f"https://wttr.in/{where}?format=j2",
                            {"User-Agent": "curl"}, 30)
            data = data.get("data", data)
            if not data.get("current_condition"):
                data = None
                errors.append("wttr.in: " + _("empty response"))
        except (OSError, ValueError) as e:
            errors.append(f"wttr.in: {e}")
        point = coordinates(data or {})
        if point:
            try:
                met = get_json("https://api.met.no/weatherapi/locationforecast/2.0/compact"
                               f"?lat={point[0]}&lon={point[1]}", {"User-Agent": agent()}, 20)
                if not met.get("properties", {}).get("timeseries"):
                    met = None
                    errors.append("met.no: " + _("empty response"))
            except (OSError, ValueError) as e:
                errors.append(f"met.no: {e}")
        if errors:
            ERROR.write_text("; ".join(errors))
            print("zen-center: " + "; ".join(errors), file=sys.stderr)
        else:
            ERROR.unlink(missing_ok=True)
        if data:
            CACHE.write_text(json.dumps({"fetched": time.time(), "data": data, "met": met}))
            return 0
        return 1
    finally:
        lock.unlink(missing_ok=True)


def met_icon(symbol):
    night = symbol.endswith("_night")
    base = symbol.split("_")[0]
    if "thunder" in base:
        return THUNDER
    if "sleet" in base:
        return SLEET
    if "snow" in base:
        return SNOW
    if "heavyrain" in base:
        return POUR
    if "rain" in base:
        return RAIN
    if base == "fog":
        return FOG
    if base == "clearsky":
        return MOON if night else SUN
    if base in ("fair", "partlycloudy"):
        return PARTLY_NIGHT if night else PARTLY
    return CLOUD


def met_series(met):
    out = []
    for p in (met or {}).get("properties", {}).get("timeseries", []):
        at = dt.datetime.fromisoformat(p["time"].replace("Z", "+00:00")).astimezone()
        out.append((at.replace(tzinfo=None), p["data"]))
    return out


def wwo_icon(code, night=False):
    code = int(code)
    if code == 113:
        return MOON if night else SUN
    for glyph, codes in WWO_CODES.items():
        if code in codes:
            return PARTLY_NIGHT if glyph == PARTLY and night else glyph
    return CLOUD


def describe(item):
    text = CONDITIONS.get(int(item.get("weatherCode", 0)))
    if text:
        return _(text)
    return (item.get("weatherDesc") or [{}])[0].get("value", "").strip().lower()


def degrees(celsius):
    t = round(float(celsius) * 9 / 5 + 32 if not METRIC else float(celsius))
    return f"+{t}°" if t > 0 else f"−{abs(t)}°" if t < 0 else "0°"


def wwo_time(s):
    """wttr.in gives "07:41 AM" in English regardless of the locale."""
    m = re.match(r"(\d+):(\d+)\s*([AP]M)", s.strip(), re.I)
    if not m:
        return None
    hour = int(m.group(1)) % 12 + (12 if m.group(3).upper() == "PM" else 0)
    return dt.datetime.combine(dt.date.today(), dt.time(hour, int(m.group(2))))


def c(text, color=None, bold=False, dim=False):
    text = html.escape(str(text))
    if bold:
        text = f"<b>{text}</b>"
    attrs = (f' color="{color}"' if color else "") + (' fgalpha="50%"' if dim else "")
    return f"<span{attrs}>{text}</span>" if attrs else text


def vis(markup):
    return len(html.unescape(re.sub(r"<[^>]+>", "", markup)))


def row(left, right=""):
    return left + " " * max(1, COLS - vis(left) - vis(right)) + right


def cells(parts, w=6):
    out = ""
    for p in parts:
        n = vis(p)
        left = (w - n) // 2
        out += " " * left + p + " " * (w - n - left)
    return " " * ((COLS - w * len(parts)) // 2) + out


def place_label(data):
    name = zen.settings().get("weather", "name").strip()
    if name:
        return name
    configured = place()
    if configured and not re.match(r"^[-\d.,\s]+$", configured):
        return configured
    area = (data.get("nearest_area") or [{}])[0] if data else {}
    try:
        return area["areaName"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return _("Weather")


def weather_lines():
    cached = weather()
    data = cached["data"] if cached else None
    label = place_label(data)[:COLS - 12]
    if not data:
        try:
            err = ERROR.read_text().strip()
        except OSError:
            err = ""
        if not err:
            return [row(c(label, bold=True), c(_("loading…"), MUTED))]
        err = err[:COLS * 3]
        return [row(c(label, bold=True), c(_("no weather"), CRITICAL))] + \
               [c(err[i:i + COLS], MUTED) for i in range(0, len(err), COLS)]
    cur = data["current_condition"][0]
    days = data.get("weather") or []
    now = dt.datetime.now()
    sun = days[0]["astronomy"][0] if days else {}
    rise, sets = wwo_time(sun.get("sunrise", "")), wwo_time(sun.get("sunset", ""))
    night = bool(rise and sets) and not (rise.time() <= now.time() <= sets.time())
    what = describe(cur)
    room = COLS - len(label) - 1
    if len(what) > room:
        what = what[:room - 1] + "…"
    if METRIC:
        wind, wind_unit = round(int(cur["windspeedKmph"]) / 3.6), _("m/s")
    else:
        wind, wind_unit = cur["windspeedMiles"], _("mph")
    lines = [
        row(c(label, bold=True), c(what, MUTED)),
        row(c(wwo_icon(cur["weatherCode"], night), ACCENT) + "  " + c(degrees(cur["temp_C"]), bold=True),
            c(_("feels like") + " ", MUTED) + degrees(cur["FeelsLikeC"])),
        row(c(WIND, ACCENT) + f"  {wind}" + c(" " + wind_unit, MUTED),
            c(DROP, ACCENT) + f'  {cur["humidity"]}' + c("%", MUTED)),
    ]
    if rise and sets:
        lines.append(row(c(SUNRISE, ACCENT) + "  " + zen.clock(rise),
                         c(SUNSET, ACCENT) + "  " + zen.clock(sets)))
    lines.append(c("─" * COLS, LINE, dim=True))
    series = met_series(cached.get("met"))
    slots = [(at, d) for at, d in series if at > now and "next_1_hours" in d][:10:3]
    if slots:
        rain = [d["next_1_hours"].get("details", {}).get("precipitation_amount", 0) for _x, d in slots]
        unit = _("mm") if METRIC else _("in")
        rain = rain if METRIC else [round(r / 25.4, 2) for r in rain]
        wet = 0.5 if METRIC else 0.02
        lines += [
            cells([c(zen.hour(at), MUTED) for at, _x in slots]),
            cells([c(met_icon(d["next_1_hours"]["summary"]["symbol_code"]), ACCENT) for _x, d in slots]),
            cells([c(degrees(d["instant"]["details"]["air_temperature"]), bold=True) for _x, d in slots]),
            cells([c(f"{r:g}{unit}", ACCENT) if r >= wet else c(f"{r:g}{unit}", MUTED, dim=True)
                   for r in rain]),
            c("─" * COLS, LINE, dim=True),
        ]
    names = zen.weekday_names()
    for day in days[1:3]:
        date = dt.date.fromisoformat(day["date"])
        noon = next((d for at, d in series if at.date() == date and at.hour >= 12), None)
        glyph = CLOUD
        if noon:
            nxt = noon.get("next_6_hours") or noon.get("next_1_hours")
            if nxt:
                glyph = met_icon(nxt["summary"]["symbol_code"])
        lines.append(row(c(f"{names[date.weekday()]} {date.day:>2}", MUTED, dim=date.weekday() >= 5)
                         + "  " + c(glyph, ACCENT),
                         c(degrees(day["maxtempC"]), bold=True) + c(" / ", LINE)
                         + c(degrees(day["mintempC"]), MUTED)))
    return lines


# calendar

def shown_month(offset):
    today = dt.date.today()
    y, m = divmod(today.year * 12 + today.month - 1 + offset, 12)
    return y, m + 1


def month_lines(offset):
    today = dt.date.today()
    y, m = shown_month(offset)
    first = zen.first_weekday()
    names = zen.weekday_names()
    order = [(first + i) % 7 for i in range(7)]
    head = [c(names[d], MUTED, dim=d >= 5) for d in order]
    lines = [c(_("Wk")[:2].rjust(2), LINE) + " " + " ".join(head)]
    for week in calendar.Calendar(firstweekday=first).monthdatescalendar(y, m):
        number = week[(3 - first) % 7].isocalendar()[1]
        this_week = today in week
        row_cells = [c(f"{number:>2}", ACCENT if this_week else LINE)]
        for d in week:
            if d.month != m:
                row_cells.append("  ")
            elif d == today:
                row_cells.append(c(f"{d.day:>2}", ACCENT, bold=True))
            elif d.weekday() >= 5:
                row_cells.append(c(f"{d.day:>2}", dim=True))
            else:
                row_cells.append(f"{d.day:>2}")
        lines.append(" ".join(row_cells))
    while len(lines) < 7:
        lines.append("")
    return lines


def title(offset, focused):
    y, m = shown_month(offset)
    return c(f"{zen.month_name(m, y)} {y}", ACCENT if focused else None, bold=True)


def side(offset):
    pad = (COLS - CAL_W) // 2
    lines = [" " * pad + line for line in month_lines(offset)]
    lines.append(c("─" * COLS, LINE))
    lines += weather_lines()
    return " ".join(line + " " * max(0, COLS - vis(line)) for line in lines)


# notifications

def dnd_on():
    return DND in run("makoctl", "mode").stdout.split()


def dnd_toggle():
    was = dnd_on()
    res = run("makoctl", "mode", "-r" if was else "-a", DND)
    if res.returncode != 0 or dnd_on() == was:
        modes = [m for m in run("makoctl", "mode").stdout.split() if m != DND] or ["default"]
        res = run("makoctl", "set-mode", *(modes if was else modes + [DND]))
    if dnd_on() == was:
        run("notify-send", "-u", "critical", _("Do not disturb"),
            res.stderr.strip() or _("mako did not switch the mode"))
    refresh_bar()


def mako_json(*args):
    try:
        return json.loads(run("makoctl", *args, "-j").stdout or "[]")
    except ValueError:
        return []


def load_ids(path):
    try:
        return set(json.loads(path.read_text()))
    except (OSError, ValueError):
        return set()


def hide(ids):
    items.cache_clear()
    HIDDEN.write_text(json.dumps(sorted(load_ids(HIDDEN) | set(ids))))


@functools.lru_cache(maxsize=None)
def items():
    """Notifications on screen (a:ID) and in the history (h:ID), read once per run."""
    out = [(f'a:{n["id"]}', n, True) for n in mako_json("list")]
    gone = load_ids(HIDDEN)
    out += [(f'h:{n["id"]}', n, False) for n in mako_json("history") if n["id"] not in gone]
    return out


def find(info):
    return next((n for key, n, _x in items() if key == info), None)


def resolve(info):
    if info[:2] not in ("a:", "h:"):
        return info
    for key, n, _x in items():
        if str(n["id"]) == info[2:]:
            return key
    return info


def unread(history_only=False):
    """Notifications not yet opened here or clicked on screen."""
    done = load_ids(READ)
    return sum(1 for _x, n, live in items() if n["id"] not in done and not (history_only and live))


def mark_read(info):
    present = {n["id"] for _x, n, _y in items()}
    READ.write_text(json.dumps(sorted((load_ids(READ) & present) | {int(info[2:])})))
    refresh_bar()


def common_options(offset, cal, data):
    option("prompt", title(offset, cal))
    option("message", side(offset))
    option("data", data)
    option("no-custom", "true")
    option("use-hot-keys", "true")
    option("markup-rows", "true")
    option("keep-selection", "true")


def show(offset, focus=None, confirm=False, cal=False):
    common_options(offset, cal, f'{offset}:{"c" if cal else "l"}' + (":wipe" if confirm else ""))
    on = dnd_on()
    rows = [(f'{_("Do not disturb")} · ‹ {_("on") if on else _("off")} ›', "dnd", on, False)]
    found = items()
    done = load_ids(READ)
    for info, n, _live in found:
        app = html.escape(n.get("app_name") or "")
        text = html.escape(" ".join(f'{n.get("summary") or ""} {n.get("body") or ""}'.split()))
        name = f"<b>{app}</b>" if n["id"] not in done else f'<span alpha="60%">{app}</span>'
        rows.append((f"{name} · {text}" if app else text, info, False, False))
    if found and confirm:
        rows.append((_("Clear all? Press again"), "clear", False, False, True))
        focus = "clear"
    elif found:
        rows.append((f'<span alpha="60%">{_("Clear all")}</span>', "clear", False, False))
    else:
        rows.append((f'<span alpha="60%">{_("No notifications")}</span>', "none", False, True))
    infos = [r[1] for r in rows]
    if focus not in infos and focus and focus[:2] in ("a:", "h:"):
        focus = next((i for i in infos if i[:2] in ("a:", "h:")), "dnd")
    option("new-selection", str(infos.index(focus) if focus in infos else 0))
    for text, info, active, nonselectable, *urgent in rows:
        extra = ("\x1factive\x1ftrue" if active else "") + \
                ("\x1fnonselectable\x1ftrue" if nonselectable else "") + \
                ("\x1furgent\x1ftrue" if urgent else "")
        sys.stdout.write(f"{text}\0info\x1f{info}{extra}\n")


def detail(offset, info, focus=None):
    """The whole notification and Delete; a click or Enter on the text goes to the app,
    Back, Escape or ← return to the list."""
    n = find(info)
    if n is None:
        show(offset, "dnd")
        return
    mark_read(info)
    common_options(offset, False, f'{offset}:l:d={info.replace(":", "_")}')
    text = []
    if n.get("app_name"):
        text.append(f'<span alpha="60%">{html.escape(n["app_name"])}</span>')
    for part, bold in ((n.get("summary") or "", True), (n.get("body") or "", False)):
        for para in part.splitlines():
            for line in textwrap.wrap(para, WRAP) or [""]:
                line = html.escape(line)
                text.append(f"<b>{line}</b>" if bold else line)
    rows = [("‹ " + html.escape(_("Back")), "back")]
    rows += [(t, f"t{i}") for i, t in enumerate(text)]
    rows += [(html.escape(_("Delete")), "del")]
    infos = [r[1] for r in rows]
    option("new-selection", str(infos.index(focus) if focus in infos else 1))
    for label, key in rows:
        sys.stdout.write(f"{label}\0info\x1f{key}\n")


def fits(n):
    text = " ".join(f'{n.get("summary") or ""} {n.get("body") or ""}'.split())
    app = n.get("app_name") or ""
    return len(f"{app} · {text}" if app else text) <= WRAP and "\n" not in (n.get("body") or "")


def focus_app(n):
    keys = {k.lower() for k in (n.get("desktop_entry"), n.get("app_name")) if k}
    try:
        wins = json.loads(run("niri", "msg", "--json", "windows").stdout or "[]")
    except ValueError:
        return False
    for w in wins:
        app_id = (w.get("app_id") or "").lower()
        if app_id and any(k == app_id or k in app_id or app_id.endswith("." + k) for k in keys):
            run("niri", "msg", "action", "focus-window", "--id", str(w["id"]))
            return True
    return False


def delete(info):
    items.cache_clear()
    if info.startswith("a:"):
        run("makoctl", "dismiss", "--no-history", "-n", info[2:])
    elif info.startswith("h:") and info[2:].isdigit():
        hide([int(info[2:])])
    refresh_bar()


def go(info):
    for key, n, live in items():
        if key != info:
            continue
        if live:
            run("makoctl", "invoke", "-n", str(n["id"]))
        focus_app(n)
        delete(info)
        return True
    return False


def clear():
    items.cache_clear()
    run("makoctl", "dismiss", "--all", "--no-history")
    hide(n["id"] for n in mako_json("history"))
    refresh_bar()


def neighbour(keys, info):
    if info not in keys:
        return "dnd"
    i = keys.index(info)
    rest = keys[i + 1:i + 2] or (keys[i - 1:i] if i else [])
    return rest[0] if rest else "dnd"


# launch

def our_rofi():
    for pid in run("pgrep", "-x", "rofi").stdout.split():
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if any(a.decode(errors="replace").endswith(f"{SELF} list") for a in args):
            return pid
    return None


def launch():
    pid = our_rofi()
    if pid:
        run("kill", pid)
        sys.exit(0)
    name = _("summary")
    cmd = ["rofi", "-show", name, "-modes", f"{name}:{SELF} list",
           "-replace", "-show-icons",
           "-kb-cancel", "Control+g,Control+bracketleft", "-kb-custom-3", "Escape",
           "-kb-delete-entry", "Shift+Delete,MouseMiddle,MouseSecondary",
           "-kb-move-char-back", "Control+b", "-kb-move-char-forward", "Control+f",
           "-kb-custom-4", "Left", "-kb-custom-5", "Right",
           "-kb-element-next", "", "-kb-element-prev", "",
           "-kb-custom-6", "Tab,ISO_Left_Tab",
           "-kb-custom-2", "Control+Shift+Delete"]
    if THEME.exists():
        title_text = _("Notifications").replace('"', "")
        cmd += ["-theme", str(THEME), "-theme-str", f'textbox-title {{ content: "{title_text}"; }}']
    cmd += zen.switch_args({2, 3, 4, 5, 6})
    os.execvp("rofi", cmd)


def handle_detail(retv, info, offset, opened):
    if retv in (LEFT, ESC) or (retv == SELECT and info == "back"):
        show(offset, opened)
    elif retv == SELECT and info[:1] == "t" and go(opened):
        pass
    elif retv in (RIGHT, DELETE) or (retv == SELECT and info == "del"):
        keys = [k for k, _x, _y in items()]
        delete(opened)
        show(offset, neighbour(keys, opened))
    else:
        detail(offset, opened, info)
    return 0


def main():
    if len(sys.argv) < 2:
        launch()
    if sys.argv[1] == "fetch":
        return fetch()
    if sys.argv[1] == "clear":
        clear()
        return 0
    if sys.argv[1] == "dnd" and sys.argv[2:] == ["toggle"]:
        dnd_toggle()
        return 0
    if sys.argv[1] == "seen" and sys.argv[2:3] and sys.argv[2].isdigit():
        hide([int(sys.argv[2])])
        refresh_bar()
        return 0
    if sys.argv[1] == "dnd":
        if dnd_on():
            count = unread()
            print(f"{BELL_OFF} {count}" if count else BELL_OFF)
        else:
            count = unread(history_only=True)
            print(f"{BELL} {count}" if count else "")
        return 0
    if sys.argv[1] != "list":
        sys.exit(__doc__)
    retv = int(os.environ.get("ROFI_RETV", "0"))
    if zen.switch(retv, "zen-center"):
        return 0
    data = (os.environ.get("ROFI_DATA") or "0").split(":")
    try:
        offset = int(data[0])
    except ValueError:
        offset = 0
    cal = data[1:2] == ["c"]
    pending = "wipe" in data[2:]
    opened = next((d[2:].replace("_", ":", 1) for d in data[2:] if d.startswith("d=")), None)
    info = resolve(os.environ.get("ROFI_INFO", ""))
    focus = info or None
    arrow = retv in (LEFT, RIGHT)

    if opened:
        return handle_detail(retv, os.environ.get("ROFI_INFO", ""), offset, resolve(opened))
    if retv == ESC:
        return 0

    if arrow and not cal and info == "clear":
        if retv == LEFT:
            show(offset, "clear")
            return 0
        retv = WIPE
    if retv == WIPE or (retv == SELECT and info == "clear"):
        if pending:
            clear()
            show(offset, "dnd")
        else:
            show(offset, "clear", confirm=True)
        return 0
    note = info[:2] in ("a:", "h:")
    if retv == TAB:
        cal = not cal
    elif retv in (PREV_M, NEXT_M):
        offset += -1 if retv == PREV_M else 1
    elif arrow and cal:
        offset += -1 if retv == LEFT else 1
    elif arrow and info == "dnd":
        dnd_toggle()
    elif retv in (RIGHT, DELETE) and note:
        keys = [k for k, _x, _y in items()]
        delete(info)
        focus = neighbour(keys, info)
    elif retv == LEFT and note:
        if go(info):
            return 0
    elif retv == SELECT and note:
        n = find(info)
        if n is not None and fits(n):
            if go(info):
                return 0
        else:
            detail(offset, info)
            return 0
    elif retv == SELECT and info == "dnd":
        cal = False
        dnd_toggle()
    show(offset, focus, cal=cal)
    return 0


if __name__ == "__main__":
    sys.exit(main())

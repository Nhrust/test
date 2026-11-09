"""zen-audio — outputs, inputs, levels, applications and Bluetooth in one Rofi menu.

  zen-audio              open the menu (a second call closes it)
  zen-audio mic-mute     mute or unmute the default input (XF86AudioMicMute)
  zen-audio mute         mute or unmute the default output (XF86AudioMute)

Devices keep the names PipeWire gives them. Levels go in steps of 5% up to 100%.
While a player plays, the first row shows it: Enter pauses, ← and → change the track.
"""
import functools
import html
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import zen
from zen import _, run

SELF = os.path.realpath(sys.argv[0])
THEME = zen.CONFIG_HOME / "rofi/audio.rasi"
PAL = zen.palette()
STEP = 5
BAR = 20
MIC_SIGNAL = 12
CONNECTING = zen.RUNTIME / "zen-audio-connecting"

ICON_OUT, ICON_OUT_MUTED = "\U000F057E", "\U000F075F"
ICON_IN, ICON_IN_MUTED = "\U000F036C", "\U000F036D"

INIT, SELECT, ESC, LEFT, RIGHT = 0, 1, 12, 13, 14


# ---------------------------------------------------------------- PipeWire

class Graph:
    """Audio nodes from pw-dump: devices, applications and the defaults."""

    def __init__(self):
        res = run("pw-dump", "--no-colors")
        try:
            objects = json.loads(res.stdout or "[]")
        except json.JSONDecodeError:
            objects = []
        self.nodes = {}
        defaults = {}
        for o in objects:
            info = o.get("info") or {}
            if o.get("type") == "PipeWire:Interface:Node":
                props = info.get("props") or {}
                self.nodes[o["id"]] = props
            elif o.get("type") == "PipeWire:Interface:Metadata" and \
                    (o.get("props") or {}).get("metadata.name") == "default":
                for m in o.get("metadata") or []:
                    value = m.get("value")
                    if isinstance(value, dict):
                        defaults[m.get("key")] = value.get("name")
        self.default_sink = self._by_name(defaults.get("default.audio.sink"))
        self.default_source = self._by_name(defaults.get("default.audio.source"))

    def _by_name(self, name):
        return next((i for i, p in self.nodes.items() if p.get("node.name") == name), None)

    def of(self, media_class):
        return [i for i, p in sorted(self.nodes.items()) if p.get("media.class") == media_class]

    def sinks(self):
        return self.of("Audio/Sink")

    def sources(self):
        return self.of("Audio/Source")

    def apps(self):
        return [i for i in self.of("Stream/Output/Audio")
                if not self.nodes[i].get("stream.monitor")]

    def name(self, nid):
        p = self.nodes.get(nid) or {}
        return p.get("node.description") or p.get("node.nick") or p.get("node.name") or str(nid)

    def app_name(self, nid):
        p = self.nodes.get(nid) or {}
        return (p.get("application.name") or p.get("application.process.binary")
                or p.get("node.name") or str(nid))


@functools.lru_cache(maxsize=None)
def level(nid):
    """(percent, muted) of a node, or (None, False); read once per run."""
    out = run("wpctl", "get-volume", str(nid)).stdout
    parts = out.split()
    try:
        pct = round(float(parts[1]) * 100)
    except (IndexError, ValueError):
        return None, False
    return pct, "[MUTED]" in out


def set_level(nid, pct):
    level.cache_clear()
    pct = max(0, min(100, pct))
    run("wpctl", "set-volume", "-l", "1.0", str(nid), f"{pct / 100:.2f}")


def step_level(nid, delta):
    cur, _m = level(nid)
    if cur is None:
        return
    new = (cur // STEP + 1) * STEP if delta > 0 else (-(-cur // STEP) - 1) * STEP
    set_level(nid, new)


def toggle_mute(nid):
    level.cache_clear()
    run("wpctl", "set-mute", str(nid), "toggle")


def signal_mic():
    run("pkill", f"-RTMIN+{MIC_SIGNAL}", "-x", "waybar")


# ---------------------------------------------------------------- media player

PLAYING, PAUSED = "\U000F040A", "\U000F03E4"


def player():
    """What the active MPRIS player plays: {status, artist, title, name}, or None."""
    res = run("playerctl", "metadata", "--format",
              "{{status}}\t{{artist}}\t{{title}}\t{{playerName}}")
    parts = res.stdout.rstrip("\n").split("\t")
    if res.returncode != 0 or len(parts) != 4 or parts[0] not in ("Playing", "Paused"):
        return None
    return dict(zip(("status", "artist", "title", "name"), parts))


def player_do(action):
    """play-pause, previous or next; waits briefly so the menu shows the result."""
    before = player()
    run("playerctl", action)
    for _x in range(8):
        time.sleep(0.05)
        if player() != before:
            break


# ---------------------------------------------------------------- Bluetooth

BLUEZ = "org.bluez"


@functools.lru_cache(maxsize=None)
def bluetooth():
    """(adapter path, powered, [(device path, name, connected)]) from BlueZ, or None.

    One D-Bus call; only paired audio devices are listed."""
    res = run("busctl", "--json=short", "call", BLUEZ, "/",
              "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    try:
        objects = json.loads(res.stdout)["data"][0]
    except (ValueError, KeyError, IndexError):
        return None

    def val(props, key, default=None):
        return (props.get(key) or {}).get("data", default)

    adapter, powered, devices = None, False, []
    for path, ifaces in sorted(objects.items()):
        if "org.bluez.Adapter1" in ifaces and adapter is None:
            adapter = path
            powered = bool(val(ifaces["org.bluez.Adapter1"], "Powered", False))
        dev = ifaces.get("org.bluez.Device1")
        if dev and val(dev, "Paired", False):
            icon = val(dev, "Icon", "") or ""
            if icon and not icon.startswith("audio-"):
                continue
            name = val(dev, "Alias") or val(dev, "Name") or val(dev, "Address") or path
            devices.append((path, name, bool(val(dev, "Connected", False))))
    if adapter is None:
        return None
    return adapter, powered, devices


def bt_power(on):
    bt = bluetooth()
    if not bt:
        return
    res = run("busctl", "set-property", BLUEZ, bt[0], "org.bluez.Adapter1", "Powered",
              "b", "true" if on else "false")
    if res.returncode != 0:
        run("notify-send", "-a", _("Sound"), "-u", "critical", "Bluetooth",
            res.stderr.strip() or _("Could not switch"))


def bt_busy():
    try:
        return CONNECTING.read_text().split()
    except OSError:
        return []


def bt_toggle(path, connected):
    """Connect or disconnect in the background; a notification tells the result."""
    action = "disconnect" if connected else "connect"
    CONNECTING.write_text(f"{path} {action}\n")
    subprocess.Popen([sys.executable, SELF, "bt", action, path],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def bt_worker(action, path):
    CONNECTING.write_text(f"{path} {action}\n")
    try:
        res = run("busctl", "--timeout=30", "call", BLUEZ, path, "org.bluez.Device1",
                  "Connect" if action == "connect" else "Disconnect")
        bt = bluetooth()
        name = next((n for p, n, _c in (bt[2] if bt else []) if p == path), path)
        ok = res.returncode == 0
        if action == "connect":
            text = _("Connected: {}") if ok else _("Could not connect: {}")
        else:
            text = _("Disconnected: {}") if ok else _("Could not disconnect: {}")
        args = ["notify-send", "-a", _("Sound"), "-u", "normal" if ok else "critical", text.format(name)]
        if not ok and res.stderr.strip():
            args.append(res.stderr.strip())
        run(*args)
    finally:
        CONNECTING.unlink(missing_ok=True)
    return 0


# ---------------------------------------------------------------- menu

def esc(text):
    return html.escape(str(text))


def tint(text, role):
    return f'<span foreground="{PAL[role]}">{text}</span>'


def arrows(text):
    return f"‹ {text} ›"


def bar(pct, muted):
    if pct is None:
        return tint("─" * BAR, "line") + "    —"
    filled = round(min(pct, 100) * BAR / 100)
    color = "critical" if muted else "accent"
    return (tint("━" * filled, color) + tint("━" * (BAR - filled), "line")
            + tint(f"{pct:>4}%", "critical" if muted else "fg"))


def header(g):
    rows = []
    for nid, icons in ((g.default_sink, (ICON_OUT, ICON_OUT_MUTED)),
                       (g.default_source, (ICON_IN, ICON_IN_MUTED))):
        pct, muted = level(nid) if nid else (None, False)
        icon = tint(icons[1], "critical") if muted else icons[0]
        rows.append(f"{icon}  {bar(pct, muted)}")
    return " ".join(rows)


def onoff(muted):
    return tint(esc(arrows(_("off"))), "critical") if muted else esc(arrows(_("on")))


def percent(pct, muted):
    text = esc(arrows(f"{pct}%" if pct is not None else "—"))
    return tint(text, "critical") if muted else text


class Menu:

    def __init__(self, view, prompt, g):
        self.view, self.prompt, self.g = view, prompt, g
        self.rows = []

    def add(self, text, info, active=False, nonselectable=False):
        self.rows.append((text, info, active, nonselectable))

    def back(self):
        self.add("‹ " + esc(_("Back")), "view:main")

    def print(self, focus=None):
        option("prompt", self.prompt)
        option("message", header(self.g))
        option("data", self.view)
        option("markup-rows", "true")
        option("no-custom", "true")
        option("use-hot-keys", "true")
        option("keep-selection", "true")
        infos = [r[1] for r in self.rows]
        if focus not in infos:
            focus = next((r[1] for r in self.rows if r[2]), None)
        if focus not in infos:
            focus = next((r[1] for r in self.rows if not r[1].startswith("view:main") and not r[3]), None)
        option("new-selection", str(infos.index(focus) if focus in infos else 0))
        for text, info, active, nonselectable in self.rows:
            extra = ""
            if active:
                extra += "\x1factive\x1ftrue"
            if nonselectable:
                extra += "\x1fnonselectable\x1ftrue"
            sys.stdout.write(f"{text}\0info\x1f{info}{extra}\n")


def option(key, value):
    sys.stdout.write(f"\0{key}\x1f{value}\n")


def show_main(g, focus):
    menu = Menu("main", _("sound"), g)
    media = player()
    if media:
        icon = PLAYING if media["status"] == "Playing" else PAUSED
        what = " — ".join(x for x in (media["artist"], media["title"]) if x) or media["name"]
        menu.add(f"{icon}  {esc(what)}", "media:", active=media["status"] == "Playing")
    sink, source = g.default_sink, g.default_source
    menu.add(f'{esc(_("Output"))} · {esc(g.name(sink)) if sink else "—"}  ›', "view:outputs")
    if sink:
        pct, muted = level(sink)
        menu.add(f'{esc(_("Volume"))} · {percent(pct, muted)}', f"adj:vol:{sink}")
        menu.add(f'{esc(_("Sound"))} · {onoff(muted)}', f"adj:mute:{sink}")
    menu.add(f'{esc(_("Input"))} · {esc(g.name(source)) if source else "—"}  ›', "view:inputs")
    if source:
        pct, muted = level(source)
        menu.add(f'{esc(_("Input level"))} · {percent(pct, muted)}', f"adj:vol:{source}")
        menu.add(f'{esc(_("Microphone"))} · {onoff(muted)}', f"adj:mute:{source}")
    apps = g.apps()
    if apps:
        menu.add(f'{esc(_("Applications"))} · {len(apps)}  ›', "view:apps")
    bt = bluetooth()
    if bt:
        _a, on, devices = bt
        n = sum(1 for _p, _n, c in devices if c)
        if not on:
            state = _("off")
        else:
            state = zen.ngettext("{} connected", "{} connected", n).format(n) if n else _("on")
        menu.add(f'Bluetooth · {esc(state)}  ›', "view:bt")
    menu.print(focus or "view:outputs")


def show_devices(g, kind, focus):
    sinks = kind == "outputs"
    menu = Menu(kind, f'{_("sound")} › {_("outputs") if sinks else _("inputs")}', g)
    menu.back()
    default = g.default_sink if sinks else g.default_source
    ids = g.sinks() if sinks else g.sources()
    for nid in ids:
        menu.add(esc(g.name(nid)), f"default:{nid}", active=(nid == default))
    if not ids:
        menu.add(esc(_("No devices")), "none", nonselectable=True)
    menu.print(focus or (f"default:{default}" if default else None))


def show_levels(g, nid, focus):
    is_sink = nid == g.default_sink or nid in g.sinks()
    what = _("volume") if is_sink else _("input level")
    menu = Menu(f"vol:{nid}", f'{_("sound")} › {what}', g)
    menu.back()
    cur, _m = level(nid)
    for pct in range(100, -1, -10):
        menu.add(f"{pct}%", f"set:{nid}:{pct}", active=cur is not None and abs(cur - pct) < 5)
    menu.print(focus)


def show_apps(g, focus):
    menu = Menu("apps", f'{_("sound")} › {_("applications")}', g)
    menu.back()
    apps = g.apps()
    for nid in apps:
        pct, muted = level(nid)
        menu.add(f"{esc(g.app_name(nid))} · {percent(pct, muted)}", f"app:{nid}")
    if not apps:
        menu.add(esc(_("Nothing is playing")), "none", nonselectable=True)
    menu.print(focus)


def show_bt(g, focus):
    menu = Menu("bt", f'{_("sound")} › Bluetooth', g)
    menu.back()
    _a, on, devices = bluetooth()
    menu.add(f'Bluetooth · {esc(arrows(_("on") if on else _("off")))}', "adj:btpower:0", active=on)
    if on:
        busy = bt_busy()
        for path, name, connected in devices:
            if busy and busy[0] == path:
                state = _("connecting…") if busy[1] == "connect" else _("disconnecting…")
            else:
                state = _("connected") if connected else _("not connected")
            menu.add(f"{esc(name)} · {esc(state)}", f"bt:{path}:{int(connected)}", active=connected)
        if not devices:
            menu.add(esc(_("No paired audio devices; pair one with bluetoothctl")), "none",
                     nonselectable=True)
    menu.print(focus)


def show(view, focus=None):
    g = Graph()
    kind, _x, rest = view.partition(":")
    if kind in ("outputs", "inputs"):
        show_devices(g, kind, focus)
    elif kind == "vol" and rest.isdigit() and int(rest) in g.nodes:
        show_levels(g, int(rest), focus)
    elif kind == "apps":
        show_apps(g, focus)
    elif kind == "bt" and bluetooth():
        show_bt(g, focus)
    else:
        show_main(g, focus)


def parent(view):
    return None if view == "main" else "main"


def adjust(what, nid, delta):
    if what == "vol":
        step_level(nid, delta)
    elif what == "mute":
        toggle_mute(nid)
        signal_mic()
    elif what == "btpower":
        bt = bluetooth()
        if bt:
            bt_power(not bt[1])
            bluetooth.cache_clear()


def act(info):
    kind, _x, rest = info.partition(":")
    if kind == "view":
        return rest, None
    if kind == "adj":
        what, _x, nid = rest.partition(":")
        if what == "vol":
            return f"vol:{nid}", None
        adjust(what, int(nid), +1)
        return None, info
    if kind == "default":
        run("wpctl", "set-default", rest)
        signal_mic()
        return None, info
    if kind == "set":
        nid, _x, pct = rest.partition(":")
        set_level(int(nid), int(pct))
        return None, info
    if kind == "app":
        toggle_mute(int(rest))
        return None, info
    if kind == "media":
        player_do("play-pause")
        return None, info
    if kind == "bt":
        path, _x, connected = rest.rpartition(":")
        if not bt_busy():
            bt_toggle(path, connected == "1")
        return None, info
    return "main", None


def side_keys(info, delta):
    kind, _x, rest = info.partition(":")
    if kind == "adj":
        what, _x, nid = rest.partition(":")
        adjust(what, int(nid), delta)
    elif kind == "app":
        step_level(int(rest), delta)
    elif kind == "media":
        player_do("previous" if delta < 0 else "next")


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
    mode = _("sound")
    cmd = ["rofi", "-show", mode, "-modes", f"{mode}:{SELF} list",
           "-replace", "-no-show-icons",
           "-kb-cancel", "Control+g,Control+bracketleft", "-kb-custom-3", "Escape",
           "-kb-move-char-back", "Control+b", "-kb-move-char-forward", "Control+f",
           "-kb-custom-4", "Left", "-kb-custom-5", "Right"]
    if THEME.exists():
        cmd += ["-theme", str(THEME)]
    os.execvp("rofi", cmd)


def main():
    if len(sys.argv) < 2:
        launch()
    cmd = sys.argv[1]
    if cmd == "mic-mute":
        run("wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "toggle")
        signal_mic()
        return 0
    if cmd == "mute":
        run("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle")
        return 0
    if cmd == "bt" and len(sys.argv) == 4 and sys.argv[2] in ("connect", "disconnect"):
        return bt_worker(sys.argv[2], sys.argv[3])
    if cmd != "list":
        sys.exit(__doc__)
    retv = int(os.environ.get("ROFI_RETV", "0"))
    info = os.environ.get("ROFI_INFO", "")
    view = os.environ.get("ROFI_DATA") or "main"
    focus = None
    if retv == ESC:
        focus = f"adj:vol:{view[4:]}" if view.startswith("vol:") else f"view:{view}"
        view = parent(view)
        if view is None:
            return 0
    elif retv in (LEFT, RIGHT):
        focus = info
        side_keys(info, -1 if retv == LEFT else +1)
    elif retv == SELECT and info:
        new_view, focus = act(info)
        view = new_view or view
    show(view, focus)
    return 0


if __name__ == "__main__":
    sys.exit(main())

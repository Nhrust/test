"""zen-network — Wi-Fi, Ethernet and Tailscale in one Rofi menu.

  zen-network              open the menu (a second call closes it)
  zen-network wifi toggle  switch Wi-Fi on or off (right click on the panel icon)

NetworkManager (nmcli) runs the networks and Tailscale its own network. A new
network with a password asks for it in a separate prompt that hides what you
type; the password goes to nmcli on its standard input, never on a command line.
Connecting happens in the background and ends with a notification.
"""
import functools
import html
import json
import os
import subprocess
import sys
from pathlib import Path

import zen
from zen import _, run

SELF = os.path.realpath(sys.argv[0])
THEME = zen.CONFIG_HOME / "rofi/network.rasi"
PAL = zen.palette()
BUSY = zen.RUNTIME / "zen-network-busy"

INIT, SELECT, ESC, LEFT, RIGHT = 0, 1, 12, 13, 14

SIGNAL = ["\U000F091F", "\U000F0922", "\U000F0925", "\U000F0928"]
WIFI_OFF, LOCK, ETHER, TAILNET = "\U000F092E", "\U000F033E", "\U000F0200", "\U000F0582"


# ---------------------------------------------------------------- NetworkManager

def fields(line):
    """Split one line of nmcli --terse output; ':' and '\\' inside values are escaped."""
    out, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def nmcli(*args):
    res = run("nmcli", "--terse", *args)
    return [fields(line) for line in res.stdout.splitlines() if line]


@functools.lru_cache(maxsize=None)
def devices():
    """[(device, type, state, connection)] for Wi-Fi and Ethernet."""
    return [tuple(f[:4]) for f in nmcli("--fields", "DEVICE,TYPE,STATE,CONNECTION", "device")
            if len(f) >= 4 and f[1] in ("wifi", "ethernet")]


def device(kind):
    return next((d for d in devices() if d[1] == kind), None)


@functools.lru_cache(maxsize=None)
def wifi_on():
    return run("nmcli", "radio", "wifi").stdout.strip() == "enabled"


@functools.lru_cache(maxsize=None)
def networks():
    """Visible networks, strongest first, one row per name:
    {ssid, signal, secure, active, freq, chan, security}."""
    seen = {}
    for f in nmcli("--fields", "IN-USE,SSID,SIGNAL,SECURITY,FREQ,CHAN", "device", "wifi", "list",
                   "--rescan", "no"):
        if len(f) < 6 or not f[1]:
            continue
        net = {"active": f[0] == "*", "ssid": f[1], "signal": int(f[2] or 0),
               "security": f[3], "secure": f[3] not in ("", "--"), "freq": f[4], "chan": f[5]}
        old = seen.get(net["ssid"])
        # several access points of one network: the one in use, else the strongest
        if old is None or (net["active"], net["signal"]) > (old["active"], old["signal"]):
            seen[net["ssid"]] = net
    return sorted(seen.values(), key=lambda n: (not n["active"], -n["signal"]))


@functools.lru_cache(maxsize=None)
def saved():
    """Names of saved Wi-Fi connections."""
    return {f[0] for f in nmcli("--fields", "NAME,TYPE", "connection", "show")
            if len(f) >= 2 and f[1] == "802-11-wireless"}


def details(dev):
    """[(label, value)] of addresses for a device."""
    out = []
    names = {"IP4.ADDRESS": "IPv4", "IP4.GATEWAY": _("Gateway"), "IP4.DNS": "DNS", "IP6.ADDRESS": "IPv6"}
    res = run("nmcli", "--terse", "--fields", "IP4.ADDRESS,IP4.GATEWAY,IP4.DNS,IP6.ADDRESS",
              "device", "show", dev)
    for line in res.stdout.splitlines():
        # "IP6.ADDRESS[1]:fd00::5/64": the name ends at the first colon; nmcli may
        # escape the colons inside the value, or not, depending on the version
        key, _x, value = line.partition(":")
        key, value = key.split("[", 1)[0], fields(value)
        value = ":".join(value)
        if key in names and value and not (key == "IP6.ADDRESS" and value.startswith("fe80")):
            out.append((names[key], value))
    return out


def bars(signal):
    return SIGNAL[min(3, signal // 25)]


def band(freq):
    try:
        mhz = int(freq.split()[0])
    except (ValueError, IndexError):
        return ""
    return "6 GHz" if mhz >= 5925 else "5 GHz" if mhz >= 5000 else "2.4 GHz"


# ---------------------------------------------------------------- Tailscale

@functools.lru_cache(maxsize=None)
def tailscale():
    """tailscale status --json, or None when Tailscale is not installed or not running."""
    res = run("tailscale", "status", "--json")
    try:
        return json.loads(res.stdout)
    except ValueError:
        return None


def ts_on(ts):
    return bool(ts) and ts.get("BackendState") == "Running"


def peers(ts):
    """Other devices, online first: [(id, peer)]."""
    items = list(((ts or {}).get("Peer") or {}).items())
    return sorted(items, key=lambda kv: (not kv[1].get("Online"), peer_name(kv[1]).lower()))


def peer_name(p):
    return p.get("HostName") or (p.get("DNSName") or "").split(".")[0] or "?"


def exit_node(ts):
    return next((p for _k, p in peers(ts) if p.get("ExitNode")), None)


# ---------------------------------------------------------------- background work

def busy():
    try:
        return BUSY.read_text().strip()
    except OSError:
        return ""


def spawn(*args):
    """Run "zen-network do ..." in the background: connecting takes seconds."""
    zen.detach(sys.executable, SELF, "do", *args)


def last_line(res):
    lines = (res.stderr or "").strip().splitlines()
    return lines[-1] if lines else ""


def notify(ok, text, detail=""):
    args = ["notify-send", "-a", _("Network"), "-u", "normal" if ok else "critical", text]
    if detail:
        args.append(detail)
    run(*args)


def ask_password(ssid):
    """A Rofi prompt that hides what is typed; None when cancelled."""
    cmd = ["rofi", "-dmenu", "-password", "-replace", "-p", _("Password"),
           "-mesg", html.escape(_("Wi-Fi network {}").format(ssid)),
           "-theme-str", 'listview { enabled: false; } entry { placeholder: ""; }']
    res = subprocess.run(cmd, input="", capture_output=True, text=True)
    return res.stdout.rstrip("\n") if res.returncode == 0 else None


def worker(action, target):
    try:
        if action == "connect":
            if target in saved():
                BUSY.write_text(target)
                res = run("nmcli", "connection", "up", "id", target)
            else:
                net = next((n for n in networks() if n["ssid"] == target), None)
                if net and net["secure"]:
                    password = ask_password(target)
                    if not password:
                        return 0
                    BUSY.write_text(target)
                    res = subprocess.run(["nmcli", "--ask", "device", "wifi", "connect", target],
                                         input=password + "\n", capture_output=True, text=True)
                else:
                    BUSY.write_text(target)
                    res = run("nmcli", "device", "wifi", "connect", target)
            ok = res.returncode == 0
            notify(ok, (_("Connected: {}") if ok else _("Could not connect: {}")).format(target),
                   "" if ok else last_line(res))
        elif action == "up":
            BUSY.write_text(target)
            res = run("nmcli", "device", "connect", target)
            notify(res.returncode == 0, (_("Connected: {}") if res.returncode == 0
                                         else _("Could not connect: {}")).format(target))
    finally:
        BUSY.unlink(missing_ok=True)
    return 0


# ---------------------------------------------------------------- menu

def esc(text):
    return html.escape(str(text))


def tint(text, role):
    return f'<span foreground="{PAL[role]}">{text}</span>'


def arrows(text):
    return f"‹ {text} ›"


def header():
    lines = []
    wifi = device("wifi")
    if wifi:
        active = next((n for n in networks() if n["active"]), None)
        if not wifi_on():
            lines.append(f'{tint(WIFI_OFF, "line")}  {tint(esc(_("Wi-Fi is off")), "muted")}')
        elif active:
            lines.append(f'{bars(active["signal"])}  <b>{esc(active["ssid"])}</b>  '
                         + tint(f'{band(active["freq"])} · {active["signal"]}%', "muted"))
        else:
            lines.append(f'{tint(SIGNAL[0], "line")}  {tint(esc(_("not connected")), "muted")}')
    eth = device("ethernet")
    if eth:
        state = _("connected") if eth[2] == "connected" else _("no cable") if eth[2] == "unavailable" \
            else _("not connected")
        lines.append(f'{ETHER}  {tint(esc("Ethernet · " + state), "muted" if eth[2] != "connected" else "fg")}')
    ts = tailscale()
    if ts is not None:
        if ts_on(ts):
            online = sum(1 for _k, p in peers(ts) if p.get("Online"))
            lines.append(f'{tint(TAILNET, "accent")}  Tailscale  ' + tint(esc(
                zen.ngettext("{} device online", "{} devices online", online).format(online)), "muted"))
        else:
            lines.append(f'{tint(TAILNET, "line")}  {tint("Tailscale · " + esc(_("off")), "muted")}')
    return " ".join(lines)


class Menu:

    def __init__(self, view):
        self.view = view
        self.rows = []
        self.skip = {"rescan"}

    def add(self, text, info, active=False, passive=False):
        # a row with nothing to do cannot be selected; the arrows skip it
        self.rows.append((text, info, active, passive or info == "none"))

    def back(self, to="view:main"):
        self.skip.add(to)
        self.add("‹ " + esc(_("Back")), to)

    def print(self, focus=None):
        option("prompt", _("network"))
        option("message", header())
        option("data", self.view)
        option("markup-rows", "true")
        option("no-custom", "true")
        option("use-hot-keys", "true")
        option("keep-selection", "true")
        infos = [r[1] for r in self.rows]
        if focus not in infos:
            focus = next((r[1] for r in self.rows if r[2]), None)
        if focus not in infos:
            focus = next((r[1] for r in self.rows if r[1] not in self.skip and not r[3]), None)
        option("new-selection", str(infos.index(focus) if focus in infos else 0))
        for text, info, active, passive in self.rows:
            extra = ("\x1factive\x1ftrue" if active else "") + ("\x1fnonselectable\x1ftrue" if passive else "")
            sys.stdout.write(f"{text}\0info\x1f{info}{extra}\n")


def option(key, value):
    sys.stdout.write(f"\0{key}\x1f{value}\n")


def show_main(focus):
    menu = Menu("main")
    wifi = device("wifi")
    if wifi:
        on = wifi_on()
        menu.add(f'Wi-Fi · {esc(arrows(_("on") if on else _("off")))}', "adj:wifi", active=on)
        if on:
            active = next((n for n in networks() if n["active"]), None)
            if active:
                menu.add(f'{esc(active["ssid"])} · {esc(_("connected"))}  ›', f"view:dev:{wifi[0]}")
            menu.add(f'{esc(_("Networks"))}  ›', "view:wifi")
    eth = device("ethernet")
    if eth:
        state = _("connected") if eth[2] == "connected" else _("not connected")
        menu.add(f"Ethernet · {esc(state)}  ›", f"view:dev:{eth[0]}")
    ts = tailscale()
    if ts is not None:
        on = ts_on(ts)
        if ts.get("BackendState") == "NeedsLogin":
            menu.add(f'Tailscale · {esc(_("log in with: tailscale up"))}', "none", passive=True)
        else:
            menu.add(f'Tailscale · {esc(arrows(_("on") if on else _("off")))}', "adj:ts", active=on)
        if on:
            online = sum(1 for _k, p in peers(ts) if p.get("Online"))
            menu.add(f'{esc(_("Devices"))} · {online}/{len(peers(ts))}  ›', "view:ts")
            node = exit_node(ts)
            menu.add(f'{esc(_("Exit node"))} · {esc(peer_name(node) if node else _("none"))}  ›', "view:exit")
    if not menu.rows:
        menu.add(esc(_("No network devices")), "none", passive=True)
    menu.print(focus)


def show_wifi(focus):
    menu = Menu("wifi")
    menu.back()
    menu.add(esc(_("Search again")), "rescan")
    target = busy()
    known = saved()
    for n in networks():
        state = []
        if n["ssid"] == target:
            state.append(_("connecting…"))
        elif n["active"]:
            state.append(_("connected"))
        elif n["ssid"] in known:
            state.append(_("saved"))
        lock = f" {LOCK}" if n["secure"] else ""
        text = f'{bars(n["signal"])}  {esc(n["ssid"])}{lock}'
        if state:
            text += " · " + esc(state[0])
        menu.add(text, f'net:{n["ssid"]}', active=n["active"])
    if len(menu.rows) == 2:
        menu.add(esc(_("No networks found")), "none", passive=True)
    menu.print(focus)


def show_device(dev, focus):
    """Addresses of a connection; Enter on one copies it. Disconnect or Forget below."""
    menu = Menu(f"dev:{dev}")
    menu.back()
    d = next((x for x in devices() if x[0] == dev), None)
    if d is None:
        return show_main(None)
    if d[1] == "wifi":
        active = next((n for n in networks() if n["active"]), None)
        if active:
            menu.add(f'{esc(_("Network"))} · {esc(active["ssid"])}', f'copy:{active["ssid"]}')
            menu.add(f'{esc(_("Signal"))} · {active["signal"]}% · {band(active["freq"])} · '
                     f'{esc(_("channel"))} {esc(active["chan"])}', "none")
            menu.add(f'{esc(_("Security"))} · {esc(active["security"] or _("none"))}', "none")
    for label, value in details(dev):
        menu.add(f"{esc(label)} · {esc(value)}", f"copy:{value.split('/')[0]}")
    if d[2] == "connected":
        menu.add(esc(_("Disconnect")), f"disconnect:{dev}")
        if d[1] == "wifi" and d[3] in saved():
            menu.add(esc(_("Forget this network")), f"forget:{d[3]}")
    elif d[1] == "ethernet" and d[2] != "unavailable":
        menu.add(esc(_("Connect")), f"up:{dev}")
    menu.print(focus)


def show_ts(focus):
    menu = Menu("ts")
    menu.back()
    for key, p in peers(tailscale()):
        # plain text: a colour of its own would vanish on the highlighted row
        state = _("online") if p.get("Online") else _("offline")
        menu.add(f"{esc(peer_name(p))} · {esc(state)}  ›", f"view:peer:{key}", active=bool(p.get("ExitNode")))
    if len(menu.rows) == 1:
        menu.add(esc(_("No other devices")), "none", passive=True)
    menu.print(focus)


def show_peer(key, focus):
    ts = tailscale()
    p = ((ts or {}).get("Peer") or {}).get(key)
    if p is None:
        return show_ts(None)
    menu = Menu(f"peer:{key}")
    menu.back("view:ts")
    menu.add(f"<b>{esc(peer_name(p))}</b> · {esc(p.get('OS') or '')}", "none")
    for ip in p.get("TailscaleIPs") or []:
        menu.add(f"{'IPv6' if ':' in ip else 'IPv4'} · {esc(ip)}", f"copy:{ip}")
    if p.get("DNSName"):
        dns = p["DNSName"].rstrip(".")
        menu.add(f"DNS · {esc(dns)}", f"copy:{dns}")
    if not p.get("Online") and p.get("LastSeen"):
        menu.add(f'{esc(_("Last seen"))} · {esc(p["LastSeen"][:16].replace("T", " "))}', "none")
    if p.get("ExitNodeOption"):
        if p.get("ExitNode"):
            menu.add(esc(_("Stop using as exit node")), "exit:")
        else:
            menu.add(esc(_("Use as exit node")), f"exit:{p['TailscaleIPs'][0]}")
    menu.print(focus)


def show_exit(focus):
    ts = tailscale()
    menu = Menu("exit")
    menu.back()
    node = exit_node(ts)
    menu.add(esc(_("None")), "exit:", active=node is None)
    for _k, p in peers(ts):
        if p.get("ExitNodeOption"):
            state = "" if p.get("Online") else " · " + esc(_("offline"))
            menu.add(esc(peer_name(p)) + state, f"exit:{p['TailscaleIPs'][0]}", active=bool(p.get("ExitNode")))
    menu.print(focus)


def show(view, focus=None):
    kind, _x, rest = view.partition(":")
    if kind == "wifi" and wifi_on():
        show_wifi(focus)
    elif kind == "dev":
        show_device(rest, focus)
    elif kind == "ts" and ts_on(tailscale()):
        show_ts(focus)
    elif kind == "peer" and ts_on(tailscale()):
        show_peer(rest, focus)
    elif kind == "exit" and ts_on(tailscale()):
        show_exit(focus)
    else:
        show_main(focus)


def clear_caches():
    for f in (devices, wifi_on, networks, saved, tailscale):
        f.cache_clear()


def toggle_wifi():
    run("nmcli", "radio", "wifi", "off" if wifi_on() else "on")
    clear_caches()


def toggle_tailscale():
    res = run("tailscale", "down" if ts_on(tailscale()) else "up")
    if res.returncode != 0:
        notify(False, "Tailscale", last_line(res))
    clear_caches()


def act(info, view):
    """→ (view, focus)."""
    kind, _x, rest = info.partition(":")
    if kind == "view":
        return rest, None
    if kind == "adj":
        (toggle_wifi if rest == "wifi" else toggle_tailscale)()
        return view, info
    if kind == "rescan":
        # waits until the scan is done, then the list below reads the result
        run("nmcli", "--terse", "device", "wifi", "list", "--rescan", "yes")
        clear_caches()
        return view, info
    if kind == "net":
        net = next((n for n in networks() if n["ssid"] == rest), None)
        wifi = device("wifi")
        if net and net["active"] and wifi:
            return f"dev:{wifi[0]}", None
        if busy():
            return view, info
        spawn("connect", rest)
        if net and net["secure"] and rest not in saved():
            # the password prompt takes the screen: the menu closes first
            return None, None
        BUSY.write_text(rest)
        return view, info
    if kind == "copy":
        subprocess.run(["wl-copy", "--", rest], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        notify(True, _("Copied: {}").format(rest))
        return view, info
    if kind == "disconnect":
        run("nmcli", "device", "disconnect", rest)
        clear_caches()
        return "main", None
    if kind == "forget":
        run("nmcli", "connection", "delete", "id", rest)
        clear_caches()
        return "main", None
    if kind == "up":
        spawn("up", rest)
        return view, info
    if kind == "exit":
        res = run("tailscale", "set", f"--exit-node={rest}")
        if res.returncode != 0:
            notify(False, _("Exit node"), last_line(res))
        clear_caches()
        return view, info
    return view, info


def parent(view):
    if view.startswith("peer:"):
        return "ts", f"view:{view}"
    if view == "main":
        return None, None
    return "main", f"view:{view}"


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
    if wifi_on():
        subprocess.Popen(["nmcli", "device", "wifi", "rescan"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    mode = _("network")
    cmd = ["rofi", "-show", mode, "-modes", f"{mode}:{SELF} list",
           "-replace", "-no-show-icons",
           "-kb-cancel", "Control+g,Control+bracketleft", "-kb-custom-3", "Escape",
           "-kb-move-char-back", "Control+b", "-kb-move-char-forward", "Control+f",
           "-kb-custom-4", "Left", "-kb-custom-5", "Right"]
    if THEME.exists():
        cmd += ["-theme", str(THEME)]
    cmd += zen.switch_args({3, 4, 5})
    os.execvp("rofi", cmd)


def main():
    if len(sys.argv) < 2:
        launch()
    cmd = sys.argv[1]
    if cmd == "wifi" and sys.argv[2:] == ["toggle"]:
        toggle_wifi()
        return 0
    if cmd == "do" and len(sys.argv) == 4:
        return worker(sys.argv[2], sys.argv[3])
    if cmd != "list":
        sys.exit(__doc__)
    retv = int(os.environ.get("ROFI_RETV", "0"))
    if zen.switch(retv, "zen-network"):
        return 0
    info = os.environ.get("ROFI_INFO", "")
    view = os.environ.get("ROFI_DATA") or "main"
    focus = None
    if retv == ESC:
        view, focus = parent(view)
        if view is None:
            return 0
    elif retv in (LEFT, RIGHT):
        # the arrows switch the row under them, as in the sound menu
        focus = info
        if info.startswith("adj:"):
            view, focus = act(info, view)
    elif retv == SELECT and info:
        view, focus = act(info, view)
        if view is None:
            return 0
    show(view, focus)
    return 0


if __name__ == "__main__":
    sys.exit(main())

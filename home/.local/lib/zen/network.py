"""zen-network — Wi-Fi, Ethernet and Tailscale in one Rofi menu.

  zen-network              open the menu (a second call closes it)
  zen-network open VIEW    open the menu on a view (the prompts come back this way)
  zen-network wifi toggle  switch Wi-Fi on or off (right click on the panel icon)

NetworkManager (nmcli) runs the networks and Tailscale its own network. Each
saved network keeps its own settings: automatic connection, metered, MAC
address, password, DNS, DNS over TLS, IPv4 and IPv6. A change applies at once
to a connected network, without dropping it (the MAC address reconnects).

What has to be typed (a password, a DNS server, an address) is asked in a
separate prompt; the menu closes for it and opens again where it was. A
password goes to nmcli and qrencode on their standard input, never on a
command line, and a copied password stays out of the clipboard history.
"""
import functools
import html
import ipaddress
import json
import os
import re
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
WIFI, WIRED = "802-11-wireless", "802-3-ethernet"
HIDDEN_PASSWORD = "•" * 8

# (key, name, IPv4 servers, IPv6 servers, note); all of them answer DNS over TLS
DNS = [("cloudflare", "Cloudflare", ["1.1.1.1", "1.0.0.1"],
        ["2606:4700:4700::1111", "2606:4700:4700::1001"], ""),
       ("quad9", "Quad9", ["9.9.9.9", "149.112.112.112"], ["2620:fe::fe", "2620:fe::9"],
        "blocks dangerous sites"),
       ("adguard", "AdGuard", ["94.140.14.14", "94.140.15.15"],
        ["2a10:50c0::ad1:ff", "2a10:50c0::ad2:ff"], "blocks ads")]


def cycles():
    """Values the arrows go through: setting → [(nmcli value, label)]."""
    return {
        "mac": [("permanent", _("permanent")), ("stable", _("own for this network")),
                ("random", _("new on every connection"))],
        "dot": [("no", _("off")), ("opportunistic", _("when possible")), ("yes", _("always"))],
        "ip4m": [("auto", _("automatic")), ("manual", _("manual"))],
        "ip6m": [("auto", _("automatic")), ("link-local", _("local network only")),
                 ("disabled", _("off"))],
    }


# ---------------------------------------------------------------- NetworkManager

def fields(line):
    """Split one line of nmcli --terse output; ':' and '\\' inside values are escaped."""
    out, cur, esc_next = [], "", False
    for ch in line:
        if esc_next:
            cur += ch
            esc_next = False
        elif ch == "\\":
            esc_next = True
        elif ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def unescape(value):
    return ":".join(fields(value))


def nmcli(*args):
    res = run("nmcli", "--terse", *args)
    return [fields(line) for line in res.stdout.splitlines() if line]


@functools.lru_cache(maxsize=None)
def devices():
    """[(device, type, state, connection, connection uuid)] for Wi-Fi and Ethernet."""
    out = []
    for f in nmcli("--fields", "DEVICE,TYPE,STATE,CONNECTION,CON-UUID", "device"):
        if len(f) >= 4 and f[1] in ("wifi", "ethernet"):
            out.append(tuple((f + [""])[:5]))
    return out


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
def connections():
    """Saved Wi-Fi and wired connections: [{name, uuid, type, device}]."""
    return [{"name": f[0], "uuid": f[1], "type": f[2], "device": f[3]}
            for f in nmcli("--fields", "NAME,UUID,TYPE,DEVICE", "connection", "show")
            if len(f) >= 4 and f[2] in (WIFI, WIRED)]


def connection(uuid):
    return next((c for c in connections() if c["uuid"] == uuid), None)


def saved():
    """Names of saved Wi-Fi connections."""
    return {c["name"] for c in connections() if c["type"] == WIFI}


@functools.lru_cache(maxsize=None)
def props(uuid):
    """Every setting of a saved connection: {"ipv4.method": "auto", …}."""
    out = {}
    for line in run("nmcli", "--terse", "connection", "show", "uuid", uuid).stdout.splitlines():
        key, _x, value = line.partition(":")
        out[key] = unescape(value)
    return out


def ssid_of(uuid):
    return props(uuid).get("802-11-wireless.ssid") or (connection(uuid) or {}).get("name", "")


def has_password(uuid):
    return props(uuid).get("802-11-wireless-security.key-mgmt") in ("wpa-psk", "sae")


def secret(uuid):
    """The saved Wi-Fi password, or None when NetworkManager does not give it."""
    try:
        res = run("nmcli", "--show-secrets", "--get-values", "802-11-wireless-security.psk",
                  "connection", "show", "uuid", uuid, timeout=20)
    except subprocess.TimeoutExpired:
        return None
    value = res.stdout.rstrip("\n")
    return value if res.returncode == 0 and value else None


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
        key, value = key.split("[", 1)[0], unescape(value)
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


# ---------------------------------------------------------------- settings of a connection

def mac_key(uuid):
    return f'{(connection(uuid) or {}).get("type", WIFI)}.cloned-mac-address'


def current(what, uuid):
    """The value of a setting in the terms of cycles()."""
    p = props(uuid)
    if what == "auto":
        return p.get("connection.autoconnect", "yes") == "yes"
    if what == "metered":
        return p.get("connection.metered", "") in ("yes", "guess-yes")
    if what == "mac":
        v = p.get(mac_key(uuid), "")
        return {"": "permanent", "preserve": "permanent", "stable-ssid": "stable"}.get(v, v)
    if what == "dot":
        v = (p.get("connection.dns-over-tls") or "default").split()[0]
        return {"-1": "no", "default": "no", "0": "no", "1": "opportunistic", "2": "yes"}.get(v, v)
    if what == "ip4m":
        return p.get("ipv4.method", "auto")
    if what == "ip6m":
        v = p.get("ipv6.method", "auto")
        return {"ignore": "disabled", "dhcp": "auto"}.get(v, v)
    return None


def label(what, value):
    return dict(cycles()[what]).get(value, value)


def servers(p, family):
    return [s for s in re.split(r"[,\s]+", p.get(f"{family}.dns", "")) if s]


def dns_choice(uuid):
    """("auto" | a key of DNS | "custom", servers)."""
    p = props(uuid)
    v4, v6 = servers(p, "ipv4"), servers(p, "ipv6")
    if not v4 and not v6:
        return "auto", []
    for key, _name, d4, _d6, _note in DNS:
        if v4 == d4:
            return key, v4
    return "custom", v4 + v6


def dns_label(uuid):
    choice, found = dns_choice(uuid)
    if choice == "auto":
        return _("automatic")
    if choice == "custom":
        return ", ".join(found)
    return next(name for key, name, *_rest in DNS if key == choice)


def modify(uuid, *pairs):
    """Change a saved connection; a connected one takes the change at once."""
    res = run("nmcli", "connection", "modify", "uuid", uuid, *pairs)
    if res.returncode != 0:
        notify(False, _("Could not change the settings"), last_line(res))
        clear_caches()
        return False
    dev = (connection(uuid) or {}).get("device")
    if dev:
        run("nmcli", "device", "reapply", dev)
    clear_caches()
    return True


def ipv6_on(uuid):
    return current("ip6m", uuid) != "disabled"


def set_dns(uuid, v4, v6):
    """Servers for this network; none means the ones the network hands out."""
    pairs = ["ipv4.dns", ",".join(v4), "ipv4.ignore-auto-dns", "yes" if v4 or v6 else "no"]
    if ipv6_on(uuid):
        # without servers of its own the network's IPv6 DNS would still answer
        pairs += ["ipv6.dns", ",".join(v6), "ipv6.ignore-auto-dns", "yes" if v4 or v6 else "no"]
    return modify(uuid, *pairs)


def step(what, uuid, delta):
    """Move a setting one value along with the arrows."""
    if what == "auto":
        modify(uuid, "connection.autoconnect", "no" if current("auto", uuid) else "yes")
        return
    if what == "metered":
        modify(uuid, "connection.metered", "no" if current("metered", uuid) else "yes")
        return
    values = [v for v, _label in cycles()[what]]
    now = current(what, uuid)
    new = values[(values.index(now) + delta) % len(values)] if now in values else values[0]
    if what == "mac":
        # a new address takes a new connection: the network reconnects in the background
        if modify(uuid, mac_key(uuid), new) and (connection(uuid) or {}).get("device"):
            spawn("activate", uuid)
    elif what == "dot":
        modify(uuid, "connection.dns-over-tls", new)
    elif what == "ip4m":
        if new == "auto":
            modify(uuid, "ipv4.method", "auto", "ipv4.addresses", "", "ipv4.gateway", "")
        else:
            # the address the network gave now is where a fixed one starts
            dev = (connection(uuid) or {}).get("device")
            found = dict(details(dev)) if dev else {}
            if "IPv4" in found:
                modify(uuid, "ipv4.method", "manual", "ipv4.addresses", found["IPv4"],
                       "ipv4.gateway", found.get(_("Gateway"), ""))
            else:
                return "prompt"
    elif what == "ip6m":
        pairs = ["ipv6.method", new]
        if new == "disabled":
            pairs += ["ipv6.dns", "", "ipv6.ignore-auto-dns", "no"]
        else:
            pairs += ["ipv6.ignore-auto-dns", props(uuid).get("ipv4.ignore-auto-dns", "no")]
        modify(uuid, *pairs)
    return None


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
    """The name tailscale status shows: the MagicDNS name, which can differ from the
    device's own host name (renamed in the admin console, or a "-1" for a twin)."""
    return (p.get("DNSName") or "").split(".")[0] or p.get("HostName") or "?"


def exit_node(ts):
    return next((p for _k, p in peers(ts) if p.get("ExitNode")), None)


# ---------------------------------------------------------------- background work and prompts

def busy():
    try:
        return BUSY.read_text().strip()
    except OSError:
        return ""


def spawn(*args):
    """Run "zen-network do ..." in the background: connecting takes seconds."""
    zen.detach(sys.executable, SELF, "do", *args)


def reopen(view):
    zen.detach(SELF, "open", view)


def last_line(res):
    lines = (res.stderr or "").strip().splitlines()
    return lines[-1] if lines else ""


def notify(ok, text, detail=""):
    args = ["notify-send", "-a", _("Network"), "-u", "normal" if ok else "critical", text]
    if detail:
        args.append(detail)
    run(*args)


def ask(prompt, message, password=False, value=""):
    """A one-line Rofi prompt; None when cancelled. A password is shown as dots."""
    cmd = ["rofi", "-dmenu", "-replace", "-p", prompt, "-mesg", html.escape(message),
           "-theme-str", 'listview { enabled: false; } entry { placeholder: ""; }']
    if password:
        cmd.append("-password")
    if value:
        cmd += ["-filter", value]
    res = subprocess.run(cmd, input="", capture_output=True, text=True)
    return res.stdout.rstrip("\n") if res.returncode == 0 else None


def wifi_connect(ssid, password, hidden=False):
    args = ["nmcli", "--ask", "device", "wifi", "connect", ssid] + (["hidden", "yes"] if hidden else [])
    if password:
        return subprocess.run(args, input=password + "\n", capture_output=True, text=True)
    return run(*[a for a in args if a != "--ask"])


def report(res, name):
    ok = res.returncode == 0
    notify(ok, (_("Connected: {}") if ok else _("Could not connect: {}")).format(name),
           "" if ok else last_line(res))


def qr_text(uuid, password):
    def q(text):
        return re.sub(r'([\\;,:"])', r"\\\1", text)
    hidden = "H:true;" if props(uuid).get("802-11-wireless.hidden") == "yes" else ""
    return f"WIFI:T:WPA;S:{q(ssid_of(uuid))};P:{q(password)};{hidden};"


def show_qr(uuid):
    password = secret(uuid)
    if password is None:
        notify(False, _("NetworkManager did not give the password"))
        return
    try:
        res = subprocess.run(["qrencode", "-t", "UTF8", "-m", "2"], input=qr_text(uuid, password),
                             capture_output=True, text=True)
    except FileNotFoundError:
        notify(False, _("The QR code needs the qrencode package"))
        return
    code = html.escape(res.stdout.rstrip("\n"))
    # the half blocks of two text lines meet at this line height: no gaps in the code
    text = (f'<span font="JetBrainsMono Nerd Font 9" line_height="0.85">{code}</span>\n\n'
            + html.escape(_("Point the phone camera at the code: {}").format(ssid_of(uuid))))
    subprocess.run(["rofi", "-e", text, "-markup", "-replace",
                    "-theme-str", "textbox { horizontal-align: 0.5; }"])


def change_password(uuid):
    name = ssid_of(uuid)
    password = ask(_("Password"), _("New password for {}").format(name), password=True)
    if not password:
        return
    # the editor reads the password from its standard input; the extra "yes"
    # answers its question about saving a network that connects by itself
    script = f"set 802-11-wireless-security.psk {password}\nsave persistent\nyes\nquit\n"
    subprocess.run(["nmcli", "connection", "edit", "uuid", uuid], input=script,
                   capture_output=True, text=True)
    clear_caches()
    ok = secret(uuid) == password
    notify(ok, _("Password changed: {}").format(name) if ok else _("Could not change the password"))
    if ok and (connection(uuid) or {}).get("device"):
        run("nmcli", "connection", "up", "uuid", uuid)


def custom_dns(uuid):
    choice, found = dns_choice(uuid)
    answer = ask("DNS", _("Servers separated by commas; empty means the network's own"),
                 value=", ".join(found) if choice == "custom" else "")
    if answer is None:
        return
    v4, v6 = [], []
    for item in re.split(r"[,\s]+", answer.strip()):
        if not item:
            continue
        try:
            ip = ipaddress.ip_address(item)
        except ValueError:
            notify(False, _("Not an address: {}").format(item))
            return
        (v6 if ip.version == 6 else v4).append(str(ip))
    set_dns(uuid, v4, v6)


def fixed_address(uuid, what):
    """Ask for the fixed IPv4 address or gateway."""
    p = props(uuid)
    if what == "address":
        answer = ask("IPv4", _("Address with the mask, e.g. 192.168.1.50/24"),
                     value=p.get("ipv4.addresses", "").split(",")[0])
        if not answer:
            return
        try:
            iface = ipaddress.IPv4Interface(answer.strip() if "/" in answer else answer.strip() + "/24")
        except ValueError:
            notify(False, _("Not an address: {}").format(answer))
            return
        gateway = p.get("ipv4.gateway") or str(next(iface.network.hosts()))
        modify(uuid, "ipv4.method", "manual", "ipv4.addresses", str(iface), "ipv4.gateway", gateway)
    else:
        answer = ask(_("Gateway"), _("The router's address, e.g. 192.168.1.1"),
                     value=p.get("ipv4.gateway", ""))
        if answer is None:
            return
        try:
            gateway = str(ipaddress.IPv4Address(answer.strip())) if answer.strip() else ""
        except ValueError:
            notify(False, _("Not an address: {}").format(answer))
            return
        modify(uuid, "ipv4.gateway", gateway)


def hidden_network():
    ssid = ask(_("Network"), _("Name of the hidden network"))
    if not ssid:
        return
    password = ask(_("Password"), _("Wi-Fi network {}; empty when it has none").format(ssid), password=True)
    if password is None:
        return
    BUSY.write_text(ssid)
    report(wifi_connect(ssid, password, hidden=True), ssid)


def worker(action, target):
    """Work that outlives the menu: connecting, and everything that asks."""
    back = None
    try:
        if action == "connect":
            if target in saved():
                BUSY.write_text(target)
                report(run("nmcli", "connection", "up", "id", target), target)
            else:
                net = next((n for n in networks() if n["ssid"] == target), None)
                password = ""
                if net and net["secure"]:
                    password = ask(_("Password"), _("Wi-Fi network {}").format(target), password=True)
                    if not password:
                        return 0
                BUSY.write_text(target)
                report(wifi_connect(target, password), target)
        elif action == "activate":
            name = (connection(target) or {}).get("name", target)
            BUSY.write_text(name)
            report(run("nmcli", "connection", "up", "uuid", target), name)
        elif action == "up":
            BUSY.write_text(target)
            report(run("nmcli", "device", "connect", target), target)
        elif action == "hidden":
            hidden_network()
        elif action == "qr":
            show_qr(target)
            back = f"pw:{target}"
        elif action == "psk":
            change_password(target)
            back = f"pw:{target}"
        elif action == "dns":
            custom_dns(target)
            back = f"dns:{target}"
        elif action in ("ip4addr", "ip4gw"):
            fixed_address(target, "address" if action == "ip4addr" else "gateway")
            back = f"ip4:{target}"
    finally:
        BUSY.unlink(missing_ok=True)
    if back:
        reopen(back)
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

    def setting(self, name, value, info, active=False):
        """A row the arrows change: "Name · ‹ value ›"."""
        self.add(f"{esc(name)} · {esc(arrows(value))}", info, active=active)

    def link(self, name, value, info):
        """A row that opens a view: "Name · value  ›"."""
        self.add(f"{esc(name)} · {esc(value)}  ›" if value else f"{esc(name)}  ›", info)

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
            menu.link(_("Networks"), "", "view:wifi")
        if any(c["type"] == WIFI for c in connections()):
            menu.link(_("Saved networks"), "", "view:saved")
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
    menu.add(esc(_("Hidden network…")), "hidden")
    menu.skip.add("hidden")
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
    if len(menu.rows) == 3:
        menu.add(esc(_("No networks found")), "none", passive=True)
    menu.print(focus)


def show_saved(focus):
    """Every saved Wi-Fi network, also the ones out of reach: its settings, or forget it."""
    menu = Menu("saved")
    menu.back()
    near = {n["ssid"] for n in networks()}
    items = [c for c in connections() if c["type"] == WIFI]
    items.sort(key=lambda c: (not c["device"], c["name"] not in near, c["name"].lower()))
    for c in items:
        state = _("connected") if c["device"] else _("in range") if c["name"] in near else ""
        menu.link(c["name"] if not state else f'{c["name"]} · {state}', "", f'view:conn:{c["uuid"]}')
    menu.print(focus)


def show_device(dev, focus):
    """Addresses of a connection; Enter on one copies it. Settings, Disconnect, Forget below."""
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
    for name, value in details(dev):
        menu.add(f"{esc(name)} · {esc(value)}", f"copy:{value.split('/')[0]}")
    if d[2] == "connected":
        if d[4]:
            menu.link(_("Settings"), "", f"view:conn:{d[4]}")
        menu.add(esc(_("Disconnect")), f"disconnect:{dev}")
        if d[1] == "wifi" and d[4]:
            menu.add(esc(_("Forget this network")), f"forget:{d[4]}")
    elif d[1] == "ethernet" and d[2] != "unavailable":
        menu.add(esc(_("Connect")), f"up:{dev}")
    menu.print(focus)


def show_conn(uuid, focus):
    """The settings of one saved network."""
    c = connection(uuid)
    if c is None:
        return show_main(None)
    menu = Menu(f"conn:{uuid}")
    menu.back(f"view:{parent(f'conn:{uuid}')[0]}")
    if not c["device"]:
        menu.add(esc(_("Connect")), f"activate:{uuid}")
    on = current("auto", uuid)
    menu.setting(_("Connect automatically"), _("on") if on else _("off"), f"adj:auto:{uuid}", active=on)
    metered = current("metered", uuid)
    menu.setting(_("Metered"), _("yes") if metered else _("no"), f"adj:metered:{uuid}")
    menu.setting(_("MAC address"), label("mac", current("mac", uuid)), f"adj:mac:{uuid}")
    if c["type"] == WIFI and has_password(uuid):
        menu.link(_("Password"), HIDDEN_PASSWORD, f"view:pw:{uuid}")
    menu.link("DNS", dns_label(uuid), f"view:dns:{uuid}")
    menu.setting(_("DNS over TLS"), label("dot", current("dot", uuid)), f"adj:dot:{uuid}")
    menu.link("IPv4", label("ip4m", current("ip4m", uuid)), f"view:ip4:{uuid}")
    menu.link("IPv6", label("ip6m", current("ip6m", uuid)), f"view:ip6:{uuid}")
    menu.add(esc(_("Forget this network")), f"forget:{uuid}")
    menu.print(focus)


def show_password(uuid, shown, focus):
    menu = Menu(f"{'pwshow' if shown else 'pw'}:{uuid}")
    menu.back(f"view:conn:{uuid}")
    value = secret(uuid) if shown else None
    if shown and value is None:
        notify(False, _("NetworkManager did not give the password"))
    text = esc(value) if value else HIDDEN_PASSWORD
    menu.add(f'{esc(_("Password"))} · {text}', f"reveal:{uuid}")
    menu.add(esc(_("Copy")), f"copypw:{uuid}")
    menu.add(esc(_("QR code for a phone")), f"qr:{uuid}")
    menu.add(esc(_("Change…")), f"psk:{uuid}")
    menu.print(focus)


def show_dns(uuid, focus):
    menu = Menu(f"dns:{uuid}")
    menu.back(f"view:conn:{uuid}")
    choice, found = dns_choice(uuid)
    menu.add(esc(_("Automatic · from the network")), f"dns:auto:{uuid}", active=choice == "auto")
    for key, name, v4, _v6, note in DNS:
        text = f"{name} · {v4[0]}" + (f" · {_(note)}" if note else "")
        menu.add(esc(text), f"dns:{key}:{uuid}", active=choice == key)
    custom = _("Your own…") if choice != "custom" else f'{_("Your own")} · {", ".join(found)}'
    menu.add(esc(custom), f"dns:custom:{uuid}", active=choice == "custom")
    menu.print(focus)


def show_ip(uuid, family, focus):
    menu = Menu(f"{family}:{uuid}")
    menu.back(f"view:conn:{uuid}")
    what = f"{family}m"
    menu.setting(_("Method"), label(what, current(what, uuid)), f"adj:{what}:{uuid}")
    p = props(uuid)
    if family == "ip4" and current("ip4m", uuid) == "manual":
        menu.link(_("Address"), p.get("ipv4.addresses", "").split(",")[0], f"ip4addr:{uuid}")
        menu.link(_("Gateway"), p.get("ipv4.gateway", ""), f"ip4gw:{uuid}")
    dev = (connection(uuid) or {}).get("device")
    if dev:
        prefix = "IPv4" if family == "ip4" else "IPv6"
        for name, value in details(dev):
            if name == prefix or (family == "ip4" and name == _("Gateway")):
                menu.add(f'{esc(_("Now"))} · {esc(name)} · {esc(value)}', f"copy:{value.split('/')[0]}")
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
    on = wifi_on()
    if kind == "wifi" and on:
        show_wifi(focus)
    elif kind == "saved":
        show_saved(focus)
    elif kind == "dev":
        show_device(rest, focus)
    elif kind == "conn":
        show_conn(rest, focus)
    elif kind in ("pw", "pwshow") and connection(rest):
        show_password(rest, kind == "pwshow", focus)
    elif kind == "dns" and connection(rest):
        show_dns(rest, focus)
    elif kind in ("ip4", "ip6") and connection(rest):
        show_ip(rest, kind, focus)
    elif kind == "ts" and ts_on(tailscale()):
        show_ts(focus)
    elif kind == "peer" and ts_on(tailscale()):
        show_peer(rest, focus)
    elif kind == "exit" and ts_on(tailscale()):
        show_exit(focus)
    else:
        show_main(focus)


def clear_caches():
    for f in (devices, wifi_on, networks, connections, props, tailscale):
        f.cache_clear()


def toggle_wifi():
    run("nmcli", "radio", "wifi", "off" if wifi_on() else "on")
    clear_caches()


def toggle_tailscale():
    res = run("tailscale", "down" if ts_on(tailscale()) else "up")
    if res.returncode != 0:
        notify(False, "Tailscale", last_line(res))
    clear_caches()


def copy(text, sensitive=False):
    # a password is marked sensitive: the clipboard history (cliphist) skips it
    subprocess.run(["wl-copy"] + (["--sensitive"] if sensitive else []), input=text, text=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def act(info, view, delta=1):
    """→ (view, focus); (None, None) closes the menu for a prompt."""
    kind, _x, rest = info.partition(":")
    if kind == "view":
        return rest, None
    if kind == "adj":
        what, _x, uuid = rest.partition(":")
        if what == "wifi":
            toggle_wifi()
        elif what == "ts":
            toggle_tailscale()
        elif step(what, uuid, delta) == "prompt":
            spawn("ip4addr", uuid)
            return None, None
        return view, info
    if kind == "rescan":
        # waits until the scan is done, then the list below reads the result
        run("nmcli", "--terse", "device", "wifi", "list", "--rescan", "yes")
        clear_caches()
        return view, info
    if kind == "hidden":
        spawn("hidden", "-")
        return None, None
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
    if kind == "activate":
        spawn("activate", rest)
        return view, info
    if kind == "copy":
        copy(rest)
        notify(True, _("Copied: {}").format(rest))
        return view, info
    if kind == "copypw":
        password = secret(rest)
        if password is None:
            notify(False, _("NetworkManager did not give the password"))
        else:
            copy(password, sensitive=True)
            notify(True, _("Password copied"))
        return view, info
    if kind == "reveal":
        return ("pw:" if view.startswith("pwshow:") else "pwshow:") + rest, info
    if kind in ("qr", "psk", "ip4addr", "ip4gw"):
        spawn(kind, rest)
        return None, None
    if kind == "dns":
        choice, _x, uuid = rest.partition(":")
        if choice == "custom":
            spawn("dns", uuid)
            return None, None
        preset = next((d for d in DNS if d[0] == choice), None)
        set_dns(uuid, preset[2] if preset else [], preset[3] if preset else [])
        return view, info
    if kind == "disconnect":
        run("nmcli", "device", "disconnect", rest)
        clear_caches()
        return "main", None
    if kind == "forget":
        run("nmcli", "connection", "delete", "uuid", rest)
        clear_caches()
        return ("saved" if view.startswith("conn:") else "main"), None
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
    """→ (view, focus) one step back; (None, None) on the first view."""
    kind, _x, rest = view.partition(":")
    if kind == "peer":
        return "ts", f"view:{view}"
    if kind == "conn":
        c = connection(rest)
        return (f"dev:{c['device']}" if c and c["device"] else "saved"), f"view:{view}"
    if kind in ("pw", "dns", "ip4", "ip6"):
        return f"conn:{rest}", f"view:{view}"
    if kind == "pwshow":
        return f"conn:{rest}", f"view:pw:{rest}"
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


def launch(view=None):
    if view is None:
        pid = our_rofi()
        if pid:
            run("kill", pid)
            sys.exit(0)
        if wifi_on():
            subprocess.Popen(["nmcli", "device", "wifi", "rescan"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    else:
        # read by the first step of the menu
        os.environ["ZEN_MENU_VIEW"] = view
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
    if cmd == "open" and len(sys.argv) == 3:
        launch(sys.argv[2])
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
    view = os.environ.get("ROFI_DATA") or (os.environ.get("ZEN_MENU_VIEW") if retv == INIT else "") or "main"
    focus = None
    if retv == ESC:
        view, focus = parent(view)
        if view is None:
            return 0
    elif retv in (LEFT, RIGHT):
        # the arrows change the setting under them, as in the sound menu
        focus = info
        if info.startswith("adj:"):
            view, focus = act(info, view, -1 if retv == LEFT else 1)
            if view is None:
                return 0
    elif retv == SELECT and info:
        view, focus = act(info, view)
        if view is None:
            return 0
    show(view, focus)
    return 0


if __name__ == "__main__":
    sys.exit(main())

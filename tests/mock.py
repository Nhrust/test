#!/usr/bin/env python3
"""Stand-ins for the programs the zen scripts call, for the tests.

The test suite links this file under each program's name into a bin folder
that comes first in PATH. The state lives in $ZEN_MOCK/state.json and every
call is appended to $ZEN_MOCK/calls.log as one line of arguments.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("ZEN_MOCK", "."))
STATE = ROOT / "state.json"
NAME = Path(sys.argv[0]).name
ARGS = sys.argv[1:]


def load():
    return json.loads(STATE.read_text())


def save(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))


def log():
    with open(ROOT / "calls.log", "a") as f:
        f.write(" ".join([NAME, *ARGS]) + "\n")


def makoctl(st):
    m = st["mako"]
    cmd = ARGS[0] if ARGS else ""
    if cmd == "mode":
        if ARGS[1:2] == ["-a"]:
            m["modes"] = sorted(set(m["modes"]) | {ARGS[2]})
        elif ARGS[1:2] == ["-r"]:
            m["modes"] = [x for x in m["modes"] if x != ARGS[2]] or ["default"]
        print("\n".join(m["modes"]))
    elif cmd == "set-mode":
        m["modes"] = ARGS[1:]
    elif cmd in ("list", "history"):
        print(json.dumps(m[cmd]))
    elif cmd == "dismiss":
        if "--all" in ARGS:
            gone = m["list"]
            m["list"] = []
        else:
            nid = int(ARGS[ARGS.index("-n") + 1])
            gone = [n for n in m["list"] if n["id"] == nid]
            m["list"] = [n for n in m["list"] if n["id"] != nid]
        if "--no-history" not in ARGS:
            m["history"] = gone + m["history"]
    elif cmd in ("invoke", "reload", "restore"):
        pass
    return 0


def wpctl(st):
    w = st["wp"]
    args = [a for a in ARGS]
    if args[:1] in (["-l"],):
        args = args[2:]
    cmd = args[0]
    rest = [a for a in args[1:]]
    if "-l" in rest:
        i = rest.index("-l")
        del rest[i:i + 2]
    target = rest[0] if rest else ""
    alias = {"@DEFAULT_AUDIO_SINK@": w["default_sink"], "@DEFAULT_AUDIO_SOURCE@": w["default_source"]}
    nid = str(alias.get(target, target))
    if cmd == "get-volume":
        if nid not in w["volume"]:
            print(f"Translator error: {nid}", file=sys.stderr)
            return 1
        vol, muted = w["volume"][nid]
        print(f"Volume: {vol:.2f}" + (" [MUTED]" if muted else ""))
    elif cmd == "set-volume":
        w["volume"][nid][0] = round(min(float(rest[1]), 1.0), 2)
    elif cmd == "set-mute":
        cur = w["volume"][nid][1]
        w["volume"][nid][1] = (not cur) if rest[1] == "toggle" else rest[1] == "1"
    elif cmd == "set-default":
        node = w["nodes"][nid]
        key = "default_sink" if node["media.class"] == "Audio/Sink" else "default_source"
        w[key] = int(nid)
    return 0


def pw_dump(st):
    w = st["wp"]
    objs = [{"id": int(i), "type": "PipeWire:Interface:Node", "info": {"props": p}}
            for i, p in w["nodes"].items()]
    meta = []
    for key, nid in (("default.audio.sink", w["default_sink"]), ("default.audio.source", w["default_source"])):
        meta.append({"subject": 0, "key": key, "type": "Spa:String:JSON",
                     "value": {"name": w["nodes"][str(nid)]["node.name"]}})
    objs.append({"id": 30, "type": "PipeWire:Interface:Metadata",
                 "props": {"metadata.name": "default"}, "metadata": meta})
    print(json.dumps(objs))
    return 0


def busctl(st):
    a = [x for x in ARGS if not x.startswith("--")]
    joined = " ".join(ARGS)
    if "org.bluez" in joined:
        bz = st.get("bluez")
        if bz is None:
            print("Unit bluetooth.service not found", file=sys.stderr)
            return 1
        if "GetManagedObjects" in joined:
            objs = {bz["adapter"]: {"org.bluez.Adapter1": {"Powered": {"type": "b", "data": bz["powered"]}}}}
            for d in bz["devices"]:
                objs[d["path"]] = {"org.bluez.Device1": {
                    "Alias": {"type": "s", "data": d["name"]}, "Paired": {"type": "b", "data": True},
                    "Connected": {"type": "b", "data": d["connected"]}, "Icon": {"type": "s", "data": d["icon"]}}}
            print(json.dumps({"type": "a{oa{sa{sv}}}", "data": [objs]}))
        elif a[0] == "set-property" and "Powered" in a:
            bz["powered"] = a[-1] == "true"
        elif a[0] == "call" and a[-1] in ("Connect", "Disconnect"):
            for d in bz["devices"]:
                if d["path"] == a[2]:
                    d["connected"] = a[-1] == "Connect"
        return 0
    up = st["upower"]
    if "EnumerateDevices" in joined:
        print('ao 2 "/org/freedesktop/UPower/devices/line_power_ACAD" '
              '"/org/freedesktop/UPower/devices/battery_BAT0"')
    elif a[0] == "get-property":
        prop = a[-1]
        if prop == "ActiveProfile":
            print(f's "{up["profile"]}"')
        elif prop in up:
            v = up[prop]
            print(f"b {'true' if v else 'false'}" if isinstance(v, bool) else f"u {v}")
        else:
            return 1
    elif a[0] == "call" and "EnableChargeThreshold" in a:
        up["ChargeThresholdEnabled"] = a[-1] == "true"
    elif a[0] == "set-property":
        prop = a[-3] if a[-2] in ("s", "b", "u") else a[-2]
        kind, value = a[-2], a[-1]
        up["profile" if prop == "ActiveProfile" else prop] = (
            value == "true" if kind == "b" else int(value) if kind == "u" else value)
    return 0


def cliphist(st):
    c = st["clip"]
    cmd = ARGS[0]
    if cmd == "list":
        for cid in sorted(c, key=int, reverse=True):
            print(f"{cid}\t{' '.join(c[cid].split())}")
    elif cmd == "decode":
        sys.stdout.write(c[ARGS[1]])
    elif cmd == "delete":
        cid = sys.stdin.read().split("\t")[0]
        c.pop(cid, None)
    elif cmd == "wipe":
        c.clear()
    elif cmd == "store":
        data = sys.stdin.read()
        for k in [k for k, v in c.items() if v == data]:
            del c[k]
        c[str(max([int(k) for k in c] + [0]) + 1)] = data
    return 0


def niri(st):
    n = st["niri"]
    if ARGS[:3] == ["msg", "--json", "outputs"]:
        print(json.dumps(n["outputs"]))
    elif ARGS[:3] == ["msg", "--json", "windows"]:
        print(json.dumps(n["windows"]))
    elif ARGS[:3] == ["msg", "--json", "keyboard-layouts"]:
        print(json.dumps({"names": ["English (US)", "Russian"], "current_idx": 0}))
    return 0


def systemctl(st):
    active = st["systemd"]["active"]
    a = [x for x in ARGS if not x.startswith("--")]
    if a[0] == "is-active":
        print("active" if a[1] in active else "inactive")
        return 0 if a[1] in active else 3
    if a[1:2] == ["zen-hotspot.service"] and a[0] in ("start", "stop"):
        if a[1] in st["systemd"].get("deny", []):
            print("Failed to start zen-hotspot.service: Access denied", file=sys.stderr)
            return 1
        devs = st["nm"]["devices"]
        devs[:] = [d for d in devs if d[0] != "ap0"] + ([["ap0", "wifi"]] if a[0] == "start" else [])
        if a[0] == "stop":
            for c in st["nm"]["conns"]:
                if c["device"] == "ap0":
                    c["device"] = ""
        return 0
    if a[0] == "start":
        if a[1] == "zen-caffeine.service":
            active[:] = [u for u in active if u != "zen-idle.service"] + [a[1]]
        elif a[1] == "zen-idle.service":
            active[:] = [u for u in active if u != "zen-caffeine.service"] + [a[1]]
    return 0


def brightnessctl(st):
    if any(a.startswith("--device=") and "kbd" in a for a in ARGS):
        kbd = st.setdefault("kbd", {"level": 1, "saved": None})
        if "--save" in ARGS:
            kbd["saved"] = kbd["level"]
        if "set" in ARGS:
            kbd["level"] = int(ARGS[-1])
        if "--restore" in ARGS and kbd["saved"] is not None:
            kbd["level"] = kbd["saved"]
        return 0
    if "-m" in ARGS:
        print(f"amdgpu_bl1,backlight,{st['brightness'] * 255 // 100},{st['brightness']}%,255")
    elif "set" in ARGS:
        st["brightness"] = int(ARGS[-1].rstrip("%"))
    return 0


def playerctl(st):
    p = st.get("player")
    if not p:
        print("No players found", file=sys.stderr)
        return 1
    cmd = ARGS[0]
    if cmd == "metadata":
        fmt = ARGS[ARGS.index("--format") + 1]
        out = fmt
        for key, value in (("status", p["status"]), ("artist", p["artist"]),
                           ("title", f'Song {p["track"]}'), ("playerName", p["name"])):
            out = out.replace("{{%s}}" % key, value)
        print(out)
    elif cmd == "play-pause":
        p["status"] = "Paused" if p["status"] == "Playing" else "Playing"
    elif cmd == "next":
        p["track"] += 1
    elif cmd == "previous":
        p["track"] = max(1, p["track"] - 1)
    return 0


def gtklock(st):
    print("gtklock v5.0.0")
    return 0


def pacman(st):
    if ARGS[:1] == ["-Q"]:
        print(f"{ARGS[1]} 5.0.1-1")
    return 0


def sudo(st):
    args = ARGS
    while args and args[0].startswith("-"):
        args = args[1:]
    return subprocess.run(args).returncode if args else 0


def notify_send(st):
    if "-A" in ARGS and st.get("notify_action"):
        print(st["notify_action"])
    return 0


WIFI, WIRED = "802-11-wireless", "802-3-ethernet"


def nmcli(st):
    """NetworkManager: nm.devices [[name, kind]], nm.conns (saved connections with
    their props and psk), nm.aps (visible networks), nm.ip (addresses per device)."""
    nm = st.get("nm")
    if nm is None:
        return 0
    a, getv, i = [], None, 0
    while i < len(ARGS):
        x = ARGS[i]
        if x in ("--terse", "-t", "--ask", "--show-secrets", "-s"):
            i += 1
        elif x in ("--fields", "-f", "--get-values", "-g"):
            if x in ("--get-values", "-g"):
                getv = ARGS[i + 1]
            i += 2
        else:
            a.append(x)
            i += 1
    conns = nm["conns"]

    def esc(v):
        return str(v).replace("\\", "\\\\").replace(":", "\\:")

    def find(how, value):
        key = "uuid" if how == "uuid" else "name"
        return next((c for c in conns if c[key] == value), None)

    def dev_of(kind):
        return next((d[0] for d in nm["devices"] if d[1] == kind), None)

    def activate(c):
        dev = c.get("ifname") or dev_of("wifi" if c["type"] == WIFI else "ethernet")
        if c.get("ifname") and dev not in [d[0] for d in nm["devices"]]:
            print(f"Error: Connection activation failed: device {dev} not available", file=sys.stderr)
            return 4
        for o in conns:
            if o["device"] == dev:
                o["device"] = ""
        c["device"] = dev
        return 0

    def active_ssid():
        c = next((c for c in conns if c["type"] == WIFI and c["device"] and not c.get("ifname")), None)
        return c["props"]["802-11-wireless.ssid"] if c else None

    if a == ["device"]:
        for name, kind in nm["devices"]:
            c = next((c for c in conns if c["device"] == name), None)
            if c:
                state = "connected"
            elif kind == "wifi":
                state = "disconnected" if nm["wifi"] else "unavailable"
            else:
                state = "disconnected" if nm.get("cable") else "unavailable"
            print(":".join(esc(x) for x in (name, kind, state, c["name"] if c else "", c["uuid"] if c else "")))
    elif a[:2] == ["radio", "wifi"]:
        if a[2:]:
            nm["wifi"] = a[2] == "on"
            if not nm["wifi"]:
                for c in conns:
                    if c["type"] == WIFI:
                        c["device"] = ""
        else:
            print("enabled" if nm["wifi"] else "disabled")
    elif a[:3] == ["device", "wifi", "list"]:
        if "yes" in a:
            nm["scans"] = nm.get("scans", 0) + 1
        now = active_ssid()
        for ap in nm["aps"] if nm["wifi"] else []:
            print(":".join(esc(x) for x in ("*" if ap["ssid"] == now else " ", ap["ssid"],
                                             ap["signal"], ap["security"], ap["freq"], ap["chan"])))
    elif a[:3] == ["device", "wifi", "rescan"]:
        pass
    elif a == ["connection", "show"]:
        for c in conns:
            print(":".join(esc(x) for x in (c["name"], c["uuid"], c["type"], c["device"])))
        print("lo:0000-lo:loopback:lo")
    elif a[:3] == ["connection", "show", "uuid"]:
        c = find("uuid", a[3])
        if c is None:
            print(f"Error: {a[3]} - no such connection profile.", file=sys.stderr)
            return 10
        if getv:
            print(c.get("psk", "") if "psk" in getv else c["props"].get(getv, ""))
        else:
            for key, value in [("connection.id", c["name"]), ("connection.uuid", c["uuid"]),
                               ("connection.type", c["type"])] + list(c["props"].items()):
                print(f"{key}:{esc(value)}")
    elif a[:3] == ["connection", "modify", "uuid"]:
        c = find("uuid", a[3])
        pairs = a[4:]
        for key, value in zip(pairs[::2], pairs[1::2]):
            if key in nm.get("refuse", []):
                print(f"Error: failed to modify {key}: invalid value", file=sys.stderr)
                return 2
            c["props"][key] = value
    elif a[:2] == ["connection", "edit"]:
        c = find(a[2], a[3])
        for line in sys.stdin.read().splitlines():
            parts = line.split(" ", 2)
            if parts[0] == "set" and len(parts) == 3:
                if parts[1].endswith(".psk"):
                    c["psk"] = parts[2]
                else:
                    c["props"][parts[1]] = parts[2]
    elif a[:2] == ["connection", "up"]:
        c = find(a[2], a[3])
        if c is None:
            return 10
        return activate(c)
    elif a[:2] == ["connection", "down"]:
        c = find(a[2], a[3])
        if c:
            c["device"] = ""
    elif a[:3] == ["connection", "add", "type"]:
        opts = dict(zip(a[4::2], a[5::2]))
        c = new_conn(f"u-{opts['con-name']}", opts["con-name"], WIFI, secure=False)
        c["ifname"] = opts.get("ifname", "")
        c["props"]["802-11-wireless.ssid"] = opts.get("ssid", "")
        for key in ("802-11-wireless.mode", "ipv4.method", "ipv6.method"):
            if key in opts:
                c["props"][key] = opts[key]
        c["props"]["connection.autoconnect"] = opts.get("autoconnect", "yes")
        conns.append(c)
    elif a[:2] == ["connection", "delete"]:
        nm["conns"] = [c for c in conns if c["uuid" if a[2] == "uuid" else "name"] != a[3]]
    elif a[:2] == ["device", "reapply"]:
        pass
    elif a[:2] == ["device", "show"]:
        for key, values in nm["ip"].get(a[2], {}).items():
            for n, v in enumerate(values, 1):
                print(f"{key}[{n}]:{esc(v)}")
    elif a[:3] == ["device", "wifi", "connect"]:
        ssid = a[3]
        want = nm["passwords"].get(ssid)
        given = sys.stdin.read().strip() if "--ask" in ARGS else ""
        if want is not None and given != want:
            print("Error: Connection activation failed: Secrets were required, but not provided.",
                  file=sys.stderr)
            return 4
        c = next((c for c in conns if c["props"].get("802-11-wireless.ssid") == ssid), None)
        if c is None:
            c = new_conn(ssid, ssid, WIFI, secure=want is not None, psk=given)
            if "hidden" in a:
                c["props"]["802-11-wireless.hidden"] = "yes"
            conns.append(c)
        activate(c)
    elif a[:2] == ["device", "disconnect"]:
        for c in conns:
            if c["device"] == a[2]:
                c["device"] = ""
    elif a[:2] == ["device", "connect"]:
        c = next((c for c in conns if c["type"] == WIRED), None)
        if c and nm.get("cable"):
            activate(c)
    return 0


def new_conn(uuid, name, kind, secure=True, psk="", device=""):
    """A saved connection the way nmcli shows its settings."""
    props = {"connection.autoconnect": "yes", "connection.metered": "unknown",
             "connection.dns-over-tls": "-1 (default)",
             "ipv4.method": "auto", "ipv4.addresses": "", "ipv4.gateway": "", "ipv4.dns": "",
             "ipv4.ignore-auto-dns": "no", "ipv6.method": "auto", "ipv6.dns": "", "ipv6.ignore-auto-dns": "no"}
    if kind == WIFI:
        props.update({"802-11-wireless.ssid": name, "802-11-wireless.cloned-mac-address": "",
                      "802-11-wireless.hidden": "no"})
        if secure:
            props["802-11-wireless-security.key-mgmt"] = "wpa-psk"
    else:
        props["802-3-ethernet.cloned-mac-address"] = ""
    return {"uuid": uuid, "name": name, "type": kind, "device": device, "props": props, "psk": psk}


def qrencode(st):
    data = sys.stdin.read()
    with open(ROOT / "qr.txt", "w") as f:
        f.write(data)
    print("█▀▀█\n█▄▄█")
    return 0


def tailscale(st):
    ts = st.get("tailscale")
    if ts is None:
        print("tailscale: command not found", file=sys.stderr)
        return 127
    if ARGS[:2] == ["status", "--json"]:
        print(json.dumps(ts))
    elif ARGS == ["up"]:
        ts["BackendState"] = "Running"
    elif ARGS == ["down"]:
        ts["BackendState"] = "Stopped"
    elif ARGS[:1] == ["set"] and ARGS[1].startswith("--exit-node="):
        ip = ARGS[1].split("=", 1)[1]
        for p in ts["Peer"].values():
            p["ExitNode"] = bool(ip) and ip in p["TailscaleIPs"]
    return 0


def rofi(st):
    """rofi -dmenu answers with what the test put in "rofi_input"; null is Escape."""
    if os.environ.get("ROFI_OUTSIDE"):
        # as the real one does while the menu that started the caller is open
        print("Do not launch rofi from inside rofi.")
        return 1
    if "-dmenu" in ARGS:
        sys.stdin.read()
        answer = st.get("rofi_input")
        if isinstance(answer, list):
            # one answer per prompt, in order
            answer = answer.pop(0) if answer else None
        if answer is None:
            return 1
        print(answer)
    return 0


def pgrep(st):
    return 1


def passive(st):
    return 0


HANDLERS = {
    "makoctl": makoctl, "wpctl": wpctl, "pw-dump": pw_dump, "busctl": busctl, "cliphist": cliphist,
    "niri": niri, "systemctl": systemctl, "brightnessctl": brightnessctl, "sudo": sudo,
    "playerctl": playerctl, "pgrep": pgrep, "notify-send": notify_send, "gtklock": gtklock, "pacman": pacman,
    "nmcli": nmcli, "tailscale": tailscale, "rofi": rofi, "qrencode": qrencode,
}


def main():
    log()
    st = load()
    before = json.dumps(st, sort_keys=True)
    if NAME in ("wl-copy",):
        (ROOT / "clipboard.txt").write_text(sys.stdin.read())
    rc = HANDLERS.get(NAME, passive)(st)
    # only calls that change something write, so a read running at the same
    # time as a background change cannot undo it
    if NAME != "sudo" and json.dumps(st, sort_keys=True) != before:
        save(st)
    return rc


if __name__ == "__main__":
    sys.exit(main())

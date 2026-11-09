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

ROOT = Path(os.environ["ZEN_MOCK"])
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


def pgrep(st):
    return 1


def passive(st):
    return 0


HANDLERS = {
    "makoctl": makoctl, "wpctl": wpctl, "pw-dump": pw_dump, "busctl": busctl, "cliphist": cliphist,
    "niri": niri, "systemctl": systemctl, "brightnessctl": brightnessctl, "sudo": sudo,
    "playerctl": playerctl, "pgrep": pgrep, "notify-send": notify_send, "gtklock": gtklock, "pacman": pacman,
}


def main():
    log()
    st = load()
    before = json.dumps(st, sort_keys=True)
    if NAME in ("wl-copy",):
        sys.stdin.read()
    rc = HANDLERS.get(NAME, passive)(st)
    # only calls that change something write, so a read running at the same
    # time as a background change cannot undo it
    if NAME != "sudo" and json.dumps(st, sort_keys=True) != before:
        save(st)
    return rc


if __name__ == "__main__":
    sys.exit(main())

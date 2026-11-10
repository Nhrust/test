"""zen-vitals — what the monitoring part of the panel shows, and in what order.

  zen-vitals         open the menu (right click on any monitoring module)

Up to six modules from the list below; Enter or the arrows switch one on or
off, Alt+Up and Alt+Down move it. The choice is the line "vitals =" in the
[panel] section of ~/.config/zen/zen.conf, written at each step; when the menu
closes, "zen apply" turns it into waybar/zen-vitals.jsonc (the modules) and
waybar/zen-vitals.css (their separators), and the panel reloads once.
"""
import html
import json
import os
import re
import subprocess
import sys
from glob import glob
from pathlib import Path

import zen
from zen import _, run

SELF = os.path.realpath(sys.argv[0])
THEME = zen.CONFIG_HOME / "rofi/vitals.rasi"
MAX = 6
DEFAULT = "cpu, gpu, memory, temp, speed"
BAR = "~/.local/lib/zen/bar"

INIT, SELECT, ESC, LEFT, RIGHT, UP, DOWN = 0, 1, 12, 13, 14, 15, 16


def hwmon(*names):
    return any(Path(h, "name").is_file() and Path(h, "name").read_text().strip() in names
               for h in glob("/sys/class/hwmon/hwmon*"))


def battery():
    return any(Path(b, "type").read_text().strip() == "Battery"
               for b in glob("/sys/class/power_supply/*") if Path(b, "type").is_file())


CPU_SENSORS = ("k10temp", "zenpower", "coretemp", "cpu_thermal")
GPU_SENSORS = ("amdgpu", "radeon", "nouveau", "xe", "i915")


def catalog():
    """key → (group, name, Waybar module, its settings, is there a sensor for it)."""
    def custom(script, fmt=None, interval=None):
        out = {"exec": f"{BAR}/{script}"}
        if fmt:
            out["format"] = fmt
        if interval:
            out["interval"] = interval
        return out

    return {
        "cpu": (_("Processor"), _("load"), "cpu", {"format": "󰍛 {usage:>3}%", "interval": 2}, True),
        "cpufreq": (_("Processor"), _("frequency"), "cpu#freq",
                    {"format": "󰍛 {avg_frequency} " + _("GHz"), "interval": 2}, True),
        "load": (_("Processor"), _("load average, 1 minute"), "cpu#load",
                 {"format": "󰊚 {load}", "interval": 5}, True),
        "gpu": (_("Video card"), _("load"), "custom/gpu", custom("gpu"),
                bool(glob("/sys/class/drm/card*/device/gpu_busy_percent"))),
        "vram": (_("Video card"), _("video memory"), "custom/vram", custom("vram", "󰢮 {}", 5),
                 bool(glob("/sys/class/drm/card*/device/mem_info_vram_used"))),
        "memory": (_("Memory"), _("used"), "memory", {"format": "\uefc5 {used:>4.1f}G", "interval": 5}, True),
        "mempct": (_("Memory"), _("used, percent"), "memory#percent",
                   {"format": "\uefc5 {percentage:>2}%", "interval": 5}, True),
        "swap": (_("Memory"), _("swap"), "memory#swap", {"format": "󰾴 {swapUsed:.1f}G", "interval": 5}, True),
        "temp": (_("Temperature"), _("average of the sensors"), "custom/temp", custom("temp", "󰔏 {}", 5), True),
        "tempcpu": (_("Temperature"), _("processor"), "custom/temp-cpu",
                    custom("temp cpu", "󰔏 CPU {}", 5), hwmon(*CPU_SENSORS)),
        "tempgpu": (_("Temperature"), _("video card"), "custom/temp-gpu",
                    custom("temp gpu", "󰔏 GPU {}", 5), hwmon(*GPU_SENSORS)),
        "tempnvme": (_("Temperature"), "NVMe", "custom/temp-nvme",
                     custom("temp nvme", "󰔏 NVMe {}", 5), hwmon("nvme")),
        "fan": (_("Fan"), _("speed, rpm"), "custom/fan", custom("fan", "\U000F0210 {} " + _("rpm"), 5),
                bool(glob("/sys/class/hwmon/hwmon*/fan*_input"))),
        "speed": (_("Network"), _("download"), "custom/speed", custom("speed", "󰓢 {}"), True),
        "upload": (_("Network"), _("upload"), "custom/upload", custom("speed up", "󰕒 {}"), True),
        "disk": (_("Disk"), _("free on /"), "disk", {"format": "󰋊 {free}", "path": "/", "interval": 60}, True),
        "diskio": (_("Disk"), _("read and write"), "custom/diskio", custom("diskio", "󰋊 {}"), True),
        "power": (_("Battery"), _("power, watts"), "custom/power", custom("power", "󰂄 {}", 5), battery()),
        "uptime": (_("System"), _("uptime"), "custom/uptime", custom("uptime", "󰔟 {}", 60), True),
    }


def chosen():
    """The keys from zen.conf that exist, at most six, in their order."""
    known = catalog()
    raw = zen.settings().get("panel", "vitals", fallback=DEFAULT)
    out = []
    for key in (k.strip() for k in raw.split(",")):
        if key in known and key not in out and len(out) < MAX:
            out.append(key)
    return out


def save(keys):
    """Write "vitals = …" into [panel] of zen.conf, the rest of the file as it is."""
    line = f"vitals = {', '.join(keys)}"
    try:
        text = zen.CONFIG.read_text(encoding="utf-8")
    except OSError:
        text = ""
    if re.search(r"(?m)^\[panel\]\s*$", text):
        start = re.search(r"(?m)^\[panel\]\s*$", text).end()
        nxt = re.search(r"(?m)^\[", text[start:])
        end = start + nxt.start() if nxt else len(text)
        body = text[start:end]
        if re.search(r"(?m)^vitals\s*=.*$", body):
            body = re.sub(r"(?m)^vitals\s*=.*$", line, body, count=1)
        else:
            body = body.rstrip("\n") + "\n" + line + "\n" + ("\n" if nxt else "")
        text = text[:start] + body + text[end:]
    else:
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + \
            "[panel]\n# Monitoring modules on the panel, in order (right click on one to change)\n" + line + "\n"
    zen.CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = zen.CONFIG.with_name(zen.CONFIG.name + ".zen-new")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, zen.CONFIG)
    zen.settings.cache_clear()


# ---------------------------------------------------------------- Waybar files

def css_id(module):
    """cpu#freq → #cpu.freq, custom/temp-cpu → #custom-temp-cpu."""
    name, _sep, cls = module.partition("#")
    return "#" + name.replace("/", "-") + (f".{cls}" if cls else "")


def generated():
    """(path, text) of the panel files that follow the choice in zen.conf."""
    items = catalog()
    keys = chosen()
    modules = [items[k][2] for k in keys]
    config = {"modules-left": ["custom/apps", "niri/workspaces", "custom/gap-l1", *modules, "custom/gap-l2"]}
    for k in keys:
        settings = dict(items[k][3], **{"on-click": "foot btop", "on-click-right": "~/.local/bin/zen-vitals",
                                        "tooltip": False})
        config[items[k][2]] = settings
    head = "// Made by zen apply from [panel] vitals in ~/.config/zen/zen.conf; edits here are lost.\n"
    css = ["/* Made by zen apply from [panel] vitals in zen.conf. */"]
    if modules:
        css += [",\n".join(css_id(m) for m in modules) + " {", "    padding: 0 10px;", "    color: @zen_fg;", "}"]
    if len(modules) > 1:
        css += [",\n".join(css_id(m) for m in modules[1:]) + " {",
                "    border-left: 1px solid @zen_line;", "}"]
    yield zen.CONFIG_HOME / "waybar/zen-vitals.jsonc", head + json.dumps(config, ensure_ascii=False, indent=4) + "\n"
    yield zen.CONFIG_HOME / "waybar/zen-vitals.css", "\n".join(css) + "\n"


# ---------------------------------------------------------------- menu

def esc(text):
    return html.escape(str(text))


def option(key, value):
    sys.stdout.write(f"\0{key}\x1f{value}\n")


def icon(key):
    """The glyph a module starts with; the GPU script prints its own."""
    fmt = catalog()[key][3].get("format", "")
    return fmt.split(" ")[0] if fmt else "\U000F08AE"


def header(keys):
    muted = zen.palette()["muted"]
    icons = esc(_("On the panel")) + ":  " + (" · ".join(icon(k) for k in keys) or esc(_("nothing")))
    count = esc(_("{} of {}").format(len(keys), MAX))
    hint = esc(_("Enter switches · Alt+↑↓ moves"))
    return f'{icons}   <span foreground="{muted}">{count}</span>\u2028<span foreground="{muted}">{hint}</span>'


def show(focus=None):
    """On the panel, in order; below it what can be added, by group."""
    items = catalog()
    keys = chosen()
    def title(text):
        # no colour of its own: dimmed, it stays readable on the highlight too
        return (f'<span alpha="60%"><b>{esc(text)}</b></span>', "none", False, True)

    rows = []
    for k in keys:
        group, name = items[k][0], items[k][1]
        rows.append((f"\u2003{esc(group)}: {esc(name)} · {esc('‹ ' + _('on') + ' ›')}", f"key:{k}", True, False))
    groups = {}
    for k, (group, name, _m, _s, present) in items.items():
        if k not in keys and present:
            groups.setdefault(group, []).append((k, name))
    for group, members in groups.items():
        rows.append(title(group))
        for k, name in members:
            rows.append((f"\u2003{esc(name)} · {esc('‹ ' + _('off') + ' ›')}", f"key:{k}", False, False))
    rows.append(title(""))
    rows.append((esc(_("As it was")), "reset", False, False))
    option("prompt", _("panel"))
    option("message", header(keys))
    option("data", "main")
    option("markup-rows", "true")
    option("no-custom", "true")
    option("use-hot-keys", "true")
    option("keep-selection", "true")
    infos = [r[1] for r in rows]
    if focus not in infos:
        focus = next((r[1] for r in rows if not r[3]), None)
    option("new-selection", str(infos.index(focus) if focus in infos else 0))
    for text, info, active, passive in rows:
        extra = ("\x1factive\x1ftrue" if active else "") + ("\x1fnonselectable\x1ftrue" if passive else "")
        sys.stdout.write(f"{text}\0info\x1f{info}{extra}\n")


def apply_now():
    """Make the panel files from zen.conf; apply reloads the panel when they change."""
    subprocess.run([str(Path.home() / ".local/lib/zen/apply"), "--user"],
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def act(retv, info):
    keys = chosen()
    if info == "reset":
        save([k.strip() for k in DEFAULT.split(",")])
        return info
    key = info.partition(":")[2]
    if not key:
        return info
    if retv in (SELECT, LEFT, RIGHT):
        if key in keys:
            keys.remove(key)
        elif len(keys) < MAX:
            keys.append(key)
        else:
            return info
    elif retv in (UP, DOWN) and key in keys:
        i = keys.index(key)
        j = i - 1 if retv == UP else i + 1
        if not 0 <= j < len(keys):
            return info
        keys[i], keys[j] = keys[j], keys[i]
    else:
        return info
    save(keys)
    return info


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
    mode = _("panel")
    cmd = ["rofi", "-show", mode, "-modes", f"{mode}:{SELF} list", "-replace", "-no-show-icons",
           "-kb-cancel", "Escape,Control+g,Control+bracketleft",
           "-kb-move-char-back", "Control+b", "-kb-move-char-forward", "Control+f",
           "-kb-custom-4", "Left", "-kb-custom-5", "Right",
           "-kb-custom-6", "Alt+Up", "-kb-custom-7", "Alt+Down"]
    if THEME.exists():
        cmd += ["-theme", str(THEME)]
    cmd += zen.switch_args({4, 5, 6, 7})
    # the panel reloads once, when the menu closes: a reload at every step would
    # blink the panel each time
    before = chosen()
    subprocess.run(cmd)
    zen.settings.cache_clear()
    if chosen() != before:
        apply_now()
    sys.exit(0)


def main():
    if len(sys.argv) < 2:
        launch()
    if sys.argv[1] != "list":
        sys.exit(__doc__)
    retv = int(os.environ.get("ROFI_RETV", "0"))
    if zen.switch(retv, "zen-vitals"):
        return 0
    info = os.environ.get("ROFI_INFO", "")
    focus = act(retv, info) if retv != INIT and info else None
    show(focus)
    return 0


if __name__ == "__main__":
    sys.exit(main())

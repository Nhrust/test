"""zen-power — power profiles, charge limit and power actions as Rofi tiles."""
import os
import sys
from pathlib import Path

import zen
from zen import _, run

THEME = zen.CONFIG_HOME / "rofi/power.rasi"
SELF = os.path.realpath(sys.argv[0])
ICON_COLOR = zen.palette()["fg"]
ICONS = zen.RUNTIME / ("zen-power-" + ICON_COLOR.lstrip("#"))

PATHS = {
    "power-saver": "M12 16C13.66 16 15 14.66 15 13C15 11.88 14.39 10.9 13.5 10.39L3.79 4.77L9.32 14.35C9.82 15.33 10.83 16 12 16M12 3C10.19 3 8.5 3.5 7.03 4.32L9.13 5.53C10 5.19 11 5 12 5C16.42 5 20 8.58 20 13C20 15.21 19.11 17.21 17.66 18.65H17.65C17.26 19.04 17.26 19.67 17.65 20.06C18.04 20.45 18.68 20.45 19.07 20.07C20.88 18.26 22 15.76 22 13C22 7.5 17.5 3 12 3M2 13C2 15.76 3.12 18.26 4.93 20.07C5.32 20.45 5.95 20.45 6.34 20.06C6.73 19.67 6.73 19.04 6.34 18.65C4.89 17.2 4 15.21 4 13C4 12 4.19 11 4.54 10.1L3.33 8C2.5 9.5 2 11.18 2 13Z",
    "balanced": "M12 1.38L9.14 12.06C8.8 13.1 9.04 14.29 9.86 15.12C11.04 16.29 12.94 16.29 14.11 15.12C14.9 14.33 15.16 13.2 14.89 12.21M14.6 3.35L15.22 5.68C18.04 6.92 20 9.73 20 13C20 15.21 19.11 17.21 17.66 18.65H17.65C17.26 19.04 17.26 19.67 17.65 20.06C18.04 20.45 18.68 20.45 19.07 20.07C20.88 18.26 22 15.76 22 13C22 8.38 18.86 4.5 14.6 3.35M9.4 3.36C5.15 4.5 2 8.4 2 13C2 15.76 3.12 18.26 4.93 20.07C5.32 20.45 5.95 20.45 6.34 20.06C6.73 19.67 6.73 19.04 6.34 18.65C4.89 17.2 4 15.21 4 13C4 9.65 5.94 6.86 8.79 5.65",
    "performance": "M12,16A3,3 0 0,1 9,13C9,11.88 9.61,10.9 10.5,10.39L20.21,4.77L14.68,14.35C14.18,15.33 13.17,16 12,16M12,3C13.81,3 15.5,3.5 16.97,4.32L14.87,5.53C14,5.19 13,5 12,5A8,8 0 0,0 4,13C4,15.21 4.89,17.21 6.34,18.65H6.35C6.74,19.04 6.74,19.67 6.35,20.06C5.96,20.45 5.32,20.45 4.93,20.07V20.07C3.12,18.26 2,15.76 2,13A10,10 0 0,1 12,3M22,13C22,15.76 20.88,18.26 19.07,20.07V20.07C18.68,20.45 18.05,20.45 17.66,20.06C17.27,19.67 17.27,19.04 17.66,18.65V18.65C19.11,17.2 20,15.21 20,13C20,12 19.81,11 19.46,10.1L20.67,8C21.5,9.5 22,11.18 22,13Z",
    "charge": "M16.67 4H15V2H9V4H7.33A1.34 1.34 0 0 0 6 5.33V20.67A1.34 1.34 0 0 0 7.33 22H16.67A1.34 1.34 0 0 0 18 20.67V5.33A1.34 1.34 0 0 0 16.67 4M12.58 15.64L12 16.17L11.42 15.64C9.36 13.77 8 12.54 8 11A2.18 2.18 0 0 1 10.2 8.8A2.4 2.4 0 0 1 12 9.63A2.4 2.4 0 0 1 13.8 8.8A2.18 2.18 0 0 1 16 11C16 12.54 14.64 13.77 12.58 15.64Z",
    "hibernate": "M18.73,18C15.4,21.69 9.71,22 6,18.64C2.33,15.31 2.04,9.62 5.37,5.93C6.9,4.25 9,3.2 11.27,3C7.96,6.7 8.27,12.39 12,15.71C13.63,17.19 15.78,18 18,18C18.25,18 18.5,18 18.73,18Z",
    "reboot": "M12,4C14.1,4 16.1,4.8 17.6,6.3C20.7,9.4 20.7,14.5 17.6,17.6C15.8,19.5 13.3,20.2 10.9,19.9L11.4,17.9C13.1,18.1 14.9,17.5 16.2,16.2C18.5,13.9 18.5,10.1 16.2,7.7C15.1,6.6 13.5,6 12,6V10.6L7,5.6L12,0.6V4M6.3,17.6C3.7,15 3.3,11 5.1,7.9L6.6,9.4C5.5,11.6 5.9,14.4 7.8,16.2C8.3,16.7 8.9,17.1 9.6,17.4L9,19.4C8,19 7.1,18.4 6.3,17.6Z",
    "poweroff": "M16.56,5.44L15.11,6.89C16.84,7.94 18,9.83 18,12A6,6 0 0,1 12,18A6,6 0 0,1 6,12C6,9.83 7.16,7.94 8.88,6.88L7.44,5.44C5.36,6.88 4,9.28 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12C20,9.28 18.64,6.88 16.56,5.44M13,3H11V13H13",
    "logout": "M17 7L15.59 8.41L18.17 11H8V13H18.17L15.59 15.58L17 17L22 12M4 5H12V3H4C2.9 3 2 3.9 2 5V19C2 20.1 2.9 21 4 21H12V19H4V5Z",
}

PROFILES = [("power-saver", _("Power saver")), ("balanced", _("Balanced")), ("performance", _("Performance"))]

POWER = [
    ("hibernate", _("Hibernate"), ["spawn", "--", "systemctl", "hibernate"], False),
    ("reboot", _("Reboot"), ["spawn", "--", "systemctl", "reboot"], True),
    ("poweroff", _("Power off"), ["spawn", "--", "systemctl", "poweroff"], True),
    ("logout", _("Log out"), ["quit", "--skip-confirmation"], True),
]

INIT, SELECT = 0, 1


def option(key, value):
    sys.stdout.write(f"\0{key}\x1f{value}\n")


def battery():
    res = run("busctl", "call", "--system", "org.freedesktop.UPower", "/org/freedesktop/UPower",
              "org.freedesktop.UPower", "EnumerateDevices")
    return next((p.strip('"') for p in res.stdout.split() if "/battery_" in p), None)


def upower(prop, path):
    if not path:
        return None
    res = run("busctl", "get-property", "--system", "org.freedesktop.UPower",
              path, "org.freedesktop.UPower.Device", prop)
    kind, _x, value = res.stdout.strip().partition(" ")
    if kind == "b":
        return value == "true"
    if kind == "u":
        return int(value)
    return None


def ensure_icons():
    ICONS.mkdir(parents=True, exist_ok=True)
    for key, d in PATHS.items():
        f = ICONS / f"{key}.svg"
        if not f.exists():
            f.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                         f'<path fill="{ICON_COLOR}" d="{d}"/></svg>\n')


PPD = [("org.freedesktop.UPower.PowerProfiles", "/org/freedesktop/UPower/PowerProfiles"),
       ("net.hadess.PowerProfiles", "/net/hadess/PowerProfiles")]


def profile_get():
    for name, path in PPD:
        res = run("busctl", "get-property", "--system", name, path, name, "ActiveProfile")
        if res.returncode == 0:
            return res.stdout.strip().partition(" ")[2].strip('"')
    return ""


def profile_set(key):
    for name, path in PPD:
        res = run("busctl", "set-property", "--system", name, path, name,
                  "ActiveProfile", "s", key)
        if res.returncode == 0:
            break
    return res


def tile(label, key, active=False, urgent=False):
    extra = ""
    if active:
        extra += "\x1factive\x1ftrue"
    if urgent:
        extra += f"\x1fdisplay\x1f{_('Press again')}\x1furgent\x1ftrue"
    sys.stdout.write(f"{label}\0icon\x1f{ICONS / key}.svg\x1finfo\x1f{key}{extra}\n")


def show(pending=""):
    ensure_icons()
    option("no-custom", "true")
    option("keep-selection", "true")
    option("data", pending)
    profile = profile_get()
    for key, label in PROFILES:
        tile(label, key, active=(key == profile))
    bat = battery()
    if bat and upower("ChargeThresholdSupported", bat):
        end = upower("ChargeEndThreshold", bat)
        tile(_("Charge to {}%").format(end) if end else _("Battery care"), "charge",
             active=bool(upower("ChargeThresholdEnabled", bat)))
    for key, label, _x, _y in POWER:
        tile(label, key, urgent=(key == pending))


def notify_error(title, res):
    if res.returncode != 0:
        run("notify-send", title, res.stderr.strip() or _("Could not change it"))


def select(key):
    if key in dict(PROFILES):
        notify_error(_("Power profile"), profile_set(key))
        show()
        return
    if key == "charge":
        bat = battery()
        enabled = bool(upower("ChargeThresholdEnabled", bat))
        notify_error(_("Charge limit"), run(
            "busctl", "call", "--system", "org.freedesktop.UPower", bat,
            "org.freedesktop.UPower.Device", "EnableChargeThreshold", "b",
            "false" if enabled else "true"))
        show()
        return
    for k, _x, action, confirm in POWER:
        if k != key:
            continue
        if confirm and os.environ.get("ROFI_DATA") != key:
            show(pending=key)
            return
        run("niri", "msg", "action", *action)
        return


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
    mode = _("power")
    cmd = ["rofi", "-show", mode, "-modes", f"{mode}:{SELF} list",
           "-replace", "-show-icons"]
    if THEME.exists():
        cmd += ["-theme", str(THEME)]
    os.execvp("rofi", cmd)


def main():
    if len(sys.argv) < 2:
        launch()
    if sys.argv[1] != "list":
        sys.exit(__doc__)
    retv = int(os.environ.get("ROFI_RETV", "0"))
    info = os.environ.get("ROFI_INFO", "")
    if retv == SELECT and info:
        select(info)
    else:
        show()


if __name__ == "__main__":
    main()

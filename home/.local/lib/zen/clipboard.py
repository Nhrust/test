"""zen-clipboard — clipboard history (cliphist) with pinned entries in Rofi."""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import zen
from zen import _

PINS = zen.STATE_HOME / "zen/clip-pins"
OLD_PINS = zen.CONFIG_HOME / "zen/clip-pins"
THEME = zen.CONFIG_HOME / "rofi/clipboard.rasi"
COLOR = zen.palette()
SELF = os.path.realpath(sys.argv[0])

PREVIEW_W = 100

IMAGE = re.compile(r"^\[\[ binary data (.+) (\w+) (\d+)x(\d+) \]\]$")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

ICONS = zen.RUNTIME / "zen-clipboard"
STAR_ON = ICONS / "star-on.svg"
STAR_OFF = ICONS / "star-off.svg"
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path {} d="{}"/></svg>\n'
STAR = "M12,17.27L18.18,21L16.54,13.97L22,9.24L14.81,8.62L12,2L9.19,8.62L2,9.24L7.45,13.97L5.82,21L12,17.27Z"
STAR_OUTLINE = ("M12,15.39L8.24,17.66L9.23,13.38L5.91,10.5L10.29,10.13L12,6.09L13.71,10.13L18.09,10.5"
                "L14.77,13.38L15.76,17.66M22,9.24L14.81,8.63L12,2L9.19,8.63L2,9.24L7.45,13.97L5.82,21"
                "L12,17.27L18.18,21L16.54,13.97L22,9.24Z")


def ensure_icons():
    """The star icons in the palette colours; written only when they change."""
    ICONS.mkdir(parents=True, exist_ok=True)
    for path, text in ((STAR_ON, SVG.format(f'fill="{COLOR["fg"]}" stroke="{COLOR["bg"]}" '
                                            f'stroke-width="1" stroke-linejoin="round"', STAR)),
                       (STAR_OFF, SVG.format(f'fill="{COLOR["line"]}"', STAR_OUTLINE))):
        try:
            if path.read_text() == text:
                continue
        except OSError:
            pass
        path.write_text(text)


INIT, SELECT, DELETE, CUSTOM_1, CUSTOM_2, LEFT, RIGHT = 0, 1, 3, 10, 11, 13, 14
WIPE_ASK = _("Clear the history? Press again")


def out(text, **opts):
    if opts:
        text += "\0" + "\x1f".join(f"{k}\x1f{v}" for k, v in opts.items())
    sys.stdout.write(text + "\n")


def option(key, value):
    sys.stdout.write(f"\0{key}\x1f{value}\n")


def cliphist(*args, data=None):
    return subprocess.run(["cliphist", *args], input=data, capture_output=True).stdout


def copy(data):
    subprocess.run(["wl-copy"], input=data,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def preview(text):
    text = " ".join(text.split())
    return text if len(text) <= PREVIEW_W else text[:PREVIEW_W] + "…"


def row(plain, info, pinned, last_pin=False):
    opts = {"icon": STAR_ON if pinned else STAR_OFF, "info": info}
    if last_pin:
        opts["active"] = "true"
    out(plain, **opts)


def image_label(m):
    size, fmt, w, h = m.groups()
    return _("Image {} {} {}").format(f"{w}×{h}", fmt, size)


def pin_files():
    if not PINS.exists() and OLD_PINS.is_dir():
        PINS.parent.mkdir(parents=True, exist_ok=True)
        OLD_PINS.rename(PINS)
    return sorted(f for f in PINS.iterdir() if f.is_file()) if PINS.is_dir() else []


def pin_label(f):
    if f.suffix.lower() in IMAGE_EXT:
        return _("Image {}").format(f.stem)
    return preview(f.read_text("utf-8", "replace")) or f.name


def pin(cid, history_preview):
    data = cliphist("decode", cid)
    if not data:
        return
    PINS.mkdir(parents=True, exist_ok=True)
    if any(f.read_bytes() == data for f in pin_files()):
        return
    m = IMAGE.match(history_preview)
    ext = "." + m.group(2) if m else ".txt"
    name = time.strftime("%Y%m%d-%H%M%S")
    path, n = PINS / f"{name}{ext}", 1
    while path.exists():
        path, n = PINS / f"{name}-{n}{ext}", n + 1
    path.write_bytes(data)


def history_rows():
    rows = []
    for line in cliphist("list").decode("utf-8", "replace").splitlines():
        cid, _x, prev = line.partition("\t")
        if cid.isdigit():
            rows.append((cid, prev))
    return rows


def show(keep=False, data=None):
    ensure_icons()
    option("use-hot-keys", "true")
    option("no-custom", "true")
    option("data", data or "")
    if keep:
        option("keep-selection", "true")
    if data == "wipe":
        out(WIPE_ASK, info="w:", urgent="true")
    pins = pin_files()
    labels = [pin_label(f) for f in pins]
    history = [(c, p) for c, p in history_rows() if p not in set(labels)]
    for i, (f, label) in enumerate(zip(pins, labels)):
        row(label, f"p:{f.name}", pinned=True,
            last_pin=(i == len(pins) - 1 and bool(history)))
    for cid, prev in history:
        m = IMAGE.match(prev)
        row(image_label(m) if m else prev, f"h:{cid}", pinned=False)
    if not pins and not history:
        out(_("The clipboard is empty"), nonselectable="true")


def action(retv, info):
    kind, _x, key = info.partition(":")
    if kind == "w":
        if retv in (SELECT, DELETE):
            wipe()
        else:
            show()
        return
    if kind == "h":
        if retv == SELECT:
            copy(cliphist("decode", key))
            return
        if retv == CUSTOM_1:
            prev = dict(history_rows()).get(key, "")
            pin(key, prev)
        elif retv == DELETE:
            cliphist("delete", data=f"{key}\t\n".encode())
    elif kind == "p":
        path = PINS / key
        if path.parent != PINS:
            return
        if retv == SELECT:
            if path.is_file():
                copy(path.read_bytes())
            return
        if retv == CUSTOM_1 and path.is_file():
            cliphist("store", data=path.read_bytes())
            path.unlink()
        elif retv == DELETE and path.is_file():
            label = pin_label(path)
            path.unlink()
            for cid, prev in history_rows():
                if prev == label:
                    cliphist("delete", data=f"{cid}\t\n".encode())
    show(keep=True)


def wipe():
    if os.environ.get("ROFI_DATA") == "wipe":
        cliphist("wipe")
        show()
    else:
        show(data="wipe")


def our_rofi():
    res = subprocess.run(["pgrep", "-x", "rofi"], capture_output=True, text=True)
    for pid in res.stdout.split():
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
        subprocess.run(["kill", pid])
        sys.exit(0)
    ensure_icons()
    cmd = ["rofi", "-show", "clip", "-modes", f"clip:{SELF} list",
           "-replace",
           "-show-icons",
           "-hover-select", "-me-select-entry", "", "-me-accept-entry", "MousePrimary",
           "-kb-cancel", "Escape,Control+g,Control+bracketleft",
           "-kb-custom-1", "Alt+p,Alt+Cyrillic_ze,MouseSecondary",
           "-kb-delete-entry", "Shift+Delete,MouseMiddle",
           "-kb-custom-2", "Control+Shift+Delete",
           "-kb-move-char-back", "Control+b", "-kb-move-char-forward", "Control+f",
           "-kb-custom-4", "Left", "-kb-custom-5", "Right"]
    if THEME.exists():
        hint = _("Search the clipboard…").replace('"', "")
        clear = _("Clear").replace('"', "")
        cmd += ["-theme", str(THEME), "-theme-str", f'entry {{ placeholder: "{hint}"; }}',
                "-theme-str", f'button-wipe {{ content: "{clear}"; }}']
    os.execvp("rofi", cmd)


def main():
    if len(sys.argv) < 2:
        launch()
    if sys.argv[1] != "list":
        sys.exit(__doc__)
    retv = int(os.environ.get("ROFI_RETV", "0"))
    info = os.environ.get("ROFI_INFO", "")
    retv = {LEFT: CUSTOM_1, RIGHT: DELETE}.get(retv, retv)
    if retv == CUSTOM_2:
        wipe()
    elif retv != INIT and info:
        action(retv, info)
    else:
        show()


if __name__ == "__main__":
    main()

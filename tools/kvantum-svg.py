#!/usr/bin/env python3
"""kvantum-svg — derive the Kvantum template (Zen.svg) from KvGnomeDark.svg.

  python3 tools/kvantum-svg.py /usr/share/Kvantum/KvGnomeDark/KvGnomeDark.svg \
      home/.local/share/zen/templates/.config/Kvantum/Zen/Zen.svg

Every colour of the source becomes a palette role ({{bg}}, {{accent}}, …),
so "zen apply" can paint the theme in any palette.
"""
import copy
import re
import sys
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)
HREF = f"{{{XLINK}}}href"

BG, DIM, LINE, MUTED, FG, ACCENT, RED = (
    "{{bg}}", "{{deep}}", "{{line}}", "{{muted}}", "{{fg}}", "{{accent}}", "{{error}}")

GLOBAL = {
    LINE:   "1b1b1b 1e1e1e 191919 171717 141414 202020 423b36 5a5a5a 646464 7b7b7b",
    DIM:    "050505 070707 080808 090909 0a0a0a 0d0d0d 0f0f0f 000",
    BG:     "232323 252525 262626 282828 2a2a2a 2d2d2d 2e2e2e 2e2f30 2f2f2f 2f2f31 303030 "
            "313133 323232 353535 373737 383839 393939 3b3b3d 454547 464646 111",
    MUTED:  "969696 a4a4a3 a5a5a5",
    FG:     "c8c8c8 c9c9c7 d2d2d2 eeeeec fff",
    ACCENT: "15539e 1b6acb 3584e4 3daee9 b74aff",
    RED:    "f55",
}
GMAP = {"#" + old: new for new, olds in GLOBAL.items() for old in olds.split()}
COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}(?![0-9a-fA-F])|#[0-9a-fA-F]{3}(?![0-9a-fA-F])")
PAINT = ("fill", "stroke", "stop-color")


def styles(e):
    out = []
    st = e.get("style")
    if st:
        for kv in st.split(";"):
            if ":" in kv:
                k, v = kv.split(":", 1)
                if k.strip() in PAINT:
                    out.append((k.strip(), v.strip()))
    for k in PAINT:
        if e.get(k):
            out.append((k, e.get(k)))
    return out


def set_paint(e, fn):
    st = e.get("style")
    if st:
        parts = []
        for kv in st.split(";"):
            if ":" in kv:
                k, v = kv.split(":", 1)
                if k.strip() in PAINT:
                    nv = fn(k.strip(), v.strip())
                    if nv is not None:
                        kv = f"{k.strip()}:{nv}"
            parts.append(kv)
        e.set("style", ";".join(parts))
    for k in PAINT:
        if e.get(k):
            nv = fn(k, e.get(k))
            if nv is not None:
                e.set(k, nv)


def global_pass(root):
    def fn(_, v):
        return COLOR_RE.sub(lambda m: GMAP.get(m.group(0).lower(), m.group(0)), v)
    for e in root.iter():
        set_paint(e, fn)


def recolor(e, mapping):
    def fn(_, v):
        if v.startswith("url(") and "url" in mapping:
            return mapping["url"]
        return mapping.get(v.lower())
    for x in e.iter():
        set_paint(x, fn)


def inline_uses(root, e, ids):
    for parent in list(e.iter()):
        for i, ch in enumerate(list(parent)):
            if ch.tag == f"{{{SVG}}}use":
                ref = ids.get(ch.get(HREF, "").lstrip("#"))
                if ref is None:
                    continue
                g = ET.Element(f"{{{SVG}}}g")
                if ch.get("transform"):
                    g.set("transform", ch.get("transform"))
                c = copy.deepcopy(ref)
                for x in c.iter():
                    x.attrib.pop("id", None)
                g.append(c)
                parent.remove(ch)
                parent.insert(i, g)


RULES = [
    (r"^(button|btn|lineedit)-(normal|focused)-bottom$|^menubar-normal-bottom", {DIM: LINE}, False),
    (r"^linearGradient3251$", {DIM: LINE}, False),
    (r"^(button|btn)-focused", {LINE: MUTED}, False),
    (r"^(button|btn)-toggled-inactive", {BG: LINE, DIM: LINE}, False),
    (r"^(checkbox-(checked|tristate)|radio-checked)-(normal|focused)$",
     {DIM: ACCENT, BG: ACCENT, "url": ACCENT, FG: BG}, True),
    (r"^(checkbox|radio)-normal$", {DIM: LINE, "url": BG}, False),
    (r"^(checkbox|radio)-focused$", {DIM: MUTED}, False),
    (r"^(slider|progress)-normal-(left|topleft)$", {BG: LINE}, False),
    (r"^slidercursor-(tickless-)?normal$", {"url": FG}, False),
    (r"^slidercursor-(tickless-)?focused$", {BG: FG, "url": ACCENT}, False),
]


def main(src, dst):
    tree = ET.parse(src)
    root = tree.getroot()
    global_pass(root)
    ids = {e.get("id"): e for e in root.iter() if e.get("id")}
    for pattern, mapping, inline in RULES:
        rx = re.compile(pattern)
        hit = [e for i, e in ids.items() if rx.search(i)]
        if not hit:
            print(f"warning: nothing matches {pattern}", file=sys.stderr)
        for e in hit:
            if inline:
                inline_uses(root, e, ids)
            if pattern.startswith("^slidercursor") and "normal" in pattern:
                def fn(prop, v):
                    if v.startswith("url("):
                        return FG if prop == "fill" else LINE
                    return None
                for x in e.iter():
                    set_paint(x, fn)
            else:
                recolor(e, mapping)
    tree.write(dst, encoding="UTF-8", xml_declaration=False)
    left = sorted({v for e in root.iter() for _, v in styles(e)
                   if not v.startswith("url(") and v != "none"})
    print("colours left:", " ".join(left))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])

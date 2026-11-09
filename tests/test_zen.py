"""Tests of the zen scripts against stand-in programs (tests/mock.py).

    tests/run            all of them
    tests/run -k audio   only the ones with "audio" in their name

Each test gets a fresh home folder built from home/ the way deploy.sh builds
it, and a bin folder where makoctl, wpctl, busctl, niri and the others are
tests/mock.py. Nothing outside the temporary folder is touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MOCKED = ["makoctl", "wpctl", "pw-dump", "busctl", "cliphist", "wl-copy", "niri", "systemctl",
          "brightnessctl", "ddcutil", "kanshictl", "pkill", "pgrep", "notify-send", "sudo",
          "nmcli", "gsettings", "setvtrgb", "rofi", "playerctl", "gtklock", "pacman"]

SELECT, DELETE, ESC, LEFT, RIGHT, TAB = 1, 3, 12, 13, 14, 15


def base_state():
    return {
        "mako": {"modes": ["default"],
                 "list": [{"id": 14, "app_name": "Telegram", "desktop_entry": "org.telegram.desktop",
                           "summary": "Anna", "body": "Where are you?", "urgency": "normal"}],
                 "history": [
                     {"id": 12, "app_name": "notify-send", "summary": "test", "body": "hello",
                      "urgency": "normal"},
                     {"id": 11, "app_name": "Updates", "summary": "12 packages",
                      "body": "A long text that does not fit into one line of the menu, so Enter "
                              "opens the full view first.", "urgency": "low"}]},
        "wp": {"default_sink": 51, "default_source": 60,
               "nodes": {
                   "50": {"media.class": "Audio/Sink", "node.name": "alsa_output.analog",
                          "node.description": "Ryzen HD Audio Controller Analog Stereo"},
                   "51": {"media.class": "Audio/Sink", "node.name": "alsa_output.usb-flow8",
                          "node.description": "FLOW 8 Multichannel"},
                   "60": {"media.class": "Audio/Source", "node.name": "alsa_input.dmic",
                          "node.description": "Digital Microphone"},
                   "70": {"media.class": "Stream/Output/Audio", "node.name": "Firefox",
                          "application.name": "Firefox"},
                   "71": {"media.class": "Stream/Output/Audio", "node.name": "mpv",
                          "application.name": "mpv"}},
               "volume": {"50": [0.45, False], "51": [0.6, False], "60": [0.3, True],
                          "70": [0.7, False], "71": [1.0, True]}},
        "bluez": {"adapter": "/org/bluez/hci0", "powered": True, "devices": [
            {"path": "/org/bluez/hci0/dev_AA_BB_CC_00_11_22", "name": "WH-1000XM4",
             "icon": "audio-headset", "connected": True},
            {"path": "/org/bluez/hci0/dev_AA_BB_CC_00_11_33", "name": "Pixel Buds",
             "icon": "audio-headphones", "connected": False},
            {"path": "/org/bluez/hci0/dev_00_00_00_00_00_01", "name": "Mouse",
             "icon": "input-mouse", "connected": True}]},
        "upower": {"profile": "balanced", "ChargeThresholdSupported": True,
                   "ChargeThresholdEnabled": True, "ChargeEndThreshold": 80},
        "clip": {"1": "Hello world", "2": "git clone https://github.com/Nhrust/zen", "3": "line one\nline two"},
        "niri": {"outputs": {"eDP-1": json.loads((FIXTURES / "outputs.json").read_text())["eDP-1"]},
                 "windows": [{"id": 5, "app_id": "org.telegram.desktop", "title": "Telegram"}]},
        "systemd": {"active": ["zen-idle.service"]},
        "player": {"status": "Playing", "artist": "Artist", "track": 1, "name": "mpv"},
        "brightness": 50,
    }


class Zen(unittest.TestCase):
    """A home folder built from the repository, stand-in programs and helpers to run the menus."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zen-test-"))
        self.home = self.tmp / "home"
        self.mock = self.tmp / "mock"
        self.bin = self.tmp / "bin"
        self.run_dir = self.tmp / "run"
        for d in (self.mock, self.bin, self.run_dir):
            d.mkdir(parents=True)
        shutil.copytree(REPO / "home", self.home, symlinks=True)
        for p in self.home.rglob("*"):
            if p.is_file() and not p.is_symlink():
                try:
                    text = p.read_text()
                except UnicodeDecodeError:
                    continue
                if "@HOME@" in text or "@USER@" in text:
                    p.write_text(text.replace("@HOME@", str(self.home)).replace("@USER@", "tester"))
        conf = self.home / ".config/zen/zen.conf"
        conf.write_text((REPO / "home/.config/zen/zen.conf.example").read_text())
        locale_dir = self.home / ".local/share/locale/ru/LC_MESSAGES"
        locale_dir.mkdir(parents=True)
        subprocess.run(["msgfmt", "-o", str(locale_dir / "zen.mo"), str(REPO / "po/ru.po")], check=True)
        for name in MOCKED:
            (self.bin / name).symlink_to(Path(__file__).resolve().parent / "mock.py")
        self.state = base_state()
        self.save()
        weather = json.loads((FIXTURES / "weather.json").read_text())
        weather["fetched"] = time.time()
        (self.run_dir / "zen-center-weather.json").write_text(json.dumps(weather))
        self.env = {
            "HOME": str(self.home), "PATH": f"{self.bin}:{os.environ['PATH']}",
            "XDG_RUNTIME_DIR": str(self.run_dir), "ZEN_MOCK": str(self.mock),
            "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
        }
        (self.mock / "calls.log").write_text("")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # state of the stand-in programs

    def save(self):
        (self.mock / "state.json").write_text(json.dumps(self.state))

    def load(self):
        self.state = json.loads((self.mock / "state.json").read_text())
        return self.state

    def calls(self, name=None):
        lines = (self.mock / "calls.log").read_text().splitlines()
        return [ln for ln in lines if name is None or ln.split(" ", 1)[0] == name]

    # running the scripts

    def run_cmd(self, *cmd, env=None, check=True):
        res = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                             env={**self.env, **(env or {})}, timeout=30)
        if check and res.returncode != 0:
            self.fail(f"{cmd} → {res.returncode}\n{res.stderr}")
        return res

    def menu(self, script, retv=0, info="", data=""):
        """Run a Rofi script-mode step; returns (options, rows) where a row is (text, options)."""
        res = self.run_cmd(self.home / ".local/bin" / script, "list",
                           env={"ROFI_RETV": str(retv), "ROFI_INFO": info, "ROFI_DATA": data})
        self.assertEqual(res.stderr.strip(), "", res.stderr)
        options, rows = {}, []
        for line in res.stdout.split("\n"):
            if not line:
                continue
            if line.startswith("\0"):
                key, _sep, value = line[1:].partition("\x1f")
                options[key] = value
                continue
            text, _sep, rest = line.partition("\0")
            parts = rest.split("\x1f")
            rows.append((text, dict(zip(parts[::2], parts[1::2]))))
        return options, rows

    @staticmethod
    def info(rows, prefix):
        return next(r[1]["info"] for r in rows if r[1].get("info", "").startswith(prefix))

    @staticmethod
    def texts(rows):
        return [r[0] for r in rows]


# ---------------------------------------------------------------- palette


class TestPalette(Zen):

    def zen(self):
        sys.path.insert(0, str(self.home / ".local/lib/zen"))
        os.environ["HOME"] = str(self.home)
        import importlib
        import zen
        importlib.reload(zen)
        zen.settings.cache_clear()
        return zen

    def tearDown(self):
        lib = str(self.home / ".local/lib/zen")
        if lib in sys.path:
            sys.path.remove(lib)
        sys.modules.pop("zen", None)
        super().tearDown()

    def test_render_formats(self):
        zen = self.zen()
        out = zen.render("{{bg}} {{bg|hex}} {{bg|rgb}} {{fg|argb:80}} {{fg|rgba:6e}} {{color4}}")
        self.assertEqual(out, "#0b0b0b 0b0b0b 11,11,11 #80dedede #dedede6e #bdb3fa")

    def test_terminal_follows_palette(self):
        conf = self.home / ".config/zen/zen.conf"
        conf.write_text(conf.read_text().replace("accent = #bdb3fa", "accent = #a0e0ff")
                        + "color9 = accent\n")
        zen = self.zen()
        c = zen.colors()
        self.assertEqual((c["color4"], c["color9"], c["color0"]), ("#a0e0ff", "#a0e0ff", "#0b0b0b"))

    def test_apply_writes_once(self):
        first = self.run_cmd(self.home / ".local/bin/zen", "apply", "--user").stdout.split()
        self.assertIn(str(self.home / ".config/mako/config"), first)
        self.assertIn(str(self.home / ".config/niri/zen-colors.kdl"), first)
        second = self.run_cmd(self.home / ".local/bin/zen", "apply", "--user").stdout.split()
        self.assertEqual(second, [])
        for path in map(Path, first):
            self.assertNotIn("{{", path.read_text(), path)


# ---------------------------------------------------------------- notifications


class TestCenter(Zen):

    def test_list(self):
        options, rows = self.menu("zen-center")
        texts = self.texts(rows)
        self.assertTrue(texts[0].startswith("Do not disturb"))
        self.assertEqual(len([r for r in rows if r[1]["info"][:2] in ("a:", "h:")]), 3)
        self.assertIn("Clear all", texts[-1])
        self.assertIn("message", options)

    def test_go_never_copies(self):
        """Opening a notification without a window must not touch the clipboard."""
        self.menu("zen-center", SELECT, "h:12")
        self.assertEqual(self.calls("wl-copy"), [])
        _o, rows = self.menu("zen-center")
        self.assertNotIn("h:12", [r[1]["info"] for r in rows])

    def test_go_focuses_the_window(self):
        self.state["mako"]["list"][0].update(summary="Hi", body="")
        self.save()
        self.menu("zen-center", SELECT, "a:14")
        self.assertIn("makoctl invoke -n 14", self.calls("makoctl"))
        self.assertIn("niri msg action focus-window --id 5", self.calls("niri"))
        self.assertEqual(self.calls("wl-copy"), [])

    def test_long_note_opens_detail(self):
        options, rows = self.menu("zen-center", SELECT, "h:11")
        self.assertIn("d=h_11", options["data"])
        infos = [r[1]["info"] for r in rows]
        self.assertEqual((infos[0], infos[-2], infos[-1]), ("back", "open", "del"))
        self.assertTrue(all(r[1].get("nonselectable") for r in rows[1:-2]))
        self.assertEqual(rows[int(options["new-selection"])][1]["info"], "open")

    def test_detail_back_and_delete(self):
        options, _rows = self.menu("zen-center", SELECT, "h:11")
        data = options["data"]
        options, rows = self.menu("zen-center", SELECT, "back", data)
        self.assertNotIn("d=", options["data"])
        self.assertEqual(rows[int(options["new-selection"])][1]["info"], "h:11")
        options, _rows = self.menu("zen-center", ESC, "t2", data)
        self.assertNotIn("d=", options["data"])
        _o, rows = self.menu("zen-center", SELECT, "del", data)
        self.assertNotIn("h:11", [r[1]["info"] for r in rows])

    def test_escape_closes_the_list(self):
        res = self.run_cmd(self.home / ".local/bin/zen-center", "list",
                           env={"ROFI_RETV": str(ESC), "ROFI_INFO": "dnd", "ROFI_DATA": "0:l"})
        self.assertEqual(res.stdout, "")

    def test_right_click_deletes(self):
        self.menu("zen-center", DELETE, "h:12")
        _o, rows = self.menu("zen-center")
        self.assertNotIn("h:12", [r[1]["info"] for r in rows])

    def test_right_deletes(self):
        self.menu("zen-center", RIGHT, "a:14")
        self.assertEqual(self.load()["mako"]["list"], [])

    def test_dnd(self):
        self.menu("zen-center", SELECT, "dnd")
        self.assertIn("do-not-disturb", self.load()["mako"]["modes"])
        out = self.run_cmd(self.home / ".local/bin/zen-center", "dnd").stdout.strip()
        self.assertTrue(out.endswith("3"), out)
        self.menu("zen-center", RIGHT, "dnd")
        self.assertNotIn("do-not-disturb", self.load()["mako"]["modes"])

    def test_bell_counts_unseen(self):
        """Without do-not-disturb the bell shows notifications that went to the history unseen."""
        bell = self.run_cmd(self.home / ".local/bin/zen-center", "dnd").stdout.strip()
        self.assertEqual(bell, "\U000F009A 2")
        self.run_cmd(self.home / ".local/bin/zen-center", "read", "12")
        self.run_cmd(self.home / ".local/bin/zen-center", "read", "11")
        self.assertEqual(self.run_cmd(self.home / ".local/bin/zen-center", "dnd").stdout.strip(), "")

    def test_dnd_toggle_command(self):
        self.run_cmd(self.home / ".local/bin/zen-center", "dnd", "toggle")
        self.assertIn("do-not-disturb", self.load()["mako"]["modes"])
        self.assertIn("pkill -RTMIN+11 -x waybar", self.calls("pkill"))
        self.run_cmd(self.home / ".local/bin/zen-center", "dnd", "toggle")
        self.assertNotIn("do-not-disturb", self.load()["mako"]["modes"])

    def test_clear_command(self):
        self.run_cmd(self.home / ".local/bin/zen-center", "clear")
        _o, rows = self.menu("zen-center")
        self.assertFalse([r for r in rows if r[1]["info"][:2] in ("a:", "h:")])

    def test_tab_moves_to_the_calendar(self):
        options, _rows = self.menu("zen-center", TAB, "dnd", "0:l")
        self.assertTrue(options["data"].startswith("0:c"))

    def test_clear_asks_first(self):
        options, rows = self.menu("zen-center", SELECT, "clear", "0:l")
        self.assertIn("wipe", options["data"])
        self.menu("zen-center", SELECT, "clear", options["data"])
        _o, rows = self.menu("zen-center")
        self.assertFalse([r for r in rows if r[1]["info"][:2] in ("a:", "h:")])


# ---------------------------------------------------------------- sound


class TestAudio(Zen):

    def volume(self, nid):
        return self.load()["wp"]["volume"][str(nid)]

    def test_main(self):
        options, rows = self.menu("zen-audio")
        texts = self.texts(rows)
        self.assertEqual(rows[0][1]["info"], "media:")
        self.assertIn("Artist — Song 1", texts[0])
        self.assertIn("FLOW 8 Multichannel", texts[1])
        self.assertIn("60%", texts[2])
        self.assertIn("Digital Microphone", texts[4])
        self.assertEqual(rows[int(options["new-selection"])][1]["info"], "view:outputs")
        self.assertTrue(any(t.startswith("Applications · 2") for t in texts))
        self.assertTrue(any(t.startswith("Bluetooth · 1 connected") for t in texts))
        self.assertIn("60%", options["message"])
        self.assertIn("30%", options["message"])

    def test_steps(self):
        self.menu("zen-audio", RIGHT, "adj:vol:51")
        self.assertEqual(self.volume(51)[0], 0.65)
        self.menu("zen-audio", LEFT, "adj:vol:51")
        self.menu("zen-audio", LEFT, "adj:vol:51")
        self.assertEqual(self.volume(51)[0], 0.55)
        self.state = self.load()
        self.state["wp"]["volume"]["51"][0] = 0.98
        self.save()
        self.menu("zen-audio", RIGHT, "adj:vol:51")
        self.assertEqual(self.volume(51)[0], 1.0)

    def test_level_list(self):
        options, rows = self.menu("zen-audio", SELECT, "adj:vol:51")
        self.assertEqual(options["data"], "vol:51")
        self.assertEqual([r[0] for r in rows if r[1].get("active")], ["60%"])
        self.menu("zen-audio", SELECT, "set:51:30", "vol:51")
        self.assertEqual(self.volume(51)[0], 0.3)
        options, _rows = self.menu("zen-audio", ESC, "", "vol:51")
        self.assertEqual(options["data"], "main")

    def test_mute_signals_the_panel(self):
        self.menu("zen-audio", SELECT, "adj:mute:60")
        self.assertFalse(self.volume(60)[1])
        self.assertIn("pkill -RTMIN+12 -x waybar", self.calls("pkill"))

    def test_default_output(self):
        _o, rows = self.menu("zen-audio", SELECT, "view:outputs")
        self.assertEqual([r[0] for r in rows if r[1].get("active")], ["FLOW 8 Multichannel"])
        self.menu("zen-audio", SELECT, "default:50", "outputs")
        self.assertEqual(self.load()["wp"]["default_sink"], 50)

    def test_apps(self):
        _o, rows = self.menu("zen-audio", SELECT, "view:apps")
        self.assertEqual([r[1]["info"] for r in rows[1:]], ["app:70", "app:71"])
        self.menu("zen-audio", SELECT, "app:71", "apps")
        self.assertFalse(self.volume(71)[1])
        self.menu("zen-audio", RIGHT, "app:70", "apps")
        self.assertEqual(self.volume(70)[0], 0.75)

    def test_bluetooth(self):
        _o, rows = self.menu("zen-audio", SELECT, "view:bt")
        texts = self.texts(rows)
        self.assertNotIn("Mouse", " ".join(texts))
        pixel = self.info(rows, "bt:/org/bluez/hci0/dev_AA_BB_CC_00_11_33")
        self.menu("zen-audio", SELECT, pixel, "bt")
        for _x in range(50):
            if not (self.run_dir / "zen-audio-connecting").exists():
                break
            time.sleep(0.1)
        dev = next(d for d in self.load()["bluez"]["devices"] if d["name"] == "Pixel Buds")
        self.assertTrue(dev["connected"])
        self.assertTrue(any("Connected: Pixel Buds" in c for c in self.calls("notify-send")))
        self.menu("zen-audio", SELECT, "adj:btpower:0", "bt")
        self.assertFalse(self.load()["bluez"]["powered"])

    def test_player(self):
        self.menu("zen-audio", SELECT, "media:")
        self.assertEqual(self.load()["player"]["status"], "Paused")
        _o, rows = self.menu("zen-audio", RIGHT, "media:")
        self.assertIn("Song 2", rows[0][0])
        self.state = self.load()
        self.state["player"] = None
        self.save()
        _o, rows = self.menu("zen-audio")
        self.assertNotEqual(rows[0][1]["info"], "media:")

    def test_without_bluetooth(self):
        self.state["bluez"] = None
        self.save()
        _o, rows = self.menu("zen-audio")
        self.assertFalse([t for t in self.texts(rows) if t.startswith("Bluetooth")])

    def test_mic_mute_command(self):
        self.run_cmd(self.home / ".local/bin/zen-audio", "mic-mute")
        self.assertFalse(self.volume(60)[1])
        out = self.run_cmd(self.home / ".local/lib/zen/bar/mic").stdout
        self.assertEqual(json.loads(out)["text"], "")
        self.run_cmd(self.home / ".local/bin/zen-audio", "mic-mute")
        self.assertEqual(json.loads(self.run_cmd(self.home / ".local/lib/zen/bar/mic").stdout)["class"], "muted")


# ---------------------------------------------------------------- clipboard, power, displays


class TestClipboard(Zen):

    def test_list_and_copy(self):
        _o, rows = self.menu("zen-clipboard")
        self.assertEqual([r[1]["info"] for r in rows], ["h:3", "h:2", "h:1"])
        self.menu("zen-clipboard", SELECT, "h:2")
        self.assertEqual(self.calls("wl-copy"), ["wl-copy"])

    def test_pin_and_delete(self):
        self.menu("zen-clipboard", LEFT, "h:1")
        pins = list((self.home / ".local/state/zen/clip-pins").iterdir())
        self.assertEqual([p.read_text() for p in pins], ["Hello world"])
        _o, rows = self.menu("zen-clipboard")
        self.assertTrue(rows[0][1]["info"].startswith("p:"))
        self.menu("zen-clipboard", RIGHT, "h:2")
        self.assertNotIn("2", self.load()["clip"])


class TestPower(Zen):

    def test_tiles(self):
        _o, rows = self.menu("zen-power")
        infos = [r[1]["info"] for r in rows]
        self.assertEqual(infos[:4], ["power-saver", "balanced", "performance", "charge"])
        self.assertEqual(rows[1][1].get("active"), "true")
        self.menu("zen-power", SELECT, "performance")
        self.assertEqual(self.load()["upower"]["profile"], "performance")
        self.menu("zen-power", SELECT, "charge")
        self.assertFalse(self.load()["upower"]["ChargeThresholdEnabled"])

    def test_reboot_asks_first(self):
        options, rows = self.menu("zen-power", SELECT, "reboot")
        self.assertEqual(options["data"], "reboot")
        self.assertFalse([c for c in self.calls("niri") if "action" in c])


class TestDisplays(Zen):

    def test_main_and_caffeine(self):
        _o, rows = self.menu("zen-displays")
        self.assertTrue(rows[0][0].startswith("Caffeine"))
        self.menu("zen-displays", SELECT, "adj:caffeine:")
        self.assertIn("zen-caffeine.service", self.load()["systemd"]["active"])
        out = self.run_cmd(self.home / ".local/bin/zen-displays", "caffeine").stdout.strip()
        self.assertNotEqual(out, "")

    def test_caffeine_toggle_command(self):
        self.run_cmd(self.home / ".local/bin/zen-displays", "caffeine", "toggle")
        self.assertIn("zen-caffeine.service", self.load()["systemd"]["active"])
        self.run_cmd(self.home / ".local/bin/zen-displays", "caffeine", "toggle")
        self.assertEqual(self.load()["systemd"]["active"], ["zen-idle.service"])

    def test_brightness(self):
        self.menu("zen-displays", RIGHT, "adj:bright:eDP-1", "out:eDP-1")
        self.assertEqual(self.load()["brightness"], 60)

    def test_three_monitors(self):
        self.state["niri"]["outputs"] = json.loads((FIXTURES / "outputs.json").read_text())
        self.save()
        _o, rows = self.menu("zen-displays")
        self.assertTrue(any(t.startswith("Layouts") for t in self.texts(rows)))
        self.assertEqual(len([r for r in rows if r[1]["info"].startswith("view:out:")]), 3)


# ---------------------------------------------------------------- panel and tools


class TestPanel(Zen):

    def test_level_icons(self):
        for what in ("volume", "brightness"):
            path = Path(self.run_cmd(self.home / ".local/lib/zen/bar/level", what).stdout.strip())
            self.assertTrue(path.is_file(), what)

    def test_step(self):
        self.run_cmd(self.home / ".local/bin/zen-step", "volume", "up")
        self.assertEqual(self.load()["wp"]["volume"]["51"][0], 0.65)
        self.run_cmd(self.home / ".local/bin/zen-step", "brightness", "down")
        self.assertEqual(self.load()["brightness"], 45)

    def test_screen_off_and_on(self):
        screen = self.home / ".local/lib/zen/screen"
        self.run_cmd(screen, "off")
        self.assertEqual(self.load()["kbd"]["level"], 0)
        self.assertIn("niri msg action power-off-monitors", self.calls("niri"))
        self.run_cmd(screen, "on")
        self.assertEqual(self.load()["kbd"]["level"], 1)

    def test_lock(self):
        built = self.home / ".local/lib/gtklock"
        built.mkdir(parents=True)
        (built / "zen-module.so").write_text("")
        (built / "zen-module.built").write_text("5\n")
        self.run_cmd(self.home / ".local/bin/zen-lock")
        self.assertIn(f"gtklock -d -m powerbar-module -m {built}/zen-module.so", self.calls("gtklock"))
        self.assertEqual(self.calls("notify-send"), [])

    def test_screenshot(self):
        shots = self.home / "Pictures/Screenshots"
        shots.mkdir(parents=True)
        shot = shots / "Screenshot from 2026-11-09 12-50-01.png"
        shot.write_bytes(b"png")
        self.state["notify_action"] = "default"
        self.save()
        self.run_cmd(self.home / ".local/lib/zen/screenshot")
        for _x in range(50):
            if any("ShowItems" in c for c in self.calls("busctl")):
                break
            time.sleep(0.1)
        self.assertTrue(any(shot.name in c for c in self.calls("notify-send")))
        self.assertTrue(any(shot.as_uri() in c for c in self.calls("busctl")))
        self.run_cmd(self.home / ".local/lib/zen/screenshot")
        time.sleep(0.5)
        self.assertEqual(len(self.calls("notify-send")), 1)

    def test_shell_modules(self):
        for name in ("temp", "net", "tmux"):
            self.run_cmd(self.home / ".local/lib/zen/bar" / name)


class TestSwitcher(Zen):

    def wait_for(self, name, text):
        for _x in range(50):
            if any(text in c for c in self.calls(name)):
                return True
            time.sleep(0.1)
        return False

    def test_alt_digit_opens_another_menu(self):
        """Alt+5 (kb-custom-15, ROFI_RETV 24) in the power menu opens the sound menu."""
        _o, rows = self.menu("zen-power", 24, "balanced")
        self.assertTrue(self.wait_for("rofi", "zen-audio list"))

    def test_own_icon_does_nothing(self):
        self.menu("zen-power", 25, "balanced")
        time.sleep(0.5)
        self.assertEqual(self.calls("rofi"), [])

    def test_every_menu_takes_the_keys(self):
        for script in ("zen-center", "zen-audio", "zen-displays", "zen-clipboard", "zen-power"):
            options, _rows = self.menu(script)
            self.assertEqual(options.get("use-hot-keys"), "true", script)

    def test_theme(self):
        self.run_cmd(self.home / ".local/bin/zen", "apply", "--user")
        text = (self.home / ".config/rofi/zen-switcher.rasi").read_text()
        self.assertIn('action: "kb-custom-16"', text)
        for name in ("center", "audio", "displays", "clipboard", "power"):
            rasi = (self.home / f".config/rofi/{name}.rasi").read_text()
            self.assertIn("switcher", rasi, name)


class TestConfigs(Zen):

    def test_waybar_paths(self):
        """Every script the panel runs exists and is executable."""
        import re
        text = (self.home / ".config/waybar/config.jsonc").read_text()
        config = json.loads(re.sub(r"^\s*//.*$", "", text, flags=re.M))
        for name, module in config.items():
            if not isinstance(module, dict):
                continue
            for key, value in module.items():
                if isinstance(value, str) and value.startswith("~/"):
                    path = self.home / value.split()[0][2:]
                    self.assertTrue(os.access(path, os.X_OK), f"{name}.{key}: {value}")

    def test_niri_binds(self):
        import re
        text = (self.home / ".config/niri/config.kdl").read_text()
        for cmd in re.findall(r'spawn-sh "~/([^ "]+)', text):
            self.assertTrue(os.access(self.home / cmd, os.X_OK), cmd)


class TestTools(Zen):

    def test_apply_check(self):
        zen = self.home / ".local/bin/zen"
        res = self.run_cmd(zen, "apply", "--check", "--user", check=False)
        self.assertEqual(res.returncode, 1)
        self.assertFalse((self.home / ".config/mako/config").exists())
        self.run_cmd(zen, "apply", "--user")
        self.assertEqual(self.run_cmd(zen, "apply", "--check", "--user", check=False).returncode, 0)

    def test_gtklock_check(self):
        res = self.run_cmd(self.home / ".local/bin/zen", "gtklock", "--check", check=False)
        self.assertEqual(res.returncode, 1)

    def test_doctor(self):
        res = self.run_cmd(self.home / ".local/bin/zen", "doctor", check=False)
        for title in ("Services", "Lock screen", "Colours", "Panel modules", "Repository"):
            self.assertIn(title, res.stdout)
        self.assertIn("zen gtklock", res.stdout)
        self.assertEqual(res.returncode, 1)


class TestDeploy(Zen):

    def test_dry_run(self):
        res = self.run_cmd("sh", REPO / "deploy.sh", "--dry-run", "--no-packages", "--host", "zen")
        self.assertIn("zen apply", res.stdout)


if __name__ == "__main__":
    unittest.main()

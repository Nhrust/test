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
          "nmcli", "gsettings", "setvtrgb", "rofi", "playerctl", "gtklock", "pacman", "tailscale", "qrencode", "ip"]

INIT, SELECT, DELETE, ESC, LEFT, RIGHT, TAB = 0, 1, 3, 12, 13, 14, 15


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
        tmp = self.mock / "state.test.tmp"
        tmp.write_text(json.dumps(self.state))
        os.replace(tmp, self.mock / "state.json")

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
                           env={"ROFI_RETV": str(retv), "ROFI_INFO": info, "ROFI_DATA": data,
                                "ROFI_OUTSIDE": "1"})
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
        self.assertEqual((infos[0], infos[1], infos[-1]), ("back", "t0", "del"))
        self.assertEqual(rows[int(options["new-selection"])][1]["info"], "t0")

    def test_click_on_text_goes_to_the_app(self):
        options, _rows = self.menu("zen-center", SELECT, "h:11")
        self.menu("zen-center", SELECT, "t1", options["data"])
        _o, rows = self.menu("zen-center")
        self.assertNotIn("h:11", [r[1]["info"] for r in rows])
        self.assertEqual(self.calls("wl-copy"), [])

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
        self.run_cmd(self.home / ".local/bin/zen-center", "seen", "12")
        self.run_cmd(self.home / ".local/bin/zen-center", "seen", "11")
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

    def test_player_mute(self):
        """Middle click on the player: only its own sound goes quiet, by name..."""
        self.run_cmd(self.home / ".local/bin/zen-audio", "player-mute")
        self.assertFalse(self.volume(71)[1], "mpv was muted: the click brings it back")
        self.run_cmd(self.home / ".local/bin/zen-audio", "player-mute")
        self.assertTrue(self.volume(71)[1])
        self.assertFalse(self.volume(70)[1], "Firefox plays on")
        self.assertFalse(self.volume(51)[1], "the output stays on")

    def test_player_mute_by_process(self):
        """...or by process: a browser plays from a process it started."""
        self.state["player"].update({"name": "chromium", "instance": "chromium.instance77", "pid": os.getpid()})
        self.state["wp"]["nodes"]["70"]["application.process.id"] = os.getpid()
        self.save()
        self.run_cmd(self.home / ".local/bin/zen-audio", "player-mute")
        self.assertTrue(self.volume(70)[1])
        self.assertTrue(self.volume(71)[1], "mpv (muted before) is not touched")

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
        self.assertFalse(self.calls("notify-send"), "a connection that worked is not told")
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


class TestNetwork(Zen):

    def setUp(self):
        super().setUp()
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from mock import new_conn, WIFI, WIRED
        home = new_conn("u-home", "Home", WIFI, psk="hunter2", device="wlan0")
        work = new_conn("u-work", "Work", WIFI, psk="w0rk")
        wired = new_conn("u-wired", "Wired connection 1", WIRED)
        self.state["nm"] = {
            "wifi": True, "cable": False,
            "devices": [["wlan0", "wifi"], ["enp1s0", "ethernet"]],
            "conns": [home, work, wired],
            "aps": [{"ssid": "Home", "signal": 82, "security": "WPA2", "freq": "5180 MHz", "chan": 36},
                    {"ssid": "Cafe: free", "signal": 40, "security": "", "freq": "2412 MHz", "chan": 1},
                    {"ssid": "Neighbour", "signal": 55, "security": "WPA3", "freq": "2437 MHz", "chan": 6},
                    {"ssid": "Home", "signal": 30, "security": "WPA2", "freq": "2462 MHz", "chan": 11}],
            "passwords": {"Neighbour": "secret", "Attic": "upstairs"},
            "ip": {"wlan0": {"IP4.ADDRESS": ["192.168.1.23/24"], "IP4.GATEWAY": ["192.168.1.1"],
                             "IP4.DNS": ["192.168.1.1"],
                             "IP6.ADDRESS": ["fd00::23/64", "fe80::1/64"]}}}
        self.state["tailscale"] = {
            "BackendState": "Running",
            "Peer": {"nodekey:a": {"HostName": "localhost", "DNSName": "nas.tail1234.ts.net.", "OS": "linux",
                                   "TailscaleIPs": ["100.64.0.2", "fd7a:115c:a1e0::2"], "Online": True,
                                   "ExitNodeOption": True, "ExitNode": False},
                     "nodekey:b": {"HostName": "phone", "DNSName": "phone.tail1234.ts.net.", "OS": "android",
                                   "TailscaleIPs": ["100.64.0.3"], "Online": False,
                                   "LastSeen": "2026-11-08T21:14:00Z"}}}
        self.save()

    def wait_for(self, check):
        for _x in range(50):
            if check(self.load()):
                return True
            time.sleep(0.1)
        return False

    def idle(self):
        """Wait for the background work of the menu to finish."""
        for _x in range(100):
            if not (self.run_dir / "zen-network-busy").exists():
                return
            time.sleep(0.1)
        self.fail("the network menu stayed busy")

    def conn(self, uuid):
        return next(c for c in self.load()["nm"]["conns"] if c["uuid"] == uuid)

    def wifi_active(self, st):
        return next((c["name"] for c in st["nm"]["conns"] if c["type"] == "802-11-wireless" and c["device"]), None)

    def infos(self, rows):
        return [r[1]["info"] for r in rows]

    def test_main(self):
        options, rows = self.menu("zen-network")
        texts = self.texts(rows)
        self.assertEqual(texts[0], "Wi-Fi · ‹ on ›")
        self.assertTrue(texts[1].startswith("Home · connected"))
        self.assertIn("view:saved", self.infos(rows))
        self.assertTrue(any(t.startswith("Ethernet · not connected") for t in texts))
        self.assertTrue(any(t.startswith("Devices · 1/2") for t in texts))
        self.assertTrue(any(t.startswith("Exit node · none") for t in texts))
        self.assertIn("5 GHz · 82%", options["message"])
        self.assertIn("1 device online", options["message"])
        self.assertNotIn("Ethernet", options["message"], "no cable: the row says it")
        self.assertNotIn("100.64", "".join(texts) + options["message"])

    def test_networks(self):
        options, rows = self.menu("zen-network", SELECT, "view:wifi", "main")
        infos = self.infos(rows)
        self.assertEqual(infos[:3], ["view:main", "rescan", "hidden"])
        # one row per name, the connected one first, the colon in a name survives
        self.assertEqual(infos[3:], ["net:Home", "net:Neighbour", "net:Cafe: free"])
        self.assertEqual(rows[int(options["new-selection"])][1]["info"], "net:Home")
        self.menu("zen-network", SELECT, "rescan", "wifi")
        self.assertEqual(self.load()["nm"]["scans"], 1)

    def test_open_network(self):
        self.menu("zen-network", SELECT, "net:Cafe: free", "wifi")
        self.assertTrue(self.wait_for(lambda st: self.wifi_active(st) == "Cafe: free"))
        self.idle()
        self.assertFalse(self.calls("notify-send"), "the panel shows the connection")
        self.assertFalse(self.calls("rofi"))

    def test_password(self):
        """A new network with a password asks for it; the password never shows in the arguments."""
        self.state["rofi_input"] = "secret"
        self.save()
        options, rows = self.menu("zen-network", SELECT, "net:Neighbour", "wifi")
        self.assertEqual(rows, [], "the menu closes for the prompt")
        self.assertTrue(self.wait_for(lambda st: self.wifi_active(st) == "Neighbour"))
        self.assertTrue(any("-password" in c for c in self.calls("rofi")))
        self.assertFalse(any("secret" in c for c in self.calls()))

    def test_wrong_password(self):
        self.state["rofi_input"] = "wrong"
        self.save()
        self.menu("zen-network", SELECT, "net:Neighbour", "wifi")
        for _x in range(50):
            if any("Could not connect" in c for c in self.calls("notify-send")):
                break
            time.sleep(0.1)
        self.assertTrue(any("Could not connect: Neighbour" in c for c in self.calls("notify-send")))
        self.assertEqual(self.wifi_active(self.load()), "Home")

    def test_cancelled_password(self):
        self.menu("zen-network", SELECT, "net:Neighbour", "wifi")
        for _x in range(30):
            if self.calls("rofi"):
                break
            time.sleep(0.1)
        time.sleep(0.3)
        self.assertFalse(any("wifi connect" in c for c in self.calls("nmcli")))
        self.assertFalse((self.run_dir / "zen-network-busy").exists())

    def test_hidden_network(self):
        self.state["rofi_input"] = ["Attic", "upstairs"]
        self.save()
        _o, rows = self.menu("zen-network", SELECT, "hidden", "wifi")
        self.assertEqual(rows, [])
        self.assertTrue(self.wait_for(lambda st: self.wifi_active(st) == "Attic"))
        self.assertEqual(self.conn("Attic")["props"]["802-11-wireless.hidden"], "yes")
        self.assertFalse(any("upstairs" in c for c in self.calls()))

    def test_wifi_toggle(self):
        options, rows = self.menu("zen-network", RIGHT, "adj:wifi", "main")
        self.assertEqual(self.texts(rows)[0], "Wi-Fi · ‹ off ›")
        self.assertFalse(self.load()["nm"]["wifi"])
        self.assertIn("Wi-Fi is off", options["message"])
        self.run_cmd(self.home / ".local/bin/zen-network", "wifi", "toggle")
        self.assertTrue(self.load()["nm"]["wifi"])

    def test_details(self):
        options, rows = self.menu("zen-network", SELECT, "view:dev:wlan0", "main")
        infos = self.infos(rows)
        self.assertIn("copy:192.168.1.23", infos)
        self.assertIn("copy:fd00::23", infos)
        self.assertNotIn("copy:fe80::1", infos)
        self.assertIn("view:conn:u-home", infos)
        self.assertIn("forget:u-home", infos)
        self.assertEqual(rows[int(options["new-selection"])][1]["info"], "copy:Home")
        _o, rows = self.menu("zen-network", SELECT, "copy:192.168.1.23", "dev:wlan0")
        self.assertEqual((self.mock / "clipboard.txt").read_text(), "192.168.1.23")
        # no notification: the row says it, until the next step
        self.assertIn("IPv4 · 192.168.1.23/24 · copied", self.texts(rows))
        self.assertFalse(self.calls("notify-send"))
        _o, rows = self.menu("zen-network", RIGHT, "copy:192.168.1.23", "dev:wlan0")
        self.assertIn("IPv4 · 192.168.1.23/24", self.texts(rows))
        _o, rows = self.menu("zen-network", SELECT, "forget:u-home", "dev:wlan0")
        self.assertNotIn("u-home", [c["uuid"] for c in self.load()["nm"]["conns"]])
        self.assertEqual(_o["data"], "main")

    def test_settings(self):
        options, rows = self.menu("zen-network", SELECT, "view:conn:u-home", "dev:wlan0")
        texts = self.texts(rows)
        self.assertEqual(self.infos(rows)[0], "view:dev:wlan0")
        self.assertIn("Connect automatically · ‹ on ›", texts)
        self.assertIn("Metered · ‹ no ›", texts)
        self.assertIn("MAC address · ‹ permanent ›", texts)
        self.assertIn("Password · ••••••••  ›", texts)
        self.assertIn("DNS · automatic  ›", texts)
        self.assertIn("DNS over TLS · ‹ off ›", texts)
        self.assertIn("IPv4 · automatic  ›", texts)
        self.assertNotIn("activate:u-home", self.infos(rows), "it is connected already")
        self.assertNotIn("hunter2", "".join(texts))
        self.menu("zen-network", RIGHT, "adj:auto:u-home", "conn:u-home")
        self.menu("zen-network", SELECT, "adj:metered:u-home", "conn:u-home")
        self.menu("zen-network", LEFT, "adj:dot:u-home", "conn:u-home")
        _o, rows = self.menu("zen-network", RIGHT, "adj:mac:u-home", "conn:u-home")
        p = self.conn("u-home")["props"]
        self.assertEqual(p["connection.autoconnect"], "no")
        self.assertEqual(p["connection.metered"], "yes")
        self.assertEqual(p["connection.dns-over-tls"], "yes")
        self.assertEqual(p["802-11-wireless.cloned-mac-address"], "stable")
        self.assertIn("MAC address · ‹ own for this network ›", self.texts(rows))
        self.assertTrue(any(c.startswith("nmcli device reapply wlan0") for c in self.calls("nmcli")))
        # a new MAC address reconnects
        self.assertTrue(self.wait_for(lambda st: any("connection up uuid u-home" in c
                                                     for c in self.calls("nmcli"))))
        options, _rows = self.menu("zen-network", ESC, "", "conn:u-home")
        self.assertEqual(options["data"], "dev:wlan0")

    def test_saved(self):
        _o, rows = self.menu("zen-network", SELECT, "view:saved", "main")
        self.assertEqual(self.infos(rows), ["view:main", "view:conn:u-home", "view:conn:u-work"])
        _o, rows = self.menu("zen-network", SELECT, "view:conn:u-work", "saved")
        self.assertEqual(self.infos(rows)[:2], ["view:saved", "activate:u-work"])
        _o, rows = self.menu("zen-network", SELECT, "forget:u-work", "conn:u-work")
        self.assertEqual(_o["data"], "saved")
        self.assertEqual(self.infos(rows), ["view:main", "view:conn:u-home"])

    def test_password_view(self):
        _o, rows = self.menu("zen-network", SELECT, "view:pw:u-home", "conn:u-home")
        self.assertNotIn("hunter2", "".join(self.texts(rows)))
        options, rows = self.menu("zen-network", SELECT, "reveal:u-home", "pw:u-home")
        self.assertEqual(options["data"], "pwshow:u-home")
        self.assertIn("Password · hunter2", self.texts(rows))
        options, _rows = self.menu("zen-network", ESC, "", "pwshow:u-home")
        self.assertEqual(options["data"], "conn:u-home")
        self.menu("zen-network", SELECT, "copypw:u-home", "pw:u-home")
        self.assertEqual((self.mock / "clipboard.txt").read_text(), "hunter2")
        self.assertIn("wl-copy --sensitive", self.calls("wl-copy"))
        self.assertFalse(any("hunter2" in c for c in self.calls()), "not in arguments or notifications")

    def test_qr(self):
        _o, rows = self.menu("zen-network", SELECT, "qr:u-home", "pw:u-home")
        self.assertEqual(rows, [])
        self.assertTrue(self.wait_for(lambda st: any(" -e " in c for c in self.calls("rofi"))))
        self.assertEqual((self.mock / "qr.txt").read_text(), "WIFI:T:WPA;S:Home;P:hunter2;;")
        # the menu comes back on the password view
        self.assertTrue(self.wait_for(lambda st: any("zen-network list" in c for c in self.calls("rofi"))))
        self.assertFalse(any("hunter2" in c for c in self.calls()))

    def test_change_password(self):
        self.state["rofi_input"] = ["n3w pass"]
        self.save()
        self.menu("zen-network", SELECT, "psk:u-home", "pw:u-home")
        self.assertTrue(self.wait_for(lambda st: self.conn("u-home")["psk"] == "n3w pass"))
        self.assertFalse(any("n3w" in c for c in self.calls()))

    def test_dns(self):
        _o, rows = self.menu("zen-network", SELECT, "view:dns:u-home", "conn:u-home")
        self.assertEqual([r[0] for r in rows if r[1].get("active")], ["Automatic · from the network"])
        _o, rows = self.menu("zen-network", SELECT, "dns:quad9:u-home", "dns:u-home")
        p = self.conn("u-home")["props"]
        self.assertEqual(p["ipv4.dns"], "9.9.9.9,149.112.112.112")
        self.assertEqual(p["ipv4.ignore-auto-dns"], "yes")
        self.assertEqual(p["ipv6.dns"], "2620:fe::fe,2620:fe::9")
        self.assertTrue([r[0] for r in rows if r[1].get("active")][0].startswith("Quad9"))
        self.state = self.load()
        self.state["rofi_input"] = ["8.8.8.8, 2001:4860:4860::8888"]
        self.save()
        self.menu("zen-network", SELECT, "dns:custom:u-home", "dns:u-home")
        self.assertTrue(self.wait_for(lambda st: self.conn("u-home")["props"]["ipv4.dns"] == "8.8.8.8"))
        self.assertEqual(self.conn("u-home")["props"]["ipv6.dns"], "2001:4860:4860::8888")
        _o, rows = self.menu("zen-network", SELECT, "view:conn:u-home", "dev:wlan0")
        self.assertIn("DNS · 8.8.8.8, 2001:4860:4860::8888  ›", self.texts(rows))
        self.menu("zen-network", SELECT, "dns:auto:u-home", "dns:u-home")
        p = self.conn("u-home")["props"]
        self.assertEqual((p["ipv4.dns"], p["ipv4.ignore-auto-dns"]), ("", "no"))

    def test_ipv4_manual(self):
        _o, rows = self.menu("zen-network", RIGHT, "adj:ip4m:u-home", "ip4:u-home")
        p = self.conn("u-home")["props"]
        self.assertEqual((p["ipv4.method"], p["ipv4.addresses"], p["ipv4.gateway"]),
                         ("manual", "192.168.1.23/24", "192.168.1.1"))
        self.assertIn("ip4addr:u-home", self.infos(rows))
        self.state = self.load()
        self.state["rofi_input"] = ["192.168.1.50"]
        self.save()
        self.menu("zen-network", SELECT, "ip4addr:u-home", "ip4:u-home")
        self.assertTrue(self.wait_for(lambda st: self.conn("u-home")["props"]["ipv4.addresses"] ==
                                      "192.168.1.50/24"))
        self.menu("zen-network", LEFT, "adj:ip4m:u-home", "ip4:u-home")
        p = self.conn("u-home")["props"]
        self.assertEqual((p["ipv4.method"], p["ipv4.addresses"]), ("auto", ""))

    def test_ipv6_off(self):
        self.menu("zen-network", SELECT, "dns:cloudflare:u-home", "dns:u-home")
        self.menu("zen-network", LEFT, "adj:ip6m:u-home", "ip6:u-home")
        p = self.conn("u-home")["props"]
        self.assertEqual((p["ipv6.method"], p["ipv6.dns"]), ("disabled", ""))
        _o, rows = self.menu("zen-network", SELECT, "view:conn:u-home", "dev:wlan0")
        self.assertIn("IPv6 · off  ›", self.texts(rows))
        self.menu("zen-network", RIGHT, "adj:ip6m:u-home", "ip6:u-home")
        p = self.conn("u-home")["props"]
        self.assertEqual((p["ipv6.method"], p["ipv6.ignore-auto-dns"]), ("auto", "yes"))

    def test_refused_change(self):
        self.state["nm"]["refuse"] = ["connection.metered"]
        self.save()
        self.menu("zen-network", SELECT, "adj:metered:u-home", "conn:u-home")
        self.assertTrue(any("Could not change the settings" in c for c in self.calls("notify-send")))

    def test_opens_on_a_view(self):
        res = self.run_cmd(self.home / ".local/bin/zen-network", "list",
                           env={"ROFI_RETV": "0", "ZEN_MENU_VIEW": "dns:u-home"})
        self.assertIn("\0data\x1fdns:u-home", res.stdout)

    def test_hotspot(self):
        _o, rows = self.menu("zen-network")
        self.assertIn("view:hotspot", self.infos(rows))
        # the first visit saves the hotspot with the computer's name and a new password
        _o, rows = self.menu("zen-network", SELECT, "view:hotspot", "main")
        hs = self.conn("u-zen-hotspot")
        self.assertEqual(hs["ifname"], "ap0")
        self.assertEqual(hs["props"]["802-11-wireless.mode"], "ap")
        self.assertEqual(hs["props"]["ipv4.method"], "shared")
        self.assertRegex(hs["psk"], r"^[a-z2-9]{4}-[a-z2-9]{4}-[a-z2-9]{4}$")
        self.assertFalse(any(hs["psk"] in c for c in self.calls()))
        self.assertEqual(self.texts(rows)[1], "Hotspot · ‹ off ›")
        self.assertIn("view:pw:u-zen-hotspot", self.infos(rows))
        # on: the interface, then the hotspot on the channel Wi-Fi uses
        self.menu("zen-network", RIGHT, "adj:hotspot", "hotspot")
        self.assertTrue(self.wait_for(lambda st: next(c for c in st["nm"]["conns"]
                                                      if c["uuid"] == "u-zen-hotspot")["device"] == "ap0"))
        self.idle()
        p = self.conn("u-zen-hotspot")["props"]
        self.assertEqual((p["802-11-wireless.band"], p["802-11-wireless.channel"]), ("a", "36"))
        # WPA2 alone: phones refuse a hotspot that also offers WPA with TKIP
        self.assertEqual((p["802-11-wireless-security.proto"], p["802-11-wireless-security.pairwise"],
                          p["802-11-wireless-security.group"]), ("rsn", "ccmp", "ccmp"))
        self.assertIn("systemctl start zen-hotspot.service", self.calls("systemctl"))
        options, rows = self.menu("zen-network", INIT, "", "hotspot")
        self.assertEqual(self.texts(rows)[1], "Hotspot · ‹ on ›")
        self.assertIn("\U000F0003", options["message"])
        # ap0 is not a second Wi-Fi of this computer
        _o, rows = self.menu("zen-network")
        self.assertEqual(self.texts(rows)[0], "Wi-Fi · ‹ on ›")
        self.assertNotIn("view:dev:ap0", self.infos(rows))
        _o, rows = self.menu("zen-network", SELECT, "view:saved", "main")
        self.assertNotIn("view:conn:u-zen-hotspot", self.infos(rows))
        # its password view goes back to the hotspot
        options, _rows = self.menu("zen-network", ESC, "", "pw:u-zen-hotspot")
        self.assertEqual(options["data"], "hotspot")
        self.menu("zen-network", LEFT, "adj:hotspot", "hotspot")
        self.assertTrue(self.wait_for(lambda st: ["ap0", "wifi"] not in st["nm"]["devices"]))
        self.idle()
        self.assertFalse(self.calls("notify-send"), "on and off show in the menu and the panel")
        self.assertEqual(self.conn("u-zen-hotspot")["device"], "")

    def hotspot_on(self, neigh=()):
        self.state["neigh"] = list(neigh)
        self.save()
        self.menu("zen-network", SELECT, "view:hotspot", "main")
        self.menu("zen-network", SELECT, "adj:hotspot", "hotspot")
        self.assertTrue(self.wait_for(lambda st: (st.get("guard") or {}).get("applied") is not None))
        self.idle()

    def guard(self):
        return self.load()["guard"]

    def test_hotspot_rules(self):
        """The settings go to the root helper when the hotspot starts and when they change."""
        phone = {"dst": "10.42.0.23", "lladdr": "0a:1b:2c:3d:4e:5f", "state": ["REACHABLE"]}
        self.hotspot_on([phone])
        self.assertEqual(self.guard()["applied"], {"mode": "all", "rate_total": 0, "rate_device": 0,
                                                   "quota_mb": 0, "blocked": [], "allowed": []})
        self.menu("zen-network", RIGHT, "adj:hs:rate_total", "hotspot")
        self.menu("zen-network", RIGHT, "adj:hs:rate_device", "hotspot")
        self.menu("zen-network", RIGHT, "adj:hs:rate_device", "hotspot")
        self.menu("zen-network", LEFT, "adj:hs:quota_mb", "hotspot")
        _o, rows = self.menu("zen-network", RIGHT, "adj:hs:mode", "hotspot")
        g = self.guard()["applied"]
        self.assertEqual((g["rate_total"], g["rate_device"], g["quota_mb"], g["mode"]), (5, 10, 10240, "known"))
        texts = self.texts(rows)
        self.assertIn("Access · ‹ only your devices ›", texts)
        self.assertIn("Speed for all · ‹ 5 Mbit/s ›", texts)
        self.assertIn("Traffic per device · ‹ 10 GB ›", texts)
        self.assertIn("view:hsallowed", self.infos(rows))
        saved_cfg = json.loads((self.home / ".local/state/zen/hotspot.json").read_text())
        self.assertEqual(saved_cfg["rate_device"], 10)

    def test_hotspot_devices(self):
        phone = {"dst": "10.42.0.23", "lladdr": "0a:1b:2c:3d:4e:5f", "state": ["REACHABLE"]}
        self.hotspot_on([phone])
        self.state = self.load()
        self.state["guard"]["usage"] = {"10.42.0.23": 157286400}
        self.save()
        _o, rows = self.menu("zen-network", SELECT, "view:hsdevs", "hotspot")
        self.assertEqual(self.texts(rows)[1], "10.42.0.23 · 150 MB  ›")
        _o, rows = self.menu("zen-network", SELECT, "view:hsdev:0a:1b:2c:3d:4e:5f", "hsdevs")
        self.assertIn("copy:0a:1b:2c:3d:4e:5f", self.infos(rows))
        # the blocklist: kept, given to the helper, and the device is sent off the air
        _o, rows = self.menu("zen-network", SELECT, "block:0a:1b:2c:3d:4e:5f", "hsdev:0a:1b:2c:3d:4e:5f")
        self.assertEqual(self.guard()["applied"]["blocked"], ["0a:1b:2c:3d:4e:5f"])
        self.assertEqual(self.guard()["kicked"], ["0a:1b:2c:3d:4e:5f"])
        self.assertIn("unblock:0a:1b:2c:3d:4e:5f", self.infos(rows))
        _o, rows = self.menu("zen-network", SELECT, "view:hsdevs", "hotspot")
        self.assertTrue(self.texts(rows)[1].endswith("blocked  ›"))
        _o, rows = self.menu("zen-network", SELECT, "view:hsblocked", "hotspot")
        self.assertEqual(self.infos(rows)[2], "unblock:0a:1b:2c:3d:4e:5f")
        self.menu("zen-network", SELECT, "unblock:0a:1b:2c:3d:4e:5f", "hsblocked")
        self.assertEqual(self.guard()["applied"]["blocked"], [])
        # your own device, for the "only your devices" access
        self.menu("zen-network", RIGHT, "adj:hsown:0a:1b:2c:3d:4e:5f", "hsdev:0a:1b:2c:3d:4e:5f")
        self.assertEqual(self.guard()["applied"]["allowed"], ["0a:1b:2c:3d:4e:5f"])
        options, _rows = self.menu("zen-network", ESC, "", "hsdev:0a:1b:2c:3d:4e:5f")
        self.assertEqual(options["data"], "hsdevs")
        self.menu("zen-network", SELECT, "kick:0a:1b:2c:3d:4e:5f", "hsdev:0a:1b:2c:3d:4e:5f")
        self.assertEqual(self.guard()["kicked"], ["0a:1b:2c:3d:4e:5f"] * 2)

    def test_hotspot_settings_while_off(self):
        """Changes while the hotspot is off are only saved; the helper gets them at the start."""
        self.menu("zen-network", SELECT, "view:hotspot", "main")
        self.menu("zen-network", RIGHT, "adj:hs:quota_mb", "hotspot")
        self.assertNotIn("guard", self.load())
        self.hotspot_on()
        self.assertEqual(self.guard()["applied"]["quota_mb"], 500)

    def test_stale_busy_mark(self):
        """A mark left by background work that died does not hold the menu forever."""
        busy = self.run_dir / "zen-network-busy"
        busy.write_text("zen-hotspot")
        os.utime(busy, (time.time() - 600, time.time() - 600))
        _o, rows = self.menu("zen-network", SELECT, "view:hotspot", "main")
        self.assertEqual(self.texts(rows)[1], "Hotspot · ‹ off ›")
        self.assertFalse(busy.exists())

    def test_hotspot_radar_channel(self):
        self.state["nm"]["aps"][0]["chan"] = 100
        self.state["nm"]["aps"][0]["freq"] = "5500 MHz"
        self.save()
        self.menu("zen-network", SELECT, "view:hotspot", "main")
        self.menu("zen-network", SELECT, "adj:hotspot", "hotspot")
        for _x in range(50):
            if any("cannot start on channel 100" in c for c in self.calls("notify-send")):
                break
            time.sleep(0.1)
        self.assertTrue(any("cannot start on channel 100" in c for c in self.calls("notify-send")))
        self.assertNotIn("systemctl start zen-hotspot.service", self.calls("systemctl"))

    def test_hotspot_refused(self):
        self.state["systemd"]["deny"] = ["zen-hotspot.service"]
        self.save()
        self.menu("zen-network", SELECT, "view:hotspot", "main")
        self.menu("zen-network", SELECT, "adj:hotspot", "hotspot")
        for _x in range(50):
            if any("Could not start the hotspot" in c for c in self.calls("notify-send")):
                break
            time.sleep(0.1)
        self.assertTrue(any("Access denied" in c for c in self.calls("notify-send")))

    def test_devices(self):
        """The list shows names and state; the address appears only inside a device."""
        _o, rows = self.menu("zen-network", SELECT, "view:ts", "main")
        self.assertEqual(self.infos(rows), ["view:main", "view:peer:nodekey:a", "view:peer:nodekey:b"])
        self.assertTrue(self.texts(rows)[1].startswith("nas · "), "the MagicDNS name, not the host name")
        self.assertNotIn("100.64", "".join(self.texts(rows)))
        _o, rows = self.menu("zen-network", SELECT, "view:peer:nodekey:a", "ts")
        infos = self.infos(rows)
        self.assertEqual(infos[0], "view:ts")
        self.assertIn("copy:100.64.0.2", infos)
        self.assertIn("copy:nas.tail1234.ts.net", infos)
        self.menu("zen-network", SELECT, "exit:100.64.0.2", "peer:nodekey:a")
        self.assertTrue(self.load()["tailscale"]["Peer"]["nodekey:a"]["ExitNode"])
        options, _rows = self.menu("zen-network", ESC, "", "peer:nodekey:a")
        self.assertEqual(options["data"], "ts")
        _o, rows = self.menu("zen-network", SELECT, "view:peer:nodekey:b", "ts")
        self.assertTrue(any("2026-11-08 21:14" in t for t in self.texts(rows)))

    def test_tailscale_toggle(self):
        _o, rows = self.menu("zen-network", SELECT, "adj:ts", "main")
        self.assertEqual(self.load()["tailscale"]["BackendState"], "Stopped")
        self.assertFalse(any(t.startswith("Devices") for t in self.texts(rows)))

    def test_without_tailscale_and_wifi(self):
        self.state.pop("tailscale")
        self.state["nm"]["devices"] = [["enp1s0", "ethernet"]]
        self.state["nm"]["cable"] = True
        self.state["nm"]["conns"][0]["device"] = ""
        self.state["nm"]["conns"][2]["device"] = "enp1s0"
        self.save()
        _o, rows = self.menu("zen-network")
        self.assertEqual(self.texts(rows), ["Ethernet · connected  ›"])
        _o, rows = self.menu("zen-network", SELECT, "view:dev:enp1s0", "main")
        self.assertIn("view:conn:u-wired", self.infos(rows))
        _o, rows = self.menu("zen-network", SELECT, "view:conn:u-wired", "dev:enp1s0")
        self.assertNotIn("view:pw:u-wired", self.infos(rows))
        self.menu("zen-network", RIGHT, "adj:mac:u-wired", "conn:u-wired")
        self.assertEqual(self.conn("u-wired")["props"]["802-3-ethernet.cloned-mac-address"], "stable")


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
        for script in ("zen-center", "zen-audio", "zen-displays", "zen-clipboard", "zen-power", "zen-network",
                       "zen-vitals"):
            options, _rows = self.menu(script)
            self.assertEqual(options.get("use-hot-keys"), "true", script)

    def test_theme(self):
        self.run_cmd(self.home / ".local/bin/zen", "apply", "--user")
        text = (self.home / ".config/rofi/zen-switcher.rasi").read_text()
        self.assertIn('action: "kb-custom-16"', text)
        for name in ("center", "audio", "displays", "clipboard", "power", "network", "vitals"):
            rasi = (self.home / f".config/rofi/{name}.rasi").read_text()
            self.assertIn("switcher", rasi, name)


class TestVitals(Zen):
    """The monitoring modules: chosen in a menu, kept in zen.conf, made into panel files."""

    def conf(self):
        return (self.home / ".config/zen/zen.conf").read_text()

    def keys(self, rows):
        return [r[1]["info"][4:] for r in rows if r[1].get("active")]

    def test_sections(self):
        """On the panel first, then what can be added under the name of its group."""
        _o, rows = self.menu("zen-vitals")
        options, rows = self.menu("zen-vitals")
        titles = [r[0] for r in rows if r[1].get("nonselectable")]
        self.assertIn("On the panel", options["message"])
        self.assertEqual(rows[0][1]["info"], "key:cpu", "the list starts with a module, not a title")
        self.assertTrue(any("Processor" in t for t in titles))
        self.assertFalse(any("foreground" in t for t in titles), "a colour would not read on the highlight")
        self.assertIn("\u2003frequency · ‹ off ›", self.texts(rows))

    def test_default(self):
        options, rows = self.menu("zen-vitals")
        self.assertEqual(self.keys(rows), ["cpu", "gpu", "memory", "temp", "speed"])
        self.assertIn("5 of 6", options["message"])
        self.assertEqual(rows[-1][1]["info"], "reset")

    def test_switch_and_move(self):
        self.menu("zen-vitals", SELECT, "key:gpu")
        _o, rows = self.menu("zen-vitals", RIGHT, "key:uptime")
        self.assertEqual(self.keys(rows), ["cpu", "memory", "temp", "speed", "uptime"])
        _o, rows = self.menu("zen-vitals", 15, "key:uptime")  # Alt+Up
        self.assertEqual(self.keys(rows), ["cpu", "memory", "temp", "uptime", "speed"])
        self.menu("zen-vitals", 16, "key:speed")  # Alt+Down on the last: stays
        self.assertIn("vitals = cpu, memory, temp, uptime, speed", self.conf())
        # the panel files follow when the menu closes (its launcher runs zen apply then)
        self.assertFalse((self.home / ".config/waybar/zen-vitals.jsonc").exists(), "no reload at each step")
        self.run_cmd(self.home / ".local/lib/zen/apply", "--user")
        made = json.loads((self.home / ".config/waybar/zen-vitals.jsonc").read_text().split("\n", 1)[1])
        self.assertEqual(made["modules-left"], ["custom/apps", "niri/workspaces", "custom/gap-l1", "cpu", "memory",
                                                "custom/temp", "custom/uptime", "custom/speed", "custom/gap-l2"])
        self.assertEqual(made["custom/uptime"]["on-click-right"], "~/.local/bin/zen-vitals")
        css = (self.home / ".config/waybar/zen-vitals.css").read_text()
        self.assertIn("#memory,\n#custom-temp,\n#custom-uptime,\n#custom-speed {\n    border-left", css)

    def test_at_most_six(self):
        for key in ("uptime", "upload", "disk"):
            _o, rows = self.menu("zen-vitals", SELECT, f"key:{key}")
        self.assertEqual(len(self.keys(rows)), 6)
        self.assertNotIn("disk", self.keys(rows))
        options, rows = self.menu("zen-vitals", SELECT, "reset")
        self.assertEqual(self.keys(rows), ["cpu", "gpu", "memory", "temp", "speed"])

    def test_keeps_the_rest_of_zen_conf(self):
        conf = self.home / ".config/zen/zen.conf"
        conf.write_text("# mine\n[general]\nlocale = ru_RU.UTF-8\n\n[weather]\nlocation = Moscow\n")
        self.menu("zen-vitals", SELECT, "key:fan")
        text = conf.read_text()
        self.assertTrue(text.startswith("# mine\n[general]\nlocale = ru_RU.UTF-8\n\n[weather]\nlocation = Moscow\n"))
        self.assertIn("[panel]", text)
        self.menu("zen-vitals", SELECT, "key:fan")
        self.assertEqual(conf.read_text().count("vitals ="), 1)

    def test_every_module(self):
        """Each module in the list makes a panel entry whose script exists."""
        keys = ["cpu", "cpufreq", "load", "gpu", "vram", "memory", "mempct", "swap", "temp", "tempcpu",
                "tempgpu", "tempnvme", "fan", "speed", "upload", "disk", "diskio", "power", "uptime"]
        conf = self.home / ".config/zen/zen.conf"
        for i in range(0, len(keys), 6):
            conf.write_text(f"[panel]\nvitals = {', '.join(keys[i:i + 6])}\n")
            self.run_cmd(self.home / ".local/lib/zen/apply", "--user")
            made = json.loads((self.home / ".config/waybar/zen-vitals.jsonc").read_text().split("\n", 1)[1])
            self.assertEqual(len(made["modules-left"]), len(keys[i:i + 6]) + 4)
            for name in made["modules-left"][3:-1]:
                command = made[name].get("exec")
                if command:
                    self.assertTrue(os.access(self.home / command.split()[0][2:], os.X_OK), command)

    def test_scripts(self):
        for script in ("temp", "vram", "fan", "power", "uptime"):
            path = self.home / ".local/lib/zen/bar" / script
            res = self.run_cmd(path)
            self.assertEqual(res.returncode, 0, script)
        self.assertRegex(self.run_cmd(self.home / ".local/lib/zen/bar/uptime").stdout, r"^\d+(d|h|m)")


class TestResize(Zen):
    """Mod+Alt+arrows move the border between the focused window and its neighbour."""

    def layout(self, *wins):
        self.state["niri"]["windows"] = [
            {"id": i, "is_focused": f, "workspace_id": ws, "layout": {"pos_in_scrolling_layout": pos}}
            for i, f, ws, pos in wins]
        self.save()

    def actions(self, way):
        self.run_cmd(self.home / ".local/lib/zen/resize", way)
        return [c for c in self.calls("niri") if " action " in c]

    def test_between_columns(self):
        # focused column 1 of two: right grows it, the second loses as much
        self.layout((1, True, 7, [1, 1]), (2, False, 7, [2, 1]), (3, False, 8, [2, 1]))
        self.assertEqual(self.actions("right"), ["niri msg action set-window-width --id 1 +5%",
                                                 "niri msg action set-window-width --id 2 -5%",
                                                 "niri msg action focus-window --id 2",
                                                 "niri msg action focus-window --id 1"])

    def test_last_column_uses_the_border_before_it(self):
        self.layout((1, False, 7, [1, 1]), (2, True, 7, [2, 1]))
        self.assertEqual(self.actions("left"), ["niri msg action set-window-width --id 2 +5%",
                                                "niri msg action set-window-width --id 1 -5%",
                                                "niri msg action focus-window --id 1",
                                                "niri msg action focus-window --id 2"])

    def test_within_a_column(self):
        self.layout((1, True, 7, [1, 1]), (2, False, 7, [1, 2]))
        self.assertEqual(self.actions("up"), ["niri msg action set-window-height --id 1 -5%",
                                              "niri msg action set-window-height --id 2 +5%",
                                              "niri msg action focus-window --id 2",
                                              "niri msg action focus-window --id 1"])

    def test_alone_or_floating(self):
        self.layout((1, True, 7, [1, 1]), (2, False, 8, [2, 1]))
        self.assertEqual(self.actions("right"), [])
        self.layout((1, True, 7, None), (2, False, 7, [1, 1]))
        self.assertEqual(self.actions("right"), [])


class TestAutowidth(unittest.TestCase):
    """The window-layout daemon: stacks (Mod+[ / ]) next to the old pair logic."""
    W = 1920

    def setUp(self):
        sys.dont_write_bytecode = True
        import importlib.machinery
        import importlib.util
        path = str(REPO / "home/.local/lib/zen/autowidth")
        loader = importlib.machinery.SourceFileLoader("zen_autowidth", path)
        spec = importlib.util.spec_from_loader("zen_autowidth", loader)
        self.m = importlib.util.module_from_spec(spec)
        loader.exec_module(self.m)
        self.sent = []
        self.m.niri = lambda *a: self.sent.append(" ".join(a)) or subprocess.CompletedProcess(a, 0, "", "")
        self.m.output_size = lambda: (self.W, 1200)
        self.m.output_width = lambda: self.W

    def win(self, i, col, row=1, width=960):
        w = {"id": i, "workspace_id": 1, "is_floating": False,
             "layout": {"pos_in_scrolling_layout": [col, row], "tile_size": [width, 600]}}
        self.m.windows[i] = w
        return w

    def test_new_window_next_to_a_stack_takes_the_other_half(self):
        self.win(1, 1)
        self.win(2, 1, 2)
        new = self.win(3, 2)
        self.m.on_new_window(new)
        self.assertEqual(self.sent, ["action set-window-width --id 3 50%"])
        self.assertEqual(self.m.stack_partner[3], [1, 2])
        self.m.on_closed(3)
        self.assertIn("action set-window-width --id 1 100%", self.sent)

    def test_pair_with_a_stack_is_complete(self):
        self.win(1, 1)
        self.win(2, 2)
        self.win(3, 2, 2)
        self.m.partner.update({1: 2, 2: 1})
        self.m.on_new_window(self.win(4, 3))
        self.assertEqual(self.sent, ["action set-window-width --id 4 100%"])

    def test_join_and_leave_restores_the_size(self):
        self.win(1, 1)
        self.win(2, 2)
        c = self.win(3, 3, width=1900)
        for i in (1, 2, 3):
            self.m.stacked[i] = False
        self.m.focused_id = 3
        # Mod+] ... Mod+[ : window 3 goes into column 2
        old = {3: c["layout"]["tile_size"][0], 2: 960}
        c["layout"] = {"pos_in_scrolling_layout": [2, 2], "tile_size": [960, 600]}
        self.m.track_stacks([3, 2], old)
        self.assertEqual(self.sent, ["action focus-window --id 1", "action focus-window --id 3"])
        self.sent.clear()
        # and out again
        c["layout"] = {"pos_in_scrolling_layout": [3, 1], "tile_size": [960, 600]}
        self.m.track_stacks([3], {3: 960})
        self.assertEqual(self.sent[0], "action set-window-width --id 3 100%")

    def test_closing_a_window_does_not_restore(self):
        self.win(2, 1)
        c = self.win(3, 1, 2)
        self.m.stacked.update({2: True, 3: True})
        self.m.saved[3] = 1.0
        self.m.focused_id = 3
        self.m.on_closed(2)
        self.m.saved[3] = 1.0
        c["layout"]["pos_in_scrolling_layout"] = [1, 1]
        self.m.track_stacks([3], {3: 960})
        self.assertEqual(self.sent, [])


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

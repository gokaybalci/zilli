#!/usr/bin/env python3
# Zilli - okul zil programı. Copyright (C) 2026 Gökay. GPL-3.0-or-later (LICENSE dosyasına bakın).
# Python 3.7 uyumlu kalmalı: Windows paketi 3.7.9 ile yapılır
# (3.8+ Windows 7'de KB2533623 güncellemesi olmadan eklenti modüllerini yükleyemez).
import copy
import datetime
import json
import os
import queue
import random
import shutil
import socket
import subprocess
import sys
import threading
import wave

if os.name == "nt" and getattr(sys, "frozen", False):
    # Tcl 8.6, TCL_LIBRARY/TK_LIBRARY ortam değişkenlerini ANSI kod sayfasıyla okur: yoldaki ş, ı gibi harfler
    # (ör. kullanıcı adı "Meşedibi") o kod sayfasında yoksa bozulur, init.tcl bulunamaz. 8.3 kısa yollar da
    # çoğu Windows 10'da kapalı. Program klasörüne geçip göreli, her zaman ASCII yol veririz.
    os.chdir(os.path.dirname(sys.executable))
    for _var, _sub in (("TCL_LIBRARY", "tcl"), ("TK_LIBRARY", "tk")):
        if os.path.isdir(_sub):
            os.environ[_var] = _sub

import tkinter as tk  # noqa: E402
from tkinter import filedialog, font as tkfont, messagebox  # noqa: E402

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402
import ttkbootstrap as ttk  # noqa: E402
from ttkbootstrap.style import Colors, ThemeDefinition  # noqa: E402
from ttkbootstrap.dialogs import MessageDialog  # noqa: E402
from ttkbootstrap.icons import Icon  # noqa: E402

APP, VERSION = "Zilli", "1.1.1"
BASE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "assets")
# Windows'ta program kullanıcı klasörüne kurulur (yazılabilir); Linux'ta AppImage/deb salt okunur, veriler ~/Zilli'de.
DATA = os.environ.get("ZILLI_DATA") or (BASE if os.name == "nt" else os.path.expanduser("~/Zilli"))
CONFIG_PATH = os.path.join(DATA, "zilli.json")
FOLDERS = ("Melodiler", "Marşlar", "Müzik")
MELODI, MARS, MUZIK = (os.path.join(DATA, d) for d in FOLDERS)
AUDIO_EXT = (".mp3", ".wav", ".ogg", ".flac", ".mid", ".midi")
DAYS = [("haftaici", "Hafta içi"), ("cumartesi", "Cumartesi"), ("pazar", "Pazar")]
DAY_TOGGLE = {"haftaici": "Hafta içi zil çalsın", "cumartesi": "Cumartesileri zil çalsın",
              "pazar": "Pazarları zil çalsın"}
# sıra: öğrenci zili (dersten önce), öğretmen zili (ders başı), teneffüs zili (ders sonu; ayar anahtarı "cikis")
BELLS = [("ogrenci", "Öğrenci zili"), ("ogretmen", "Öğretmen zili"), ("cikis", "Teneffüs zili")]
BELL_NAMES = dict(BELLS + [("son", "Son zil")])
OFFSETS = [(0, "Çalmasın"), (15, "15 saniye önce"), (30, "30 saniye önce"), (45, "45 saniye önce"),
           (60, "1 dakika önce"), (120, "2 dakika önce"), (180, "3 dakika önce")]
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül",
         "Ekim", "Kasım", "Aralık"]
MAX_LESSONS = 16
MUSIC_STOP_BEFORE = 30  # teneffüs müziği sonraki zilden bu kadar saniye önce susar
LATE_LIMIT = 60  # bilgisayar uykudan uyanırsa bundan eski zilleri çalma
SINGLE_PORT = 47392

DEFAULT_CONFIG = {
    "theme": "acik",
    "bells_on": True,
    "teacher_offset": 60,
    "bells": {
        "ogrenci": {"melody": "MEB Öğrenci Zili.mp3", "volume": 100},
        "ogretmen": {"melody": "MEB Çıkış Zili.mp3", "volume": 100},
        "cikis": {"melody": "MEB Teneffüs Zili.mp3", "volume": 100},
        "son": {"melody": "MEB Çıkış Zili.mp3", "volume": 100},  # günün son zili
    },
    "music": {"on": False, "volume": 60},
    "march_volume": 100,
    "days": {
        "haftaici": {"on": True, "lessons": [
            ["08:30", "09:10"], ["09:20", "10:00"], ["10:10", "10:50"], ["11:00", "11:40"],
            ["12:30", "13:10"], ["13:20", "14:00"], ["14:10", "14:50"]]},
        "cumartesi": {"on": False, "lessons": [["09:00", "09:40"], ["09:50", "10:30"]]},
        "pazar": {"on": False, "lessons": []},
    },
    "autostart_asked": False,
    "sounds_version": 0,
}
SOUNDS_VERSION = 3  # programla gelen ses seti değişince artır: eksik dosyalar veri klasörüne bir kez kopyalanır


# ---------- saf fonksiyonlar (test_zilli.py bunları sınar) ----------

def parse_hhmm(text):
    h, m = text.strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(text)
    return h * 3600 + m * 60


def fmt_hhmm(sec):
    sec %= 86400
    return "%02d:%02d" % (sec // 3600, sec % 3600 // 60)


def day_key(date):
    return {5: "cumartesi", 6: "pazar"}.get(date.weekday(), "haftaici")


def validate_lessons(rows):
    """[(giriş, çıkış), ...] metinlerini kontrol eder; boş satırları atlar, hata varsa ValueError."""
    out, prev_end = [], -1
    for i, (s, e) in enumerate(rows, 1):
        if not s.strip() and not e.strip():
            continue
        try:
            s, e = parse_hhmm(s), parse_hhmm(e)
        except ValueError:
            raise ValueError("%d. ders: saat SS:DD biçiminde olmalı (ör. 08:30)." % i)
        if e <= s:
            raise ValueError("%d. ders: çıkış saati girişten sonra olmalı." % i)
        if s < prev_end:
            raise ValueError("%d. ders: önceki dersin çıkışından önce başlıyor." % i)
        prev_end = e
        out.append([fmt_hhmm(s), fmt_hhmm(e)])
    return out


def break_error(lessons, offset):
    """Öğrenci zili teneffüs bitmeden çalmasın: her teneffüs bu süreden uzun olmalı (eşitse iki zil aynı
    saniyeye düşer, biri çalmaz). Sorun yoksa boş metin."""
    def dur(sec):
        return "%d dk" % (sec // 60) if sec % 60 == 0 else "%d sn" % sec
    for i in range(1, len(lessons) if offset else 0):
        gap = parse_hhmm(lessons[i][0]) - parse_hhmm(lessons[i - 1][1])
        if gap <= offset:
            return ("%d. dersten önceki teneffüs %s; öğrenci zili dersten %s önce çaldığı için teneffüs bundan "
                    "uzun olmalı." % (i + 1, dur(gap), dur(offset)))
    return ""


def events_for(cfg, date):
    """O günün zilleri: sıralı [(saniye, zil_türü, ders_no), ...]"""
    day = cfg["days"][day_key(date)]
    if not day["on"]:
        return []
    off, ev = cfg["teacher_offset"], []
    for n, (s, e) in enumerate(day["lessons"], 1):
        s, e = parse_hhmm(s), parse_hhmm(e)
        if off:
            ev.append((s - off, "ogrenci", n))
        ev.append((s, "ogretmen", n))
        ev.append((e, "cikis", n))
    ev.sort()
    if ev:  # günün son zili ayrı melodiyle çalar
        ev[-1] = (ev[-1][0], "son", ev[-1][2])
    return ev


def due_event(events, last, now):
    """last < saniye <= now aralığındaki en son zil (eski kalmışsa None)."""
    due = [e for e in events if last < e[0] <= now]
    return due[-1] if due and now - due[-1][0] < LATE_LIMIT else None


def in_break(events, now):
    prev = [e for e in events if e[0] <= now]
    nxt = [e for e in events if e[0] > now]
    return bool(prev and prev[-1][1] == "cikis" and nxt and nxt[0][0] - now > MUSIC_STOP_BEFORE)


def current_period(lessons, sec):
    """(metin, başlangıç, bitiş): şu anki ders/teneffüs; ikisi de değilse başlangıç/bitiş None."""
    spans = [(parse_hhmm(s), parse_hhmm(e)) for s, e in lessons]
    for i, (s, e) in enumerate(spans):
        if s <= sec < e:
            return "%d. ders" % (i + 1), s, e
        if i + 1 < len(spans) and e <= sec < spans[i + 1][0]:
            return "Teneffüs", e, spans[i + 1][0]
    if not spans:
        return "Bugün ders yok", None, None
    return ("Okul başlamadı" if sec < spans[0][0] else "Okul bitti"), None, None


MP3_KBPS = {3: (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),  # MPEG1 katman 3
            2: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)}   # MPEG2/2.5
MP3_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def mp3_duration(f, size):
    head = f.read(10)
    start = 0
    if head[:3] == b"ID3":  # etiket boyutu "syncsafe" (bayt başına 7 bit)
        start = 10 + (head[6] << 21 | head[7] << 14 | head[8] << 7 | head[9])
    f.seek(start)
    b = f.read(8192)
    for i in range(len(b) - 4):
        if b[i] != 0xFF or b[i + 1] & 0xE6 != 0xE2:  # çerçeve eşlemesi + katman 3
            continue
        ver, bri, sri = (b[i + 1] >> 3) & 3, b[i + 2] >> 4, (b[i + 2] >> 2) & 3
        if ver == 1 or not 0 < bri < 15 or sri == 3:
            continue
        rate = MP3_RATES[ver][sri]
        spf = 1152 if ver == 3 else 576
        mono = b[i + 3] >> 6 == 3
        x = i + 4 + ((17 if mono else 32) if ver == 3 else (9 if mono else 17))
        if b[x:x + 4] in (b"Xing", b"Info") and b[x + 7] & 1:  # VBR: çerçeve sayısı yazılı
            return int.from_bytes(b[x + 8:x + 12], "big") * spf / rate
        if b[i + 36:i + 40] == b"VBRI":
            return int.from_bytes(b[i + 50:i + 54], "big") * spf / rate
        return (size - start - i) * 8 / (MP3_KBPS[3 if ver == 3 else 2][bri] * 1000.0)  # sabit bit hızı
    return None


def audio_duration(path):
    """Ses süresi (sn), dosyayı çözmeden başlıktan okunur (eski PC'de uzun şarkılar da anında). Bilinmiyorsa None."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".wav":
            with wave.open(path) as w:
                return w.getnframes() / float(w.getframerate())
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if ext == ".mp3":
                return mp3_duration(f, size)
            head = f.read(65536)
            if ext == ".flac" and head[:4] == b"fLaC":
                v = int.from_bytes(head[18:26], "big")  # STREAMINFO: 20 bit örnek hızı ... 36 bit örnek sayısı
                rate, total = v >> 44, v & ((1 << 36) - 1)
                return total / float(rate) if rate and total else None
            if ext == ".ogg":
                i = head.find(b"\x01vorbis")
                rate = int.from_bytes(head[i + 12:i + 16], "little") if i >= 0 else (48000 if b"OpusHead" in head else 0)
                f.seek(max(0, size - 65536))
                tail = f.read()
                j = tail.rfind(b"OggS")
                if rate and j >= 0:  # son sayfanın "granule" konumu = toplam örnek
                    return int.from_bytes(tail[j + 6:j + 14], "little") / float(rate)
    except (OSError, EOFError, ValueError, wave.Error):
        pass
    return None


def mmss(sec):
    return "%d:%02d" % (sec // 60, sec % 60)


def merge(base, over):
    for k, v in over.items():
        base[k] = merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return base


def audio_files(folder):
    try:
        return sorted((f for f in os.listdir(folder) if f.lower().endswith(AUDIO_EXT)), key=str.lower)
    except OSError:
        return []


# ---------- veri klasörü ve ayarlar ----------

def ensure_data(cfg):
    """Programla gelen sesleri (sounds/) veri klasörüne kopyalar: ilk açılışta hepsini, ses seti
    yenilenince yalnız eksikleri (kullanıcının sildikleri her açılışta geri gelmesin diye bir kez)."""
    fill = cfg.get("sounds_version", 0) < SOUNDS_VERSION
    for d in FOLDERS:
        src, dst = os.path.join(BASE, "sounds", d), os.path.join(DATA, d)
        os.makedirs(dst, exist_ok=True)
        if fill and os.path.isdir(src) and os.path.abspath(src) != os.path.abspath(dst):
            for f in os.listdir(src):
                if not os.path.exists(os.path.join(dst, f)):
                    shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
    cfg["sounds_version"] = SOUNDS_VERSION


MARCH_CHAINS = {"saygidurusu.mp3": ["istiklalmarsi.mp3"]}  # saygı duruşunun ardından marş hemen çalar
# ayarlara yazılmaz: yeni sürümdeki ad düzeltmesi herkese ulaşsın
MARCH_LABELS = {"istiklalmarsi.mp3": "İstiklal Marşı", "istiklalmarsiorkestra.mp3": "İstiklal Marşı (Enstrümental)",
                "saygidurusu.mp3": "Saygı Duruşu + İstiklal Marşı", "siren.mp3": "Siren"}


def march_label(name):
    """Marş düğmesinin yazısı: bilinen dosyaların adı, diğerlerinde uzantısız dosya adı."""
    return MARCH_LABELS.get(name, os.path.splitext(name)[0])


def check_config(cfg):
    """Elle bozulmuş ayarları açılışta yakalar (yoksa zil döngüsü çalışırken patlardı); hatada istisna atar."""
    for key, _ in DAYS:
        day = cfg["days"][key]
        day["on"] = bool(day["on"])
        day["lessons"] = validate_lessons([(str(s), str(e)) for s, e in day["lessons"]])
    cfg["teacher_offset"] = max(0, int(cfg["teacher_offset"]))
    for key in BELL_NAMES:
        b = cfg["bells"][key]
        b["melody"], b["volume"] = str(b["melody"]), max(0, min(100, int(b["volume"])))
    cfg["music"]["volume"] = max(0, min(100, int(cfg["music"]["volume"])))
    cfg["march_volume"] = max(0, min(100, int(cfg["march_volume"])))
    if cfg["theme"] not in THEME_COLORS:  # 1.0.x'in Bootstrap temaları (flatly, darkly...) artık yok
        cfg["theme"] = "acik"
    return cfg


def load_config():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if not os.path.exists(CONFIG_PATH):
        return cfg, None
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return check_config(merge(cfg, json.load(f))), None
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as ex:
        bad = CONFIG_PATH + ".bozuk"  # bozuk dosyayı silme, kenara al
        try:
            os.replace(CONFIG_PATH, bad)
        except OSError:
            pass
        return copy.deepcopy(DEFAULT_CONFIG), "Ayar dosyası okunamadı (%s).\nVarsayılanlar yüklendi, eski dosya: %s" % (ex, bad)


def save_config(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CONFIG_PATH)  # elektrik kesilirse yarım dosya kalmasın


# ---------- açılışta başlatma ----------

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
DESKTOP_FILE = os.path.expanduser("~/.config/autostart/zilli.desktop")
SYSTEM_DESKTOP = "/etc/xdg/autostart/zilli.desktop"  # .deb kurar


def autostart_cmd():
    if os.environ.get("APPIMAGE"):
        return '"%s" --min' % os.environ["APPIMAGE"]
    if getattr(sys, "frozen", False):
        return '"%s" --min' % sys.executable
    exe = sys.executable
    if os.name == "nt":
        exe = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return '"%s" "%s" --min' % (exe, os.path.abspath(__file__))


def get_autostart():
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, APP)
            return True
        except OSError:
            return False
    if os.path.exists(DESKTOP_FILE):
        with open(DESKTOP_FILE, encoding="utf-8") as f:
            return "Hidden=true" not in f.read()
    return os.path.exists(SYSTEM_DESKTOP)


def set_autostart(on):
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, autostart_cmd())
            else:
                try:
                    winreg.DeleteValue(k, APP)
                except OSError:
                    pass
        return
    os.makedirs(os.path.dirname(DESKTOP_FILE), exist_ok=True)
    with open(DESKTOP_FILE, "w", encoding="utf-8") as f:
        # aynı adlı kullanıcı dosyası sistem dosyasını geçersiz kılar; kapatmak için Hidden=true gerekir
        f.write("[Desktop Entry]\nType=Application\nName=%s\nExec=%s\n%s" % (
            APP, autostart_cmd(), "" if on else "Hidden=true\n"))


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)
    else:
        # paketin Tcl/Tk yolları dosya yöneticisine sızmasın
        env = {k: v for k, v in os.environ.items() if k not in ("TCL_LIBRARY", "TK_LIBRARY", "TCL8_6_TM_PATH")}
        subprocess.Popen(["xdg-open", path], env=env)


def tray_available():
    """Linux'ta sistem tepsisi yoksa (ör. eklentisiz GNOME) pencere görev çubuğuna küçültülür."""
    if os.name == "nt":
        return True
    try:
        from Xlib import display
        d = display.Display()
        owner = d.get_selection_owner(d.intern_atom("_NET_SYSTEM_TRAY_S%d" % d.get_default_screen()))
        d.close()
        return getattr(owner, "id", owner) != 0
    except Exception:
        return False


SNI_INTROSPECT = """<node><interface name="org.kde.StatusNotifierItem">
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
</interface></node>"""


class SniTray:
    """Linux tepsi simgesi (StatusNotifierItem, D-Bus): KDE, GNOME AppIndicator eklentisi, XFCE, Cinnamon.
    Eski XEmbed simgeleri KDE Wayland'de tıklama için izin ister; bu istemez."""

    def __init__(self, send, icon_path):
        from PIL import Image
        self.send, self.conn = send, None
        self.pixmaps = []
        src = Image.open(icon_path).convert("RGBA")
        for s in (22, 32, 48, 64):
            r, g, b, a = src.resize((s, s), Image.LANCZOS).split()
            self.pixmaps.append((s, s, Image.merge("RGBA", (a, r, g, b)).tobytes()))  # ARGB32, büyük sonlu
        self.props = {"Category": ("s", "ApplicationStatus"), "Id": ("s", "zilli"), "Title": ("s", APP),
                      "Status": ("s", "Active"), "IconName": ("s", ""), "IconPixmap": ("a(iiay)", self.pixmaps),
                      "ItemIsMenu": ("b", False), "Menu": ("o", "/NO_DBUSMENU"), "WindowId": ("i", 0),
                      "ToolTip": ("(sa(iiay)ss)", ("", [], APP, "Okul zil sistemi"))}

    def start(self):
        """Masaüstünde StatusNotifierWatcher yoksa False döner."""
        from jeepney import DBusAddress, new_method_call
        from jeepney.bus_messages import message_bus
        from jeepney.io.blocking import open_dbus_connection
        self.conn = open_dbus_connection(bus="SESSION")
        if not self.conn.send_and_get_reply(message_bus.NameHasOwner("org.kde.StatusNotifierWatcher")).body[0]:
            self.conn.close()
            return False
        name = "org.kde.StatusNotifierItem-%d-1" % os.getpid()
        self.conn.send_and_get_reply(message_bus.RequestName(name))
        watcher = DBusAddress("/StatusNotifierWatcher", bus_name="org.kde.StatusNotifierWatcher",
                              interface="org.kde.StatusNotifierWatcher")
        self.conn.send_and_get_reply(new_method_call(watcher, "RegisterStatusNotifierItem", "s", (name,)))
        threading.Thread(target=self.serve, daemon=True).start()
        return True

    def serve(self):
        from jeepney import MessageType
        while True:
            try:
                msg = self.conn.receive()
            except Exception:  # bağlantı kapandı
                return
            if msg.header.message_type != MessageType.method_call:
                continue
            try:
                self.conn.send(self.handle(msg))
            except Exception:
                return

    def handle(self, msg):
        """Gelen çağrının yanıtı. Bozuk çağrı hata yanıtı alır; iş parçacığı ölüp tepsi tıklanmaz hale gelmez."""
        from jeepney import HeaderFields, new_error, new_method_return
        member = msg.header.fields.get(HeaderFields.member)
        try:
            if member in ("Activate", "SecondaryActivate"):
                self.send("show")
                return new_method_return(msg)
            if member == "ContextMenu":
                x, y = msg.body
                self.send(("menu", x, y))
                return new_method_return(msg)
            if member == "Scroll":
                return new_method_return(msg)
            if member == "GetAll":
                return new_method_return(msg, "a{sv}", (self.props,))
            if member == "Get" and msg.body[1] in self.props:
                return new_method_return(msg, "v", (self.props[msg.body[1]],))
            if member == "Introspect":
                return new_method_return(msg, "s", (SNI_INTROSPECT,))
            return new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod")
        except Exception:
            return new_error(msg, "org.freedesktop.DBus.Error.InvalidArgs")

    def stop(self):
        try:
            self.conn.close()
        except Exception:
            pass


# ---------- ses ----------

def missing_error(items):
    missing = [os.path.basename(p) or "(seçilmedi)" for p, _ in items if not os.path.isfile(p)]
    return "Ses dosyası yok: " + ", ".join(missing) if missing else ""


class Player:
    """Tek ses kanalı: zil, marş ve müzik sırayla çalar, üst üste binmez."""

    def __init__(self):
        self.queue, self.kind, self.title, self.error, self.duration = [], None, "", "", None

    def play(self, items, kind):
        """items: [(dosya_yolu, ses 0-100), ...]"""
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init(44100, -16, 2, 2048)
            except pygame.error as ex:
                self.error = "Ses aygıtı açılamadı: %s" % ex
                return
        self.error = missing_error(items)
        self.queue = [i for i in items if os.path.isfile(i[0])]
        self.kind = kind
        pygame.mixer.music.stop()
        self._next()

    def _next(self):
        while self.queue:
            path, vol = self.queue.pop(0)
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(vol / 100.0)
                pygame.mixer.music.play()
                self.title, self.duration = os.path.basename(path), audio_duration(path)
                return
            except pygame.error as ex:
                self.error = "%s çalınamadı: %s" % (os.path.basename(path), ex)
        self.kind, self.title = None, ""

    def poll(self):
        if self.kind and not pygame.mixer.music.get_busy():
            self._next()

    def stop(self, fade_ms=0):
        self.queue, self.kind, self.title = [], None, ""
        if pygame.mixer.get_init():
            if fade_ms:
                pygame.mixer.music.fadeout(fade_ms)
            else:
                pygame.mixer.music.stop()


# ---------- arayüz ----------

FONT_FILES = ("AtkinsonHyperlegibleNext-Regular.ttf", "AtkinsonHyperlegibleNext-Bold.ttf")
FONT_FAMILY = "Atkinson Hyperlegible Next"

# "Okul tahtası ve pirinç zil": tahta yeşili yapı, pirinç tek vurgu. Her çift WCAG oranlarıyla ölçüldü.
THEMES = [("acik", "Açık"), ("gece", "Gece"), ("kontrast", "Yüksek kontrast")]
THEME_COLORS = {
    "acik": ("light", dict(
        primary="#2E5A4C", secondary="#56635E", success="#2E5A4C", info="#C9971C", warning="#7A5800",
        danger="#B83227", light="#ECEFEC", dark="#56635E", bg="#F7F8F6", fg="#1E2B26", selectbg="#7A5800",
        selectfg="#F2F5F2", border="#C8CFCB", inputfg="#1E2B26", inputbg="#FFFFFF", active="#E3E7E4")),
    "gece": ("dark", dict(
        primary="#2F7A62", secondary="#A3B3AC", success="#6FB89C", info="#E0B54A", warning="#E8C468",
        danger="#C8382D", light="#1B332C", dark="#A3B3AC", bg="#13241F", fg="#ECF1EC", selectbg="#5E4A12",
        selectfg="#ECF1EC", border="#2E4C42", inputfg="#ECF1EC", inputbg="#1A302A", active="#24413A")),
    "kontrast": ("light", dict(
        primary="#003D2E", secondary="#2B2B2B", success="#003D2E", info="#E0A800", warning="#5A4100",
        danger="#A30000", light="#EDEDED", dark="#2B2B2B", bg="#FFFFFF", fg="#000000", selectbg="#5A4100",
        selectfg="#FFFFFF", border="#000000", inputfg="#000000", inputbg="#FFFFFF", active="#E6E6E6")),
}
# ttkbootstrap paletinde olmayan roller: pirinç yazı/çizgi, seçili menü yazısı, ders bloğu ve üstündeki yazı
THEME_EXTRA = {
    "acik": dict(brass_text="#7A5800", brass_line="#8C6400", nav_text="#F2F5F2", nav_sel_text="#1E2B26",
                 block="#2E5A4C", block_text="#F2F5F2"),
    "gece": dict(brass_text="#E8C468", brass_line="#E0B54A", nav_text="#ECF1EC", nav_sel_text="#13241F",
                 block="#529E84", block_text="#13241F"),
    "kontrast": dict(brass_text="#5A4100", brass_line="#7A5800", nav_text="#FFFFFF", nav_sel_text="#000000",
                     block="#003D2E", block_text="#FFFFFF"),
}


def load_fonts():
    """Programla gelen yazı tipini yalnız bu süreç için yükler (kurulum, yönetici izni gerekmez).
    Yüklenemezse sistem yazı tipine düşülür (pick_font)."""
    folder = os.path.join(ASSETS, "fonts")
    try:
        if os.name == "nt":
            import ctypes
            for f in FONT_FILES:
                ctypes.windll.gdi32.AddFontResourceExW(os.path.join(folder, f), 0x10, 0)  # FR_PRIVATE
        else:
            import ctypes
            ctypes.CDLL("libfontconfig.so.1").FcConfigAppFontAddDir(None, os.fsencode(folder))
    except (ImportError, OSError, AttributeError):  # ctypes/fontconfig yoksa da açılış durmasın
        pass


def pick_font():
    have = set(tkfont.families())
    for f in (FONT_FAMILY, "Segoe UI", "Ubuntu", "Noto Sans", "Cantarell", "DejaVu Sans"):
        if f in have:
            return f
    return "Helvetica"


def register_themes(style):
    for name, (kind, colors) in THEME_COLORS.items():
        style.register_theme(ThemeDefinition(name, colors, kind))


def now_text(day_on, lessons, sec):
    """Panodaki büyük satır: "2. ders, 25 dakika kaldı" gibi."""
    if not day_on:
        return "Bugün zil yok"
    label, s, e = current_period(lessons, sec)
    if s is None:
        return label
    return "%s, %d dakika kaldı" % (label, (e - sec + 59) // 60)


def timeline_span(events):
    """Gün çizelgesinin kapsadığı aralık (saniye): ilk zilden 10 dk önce, son zilden 10 dk sonra."""
    if not events:
        return None
    return events[0][0] - 600, events[-1][0] + 600


def countdown_text(left):
    return "%d:%02d:%02d" % (left // 3600, left % 3600 // 60, left % 60) if left >= 3600 else \
        "%d:%02d" % (left // 60, left % 60)


class Bubble:
    """Üzerine gelince yanında çıkan küçük balon (ttkbootstrap ToolTip Python 3.7'de açılmıyor)."""

    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tip:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.geometry("+%d+%d" % (self.widget.winfo_rootx() + self.widget.winfo_width() + 10,
                                      self.widget.winfo_rooty() - 4))
        ttk.Label(self.tip, text=self.text, bootstyle="inverse-primary", padding=(10, 4)).pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class Digits(tk.Canvas):
    """Rakamları eşit hücrelere çizen saat yazısı: yazı tipinin rakam genişlikleri farklı olsa da saniye
    değişince yazı titremez. İkinci (küçük) kısım aynı taban çizgisine oturur."""

    def __init__(self, parent, family, size, small=0):
        tk.Canvas.__init__(self, parent, highlightthickness=0, bd=0, autostyle=False)
        self.family, self.small_size = family, small
        self.text, self.tail, self.fg, self.tail_fg = "", "", "#000", "#000"
        self.resize(size)

    def resize(self, size):
        self.big = tkfont.Font(family=self.family, size=size, weight="bold")
        self.sm = tkfont.Font(family=self.family, size=self.small_size or size, weight="bold")
        self.cell = max(self.big.measure(d) for d in "0123456789")
        self.draw()

    def colors(self, bg, fg, tail_fg):
        self.fg, self.tail_fg = fg, tail_fg
        self.configure(bg=bg)
        self.draw()

    def set(self, text, tail=""):
        if (text, tail) != (self.text, self.tail):
            self.text, self.tail = text, tail
            self.draw()

    def draw(self):
        self.delete("all")
        h = self.big.metrics("linespace")
        bottom = h - (self.big.metrics("descent") - self.sm.metrics("descent"))
        x = 0
        for ch in self.text:
            w = self.cell if ch.isdigit() else self.big.measure(ch)
            self.create_text(x + w / 2.0, h, text=ch, font=self.big, fill=self.fg, anchor="s")
            x += w
        if self.tail:
            self.create_text(x, bottom, text=self.tail, font=self.sm, fill=self.tail_fg, anchor="sw")
            x += self.sm.measure(self.tail)
        self.configure(width=max(1, x), height=h)


class App:
    def __init__(self, root, cfg):
        self.root, self.cfg = root, cfg
        self.player = Player()
        self.date, self.events, self.last = None, [], 0
        self.music_hold = False  # "Durdur"a basılınca teneffüs müziği sonraki zile kadar susar
        self.shown, self.sched_key = {}, None
        self.commands = queue.Queue()  # tepsi ve ikinci açılış iş parçacıklarından gelen komutlar
        self.tray = None
        self.last_error = ""
        self.F = pick_font()
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(name).configure(family=self.F, size=11)
        self.extra = THEME_EXTRA[root.style.theme_use()]

        root.title(APP)
        root.geometry("960x680")
        root.minsize(640, 600)
        self.compact = None
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        try:
            root.iconphoto(True, tk.PhotoImage(file=os.path.join(ASSETS, "zilli.png")))
            self.logo = tk.PhotoImage(file=os.path.join(ASSETS, "zilli-48.png"))
        except tk.TclError:
            self.logo = ""

        side = ttk.Frame(root, bootstyle="primary", padding=(0, 20))
        side.pack(side="left", fill="y")
        self.side_title = ttk.Label(side, text=" Zilli", image=self.logo, compound="left", font=(self.F, 24, "bold"),
                                    bootstyle="inverse-primary")
        self.side_title.pack(padx=14)
        self.side_sub = ttk.Label(side, text="Okul zil sistemi", bootstyle="inverse-primary")
        self.side_sub.pack(padx=14, pady=(2, 24))
        self.page_var = tk.StringVar(value="pano")
        self.pages, self.nav, self.nav_titles = {}, [], []
        main = self.main = ttk.Frame(root, padding=(24, 16))
        main.pack(side="left", fill="both", expand=True)
        self.build_header(main)
        body = ttk.Frame(main)
        body.pack(fill="both", expand=True, pady=(20, 0))
        for key, title, short, builder in (("pano", "Pano", "Pano", self.page_dashboard),
                                           ("saat", "Zil saatleri", "Saatler", self.page_schedule),
                                           ("melodi", "Melodiler", "Melodi", self.page_bells),
                                           ("muzik", "Müzik ve marşlar", "Müzik", self.page_music),
                                           ("ayar", "Ayarlar", "Ayarlar", self.page_settings)):
            page = ttk.Frame(body)
            builder(page)
            self.pages[key] = page
            # düz tk düğmesi: renkleri temadan biz veririz (apply_theme); seçili olan pirinç
            b = tk.Radiobutton(side, text="  " + title, value=key, variable=self.page_var, command=self.show_page,
                               indicatoron=False, anchor="w", relief="flat", bd=0, highlightthickness=0,
                               padx=18, pady=10, width=19, font=(self.F, 12), cursor="hand2", autostyle=False)
            b.pack(fill="x", padx=10, pady=1)
            self.nav.append(b)
            self.nav_titles.append((title, short))
        ver = self.ver = ttk.Label(side, text="Sürüm " + VERSION, bootstyle="inverse-primary", cursor="hand2")
        ver.pack(side="bottom", anchor="w", padx=20)
        Bubble(ver, "Gökay")
        root.bind("<Configure>", self.on_resize)
        self.apply_theme()
        self.show_page()
        self.start_tray()
        root.bind("<Unmap>", self.on_unmap)
        root.report_callback_exception = lambda exc, val, tb: self.add_log("Hata: %s" % val)  # Windows'ta konsol yok
        self.tick()

    def on_resize(self, e):
        """Dar pencerede kenar çubuğu kısa yazılara geçer, saat küçülür."""
        if e.widget is self.timeline:
            self.draw_timeline()
            return
        if e.widget is not self.root:
            return
        compact = e.width < 820
        if compact == self.compact:
            return
        self.compact = compact
        self.side_title.configure(text="" if compact else " Zilli")
        self.side_sub.configure(text="" if compact else "Okul zil sistemi")
        for b, (title, short) in zip(self.nav, self.nav_titles):
            b.configure(text=(" " + short) if compact else ("  " + title), width=7 if compact else 19,
                        padx=10 if compact else 18)
        self.ver.configure(text=VERSION if compact else "Sürüm " + VERSION)
        self.main.configure(padding=(14, 10) if compact else (24, 16))
        self.clock.resize(30 if compact else 40)
        self.countdown.resize(26 if compact else 34)
        self.play_lbl.configure(wraplength=200 if compact else 0)

    # --- görünüm ---
    def apply_theme(self):
        """Tema değişince ttk dışındaki parçaları (menü, saat, çizelge) ve bölüm başlıklarını yeniden boya."""
        st, c = self.root.style, self.root.style.colors
        self.extra = x = THEME_EXTRA[st.theme_use()]
        # çerçeveli grup kutusu yerine sade bölüm başlığı
        for name in ("TLabelframe", "secondary.TLabelframe"):
            st.configure(name, borderwidth=0, relief="flat", bordercolor=c.bg, lightcolor=c.bg, darkcolor=c.bg)
        st.configure("TLabelframe", labelmargins=0)
        st.configure("TLabelframe.Label", font=(self.F, 15, "bold"), foreground=c.fg, background=c.bg, padding=0)
        st.configure("secondary.Link.TButton", padding=(0, 4))  # yazı düğmeleri metinle aynı hizada
        st.configure("info.Horizontal.TProgressbar", thickness=4, troughcolor=c.border, background=c.info)
        st.configure("Treeview.Heading", font=(self.F, 11, "bold"))
        # salt okunur açılır kutu bazı koyu temalarda seçim rengiyle dolar; normal giriş zemini kalsın
        st.map("TCombobox", fieldbackground=[("readonly", c.inputbg)], foreground=[("readonly", c.inputfg)],
               selectbackground=[("readonly", c.inputbg)], selectforeground=[("readonly", c.inputfg)])
        st.configure("Treeview", rowheight=26)
        for b in self.nav:
            b.configure(bg=c.primary, activebackground=Colors.update_hsv(c.primary, vd=0.06),
                        activeforeground=x["nav_text"], selectcolor=c.info)
        self.color_nav()
        self.color_tabs()
        for d in (self.clock, self.countdown):
            d.colors(c.bg, c.fg, c.secondary)
        self.timeline.configure(bg=c.bg)
        self.next_at.configure(foreground=x["brass_text"])
        self.draw_timeline()
        self.sched_key = None

    def color_nav(self):
        sel = self.page_var.get()
        for b, key in zip(self.nav, self.pages):
            b.configure(fg=self.extra["nav_sel_text"] if key == sel else self.extra["nav_text"])

    # --- yardımcılar ---
    def save(self):
        try:
            save_config(self.cfg)
        except OSError as ex:
            messagebox.showerror(APP, "Ayarlar kaydedilemedi: %s" % ex)
        self.events = events_for(self.cfg, self.date) if self.date else []
        self.sched_key = None
        self.draw_timeline()

    def set_cfg(self, key, value):
        self.cfg[key] = value
        self.save()

    def set_text(self, widget, text):
        if self.shown.get(widget) != text:  # gereksiz yeniden çizimden kaçın
            self.shown[widget] = text
            widget.configure(text=text)

    # --- sistem tepsisi ---
    def start_tray(self):
        if os.name != "nt":
            try:
                sni = SniTray(self.commands.put, os.path.join(ASSETS, "zilli.png"))
                if sni.start():
                    self.tray = sni
                    return
            except Exception:  # D-Bus yok: eski XEmbed tepsisi denenir
                pass
        if not tray_available():
            return
        try:
            import pystray
            from PIL import Image
            cmd = self.commands.put
            menu = pystray.Menu(pystray.MenuItem("Zilli'yi aç", lambda: cmd("show"), default=True),
                                pystray.MenuItem("Sesi durdur", lambda: cmd("stop")),
                                pystray.MenuItem("Çıkış", lambda: cmd("quit")))
            self.tray = pystray.Icon(APP, Image.open(os.path.join(ASSETS, "zilli.png")), APP, menu)
            threading.Thread(target=self.tray.run, daemon=True).start()
        except Exception:  # tepsi açılamazsa görev çubuğu kullanılır
            self.tray = None

    def hide(self):
        if self.tray:
            self.root.withdraw()  # görev çubuğundan da kalkar, tepsi simgesi kalır
        else:
            self.root.iconify()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def tray_menu(self, x, y):
        if not x and not y:  # Wayland'de konum gelmeyebilir
            x, y = self.root.winfo_pointerxy()
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Zilli'yi aç", command=self.show_window)
        m.add_command(label="Sesi durdur", command=self.stop)
        m.add_separator()
        m.add_command(label="Çıkış", command=lambda: self.commands.put("quit"))
        m.tk_popup(x, y)

    def on_unmap(self, e):
        # "simge durumuna küçült" düğmesi de tepsiye gönderir
        if e.widget is self.root and self.tray and self.root.state() == "iconic":
            self.root.after_idle(self.root.withdraw)

    def listen(self, lock):
        """Zilli ikinci kez açılınca yeni kopya buraya "show" gönderir, açık pencere öne gelir."""
        while True:
            try:
                conn, _ = lock.accept()
            except OSError:
                return
            try:
                conn.settimeout(2)
                if conn.recv(16) == b"show":
                    self.commands.put("show")
            except OSError:
                pass
            finally:
                conn.close()

    def show_page(self):
        for p in self.pages.values():
            p.pack_forget()
        self.pages[self.page_var.get()].pack(fill="both", expand=True)
        self.color_nav()

    def card(self, parent, title):
        """Bölüm: başlık + içerik. Çerçeve yok (apply_theme kenarlığı kaldırır)."""
        return ttk.Labelframe(parent, text=title, padding=(0, 10, 0, 0))

    def hint(self, parent, text, **kw):
        return ttk.Label(parent, text=text, bootstyle="secondary", wraplength=kw.pop("wrap", 480), **kw)

    def add_log(self, text):
        self.log.insert("", 0, values=(datetime.datetime.now().strftime("%H:%M:%S"), text))
        for extra in self.log.get_children()[100:]:
            self.log.delete(extra)

    def volume(self, parent, value, on_change, length=160):
        """Sürgü + yüzde etiketi; bırakınca on_change(int) çağrılır."""
        f = ttk.Frame(parent)
        lbl = ttk.Label(f, text="%d%%" % value, width=5)
        sc = ttk.Scale(f, from_=0, to=100, value=value, length=length,
                       command=lambda v: lbl.configure(text="%d%%" % float(v)))
        sc.pack(side="left")
        lbl.pack(side="left", padx=(8, 0))
        sc.bind("<ButtonRelease-1>", lambda _: on_change(int(sc.get())))
        return f

    def add_file(self, folder, after=None):
        src = filedialog.askopenfilename(title="Ses dosyası seçin", filetypes=[
            ("Ses dosyaları", " ".join("*" + e for e in AUDIO_EXT)), ("Tüm dosyalar", "*")])
        if getattr(sys, "frozen", False):
            os.chdir(BASE)  # Windows dosya penceresi çalışma klasörünü değiştirebilir; Tcl göreli yollara bağlı
        if not src:
            return
        dst = os.path.join(folder, os.path.basename(src))
        if os.path.exists(dst) and not messagebox.askyesno(APP, "%s zaten var. Üzerine yazılsın mı?" % os.path.basename(dst)):
            return
        try:
            os.makedirs(folder, exist_ok=True)
            shutil.copyfile(src, dst)
        except OSError as ex:
            messagebox.showerror(APP, "Kopyalanamadı: %s" % ex)
            return
        if after:
            after()
        messagebox.showinfo(APP, "%s eklendi." % os.path.basename(dst))

    # --- üst bilgi ---
    def build_header(self, main):
        h = ttk.Frame(main)
        h.pack(fill="x")
        self.clock = Digits(h, self.F, 40, small=20)
        self.clock.pack(side="left")
        info = ttk.Frame(h)
        info.pack(side="left", padx=(18, 0), fill="y")
        self.date_lbl = ttk.Label(info, font=(self.F, 12), bootstyle="secondary")
        self.date_lbl.pack(anchor="w", pady=(8, 0))
        self.play_lbl = ttk.Label(info, font=(self.F, 11))
        self.play_lbl.pack(anchor="w")
        right = ttk.Frame(h)
        right.pack(side="right")
        # boşta sakin; ses çalarken kırmızı (update_view)
        self.stop_btn = ttk.Button(right, text="Sesi durdur", bootstyle="secondary-outline", padding=(18, 10),
                                   command=self.stop)
        self.stop_btn.pack(fill="x")
        self.bells_var = tk.BooleanVar(value=self.cfg["bells_on"])
        ttk.Checkbutton(right, text="Ziller açık", variable=self.bells_var, bootstyle="success-round-toggle",
                        command=lambda: self.set_cfg("bells_on", self.bells_var.get())).pack(anchor="e", pady=(8, 0))
        # çalarken pirinç renkle dolan ince çizgi; boşken ayırıcı
        self.play_bar = ttk.Progressbar(main, maximum=1000, bootstyle="info")
        self.play_bar.pack(fill="x", pady=(14, 0))
        self.bar_val = 0

    # --- sayfalar ---
    def page_dashboard(self, p):
        self.now_lbl = ttk.Label(p, font=(self.F, 22, "bold"))
        self.now_lbl.pack(anchor="w")
        # günün çizelgesi: dersler tahta yeşili bloklar, teneffüsler boşluk, "şimdi" pirinç çizgi
        self.timeline = tk.Canvas(p, height=92, highlightthickness=0, bd=0, autostyle=False)
        self.timeline.pack(fill="x", pady=(14, 22))  # yeniden boyutlanınca on_resize çizer
        row = ttk.Frame(p)
        row.pack(fill="x")
        left = ttk.Frame(row)
        left.pack(side="left", anchor="n")
        self.next_name = ttk.Label(left, font=(self.F, 15, "bold"))
        self.next_name.pack(anchor="w")
        self.countdown = Digits(left, self.F, 34, small=15)
        self.countdown.pack(anchor="w", pady=(2, 0))
        self.next_at = ttk.Label(left, font=(self.F, 12))
        self.next_at.pack(anchor="w")
        right = ttk.Frame(row)
        right.pack(side="left", anchor="n", padx=(48, 0))
        self.later_title = ttk.Label(right, text="Sonra", font=(self.F, 15, "bold"))
        self.later_title.pack(anchor="w")
        self.later = []
        for _ in range(3):
            line = ttk.Frame(right)
            line.pack(anchor="w", pady=(6, 0))
            t = ttk.Label(line, font=(self.F, 12, "bold"), width=6)
            t.pack(side="left")
            d = ttk.Label(line, font=(self.F, 12))
            d.pack(side="left")
            self.later.append((t, d))
        bottom = ttk.Frame(p)
        bottom.pack(fill="both", expand=True, pady=(18, 0))
        self.log_box = ttk.Frame(bottom)
        self.log = ttk.Treeview(self.log_box, columns=("t", "m"), show="headings", height=6)
        self.log.heading("t", text="Saat", anchor="w")
        self.log.heading("m", text="Olay", anchor="w")
        self.log.column("t", width=80, minwidth=60, stretch=False, anchor="w")
        self.log.column("m", width=300, minwidth=120, anchor="w")
        self.log.pack(fill="both", expand=True, pady=(6, 0))

        def toggle_log():
            if self.log_box.winfo_manager():
                self.log_box.pack_forget()
                self.log_btn.configure(text="Olay kaydını göster")
            else:
                self.log_box.pack(fill="both", expand=True, after=self.log_btn)
                self.log_btn.configure(text="Olay kaydını gizle")
        self.log_btn = ttk.Button(bottom, text="Olay kaydını göster", bootstyle="secondary-link", command=toggle_log)
        self.log_btn.pack(anchor="w")

    def draw_timeline(self):
        cv = self.timeline
        cv.delete("all")
        w = cv.winfo_width()
        span = timeline_span(self.events)
        c, x = self.root.style.colors, self.extra
        if w < 50:
            return
        self.now_line = None
        if not span:
            cv.create_text(0, 38, text="Bugün için zil saati yok.", anchor="w", fill=c.secondary, font=(self.F, 12))
            return
        start, end = span
        pad = 4

        def px(t):
            return pad + (t - start) * (w - 2 * pad) / float(end - start)
        top, bot = 30, 54
        cv.create_line(pad, (top + bot) / 2, w - pad, (top + bot) / 2, fill=c.border, width=2)
        day = self.cfg["days"][day_key(self.date)] if self.date else {"lessons": []}
        for n, (s, e) in enumerate(day["lessons"], 1):
            x0, x1 = px(parse_hhmm(s)), px(parse_hhmm(e))
            cv.create_rectangle(x0, top, x1, bot, fill=x["block"], outline="")
            if x1 - x0 > 22:
                cv.create_text((x0 + x1) / 2, (top + bot) / 2, text=str(n), fill=x["block_text"],
                               font=(self.F, 10, "bold"))
        for t, kind, _ in self.events:
            cv.create_line(px(t), bot + 3, px(t), bot + 9, fill=c.secondary)
        f = (self.F, 10)
        cv.create_text(pad, bot + 22, text=fmt_hhmm(self.events[0][0]), anchor="w", fill=c.secondary, font=f)
        cv.create_text(w - pad, bot + 22, text=fmt_hhmm(self.events[-1][0]), anchor="e", fill=c.secondary, font=f)
        self.now_line = cv.create_line(0, top - 8, 0, bot + 9, fill=x["brass_line"], width=3)
        self.now_label = cv.create_text(0, top - 9, text="şimdi", anchor="s", fill=x["brass_text"],
                                        font=(self.F, 10, "bold"))
        self.timeline_px = px
        self.move_now(datetime.datetime.now())

    def move_now(self, now):
        span = timeline_span(self.events)
        if not span or not getattr(self, "now_line", None):
            return
        sec = now.hour * 3600 + now.minute * 60 + now.second
        visible = span[0] <= sec <= span[1]
        state = "normal" if visible else "hidden"
        x = self.timeline_px(min(max(sec, span[0]), span[1]))
        self.timeline.coords(self.now_line, x, 22, x, 63)
        w = self.timeline.winfo_width()
        self.timeline.coords(self.now_label, min(max(x, 18), w - 18), 21)
        self.timeline.itemconfigure(self.now_line, state=state)
        self.timeline.itemconfigure(self.now_label, state=state)

    def page_schedule(self, p):
        top = ttk.Frame(p)
        top.pack(fill="x")
        self.day_var = tk.StringVar(value="haftaici")
        self.tabs = []
        for key, name in DAYS:
            t = tk.Radiobutton(top, text=name, value=key, variable=self.day_var, command=self.show_day,
                               indicatoron=False, relief="flat", bd=0, highlightthickness=1, padx=16, pady=6,
                               font=(self.F, 11), cursor="hand2", autostyle=False)
            t.pack(side="left", padx=(0, 6))
            self.tabs.append((t, key))
        orow = ttk.Frame(p)
        orow.pack(fill="x", pady=(14, 0))
        ttk.Label(orow, text="Öğrenci zili").pack(side="left", padx=(0, 10))
        off = ttk.Combobox(orow, values=[n for _, n in OFFSETS], state="readonly", width=14)
        off.set(dict(OFFSETS).get(self.cfg["teacher_offset"], OFFSETS[0][1]))
        off.pack(side="left")
        self.hint(orow, "Tüm günler için").pack(side="left", padx=(10, 0))

        def off_changed(_):
            new = OFFSETS[off.current()][0]
            for key, name in DAYS:  # kapalı günler de: sonradan açılınca yanlış sırada çalmasın
                err = break_error(self.cfg["days"][key]["lessons"], new)
                if err:
                    off.set(dict(OFFSETS).get(self.cfg["teacher_offset"], OFFSETS[0][1]))  # eski değere dön
                    messagebox.showerror(APP, "%s: %s" % (name, err))
                    return
            self.set_cfg("teacher_offset", new)
            for refresh in self.previews:
                refresh()
        off.bind("<<ComboboxSelected>>", off_changed)
        holder = ttk.Frame(p)
        holder.pack(fill="both", expand=True, pady=(18, 0))
        self.day_frames, self.previews = {}, []
        for key, name in DAYS:
            self.day_frames[key] = self.day_editor(holder, key, name)
        self.show_day()

    def show_day(self):
        for f in self.day_frames.values():
            f.pack_forget()
        self.day_frames[self.day_var.get()].pack(fill="both", expand=True)
        self.color_tabs()

    def color_tabs(self):
        c, sel = self.root.style.colors, self.day_var.get()
        for t, key in self.tabs:
            on = key == sel
            t.configure(bg=c.bg, fg=self.extra["nav_sel_text"] if on else c.fg, selectcolor=c.info,
                        activebackground=c.active, activeforeground=c.fg, highlightbackground=c.border)

    def day_editor(self, holder, key, name):
        day = self.cfg["days"][key]
        f = self.card(holder, name + " ders saatleri")
        head = ttk.Frame(f)
        head.pack(fill="x")
        on = tk.BooleanVar(value=day["on"])

        def toggled():  # diğer anahtarlar gibi hemen kaydet; Kaydet'e basmayı unutan da etkilenmesin
            self.cfg["days"][key]["on"] = on.get()
            self.save()
        ttk.Checkbutton(head, text=DAY_TOGGLE[key], variable=on, bootstyle="success-round-toggle",
                        command=toggled).pack(side="left")
        self.hint(f, "Saatleri 08:30 biçiminde yazın. Öğrenci zili, yukarıda seçilen süre kadar önce çalar.").pack(
            anchor="w", pady=(6, 10))
        grid = ttk.Frame(f)
        grid.pack(fill="x")
        values = [list(l) for l in day["lessons"]]
        rows = []

        def preview(sv, lbl):
            try:
                s = parse_hhmm(sv.get()) - self.cfg["teacher_offset"]
                lbl.configure(text="öğrenci zili %s" % fmt_hhmm(s) if self.cfg["teacher_offset"] else "")
            except ValueError:
                lbl.configure(text="")

        def render():
            for w in grid.winfo_children():
                w.destroy()
            del rows[:]
            per_col = 8 if len(values) > 8 else max(len(values), 1)
            for i, (s, e) in enumerate(values):
                r, c = i % per_col, i // per_col * 6
                sv, ev = tk.StringVar(value=s), tk.StringVar(value=e)
                ttk.Label(grid, text="%d. ders" % (i + 1), width=7).grid(row=r, column=c, sticky="w",
                                                                          padx=(28 if c else 0, 6), pady=3)
                ttk.Entry(grid, textvariable=sv, width=6, justify="center").grid(row=r, column=c + 1, pady=3)
                ttk.Label(grid, text="–").grid(row=r, column=c + 2, padx=6)
                ttk.Entry(grid, textvariable=ev, width=6, justify="center").grid(row=r, column=c + 3, pady=3)
                lbl = ttk.Label(grid, bootstyle="secondary", width=17)
                lbl.grid(row=r, column=c + 4, sticky="w", padx=(12, 0))
                ttk.Button(grid, text="Sil", bootstyle="secondary-link", padding=(4, 0),
                           command=lambda i=i: remove(i)).grid(row=r, column=c + 5)
                sv.trace_add("write", lambda *_, sv=sv, lbl=lbl: preview(sv, lbl))
                preview(sv, lbl)
                rows.append((sv, ev, lbl))

        def sync():  # ekrandaki değerleri listeye al (ekle/sil yeniden çizmeden önce)
            values[:] = [[s.get(), e.get()] for s, e, _ in rows]

        def add():
            sync()
            if len(values) >= MAX_LESSONS:
                return
            try:
                last = parse_hhmm(values[-1][1]) if values else parse_hhmm("08:20")
                values.append([fmt_hhmm(last + 600), fmt_hhmm(last + 3000)])  # 10 dk teneffüs, 40 dk ders
            except ValueError:
                values.append(["", ""])
            render()

        def remove(i):
            sync()
            del values[i]
            render()

        def save():
            sync()
            try:
                lessons = validate_lessons(values)
            except ValueError as ex:
                messagebox.showerror(APP, str(ex))
                return
            err = break_error(lessons, self.cfg["teacher_offset"])
            if err:
                messagebox.showerror(APP, err)
                return
            self.cfg["days"][key] = {"on": on.get(), "lessons": lessons}
            self.save()
            values[:] = [list(l) for l in lessons]  # boş satırlar kapanır
            render()
            messagebox.showinfo(APP, "%s ders saatleri kaydedildi." % name)
        render()
        self.previews.append(lambda: [preview(sv, lbl) for sv, _, lbl in rows])
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(14, 0))
        ttk.Button(bar, text="Ders ekle", bootstyle="success-outline", command=add).pack(side="left")
        ttk.Button(bar, text="Kaydet", bootstyle="primary", padding=(22, 6), command=save).pack(side="right")
        return f

    def bell_row(self, grid, r, key):
        b = self.cfg["bells"][key]
        name = ttk.Label(grid, text=BELL_NAMES[key], font=(self.F, 12, "bold"))
        name.grid(row=r, column=0, columnspan=3, sticky="w", pady=(12, 4))
        mel = ttk.Combobox(grid, state="readonly", width=20)
        mel.set(b["melody"])
        mel.grid(row=r + 1, column=0, sticky="w")
        warn = ttk.Label(grid, text="", bootstyle="danger")
        warn.grid(row=r + 2, column=0, columnspan=3, sticky="w")

        def changed(_=None):
            b["melody"] = mel.get()
            self.save()
            self.refresh_lists()

        def vol_changed(v):
            b["volume"] = v
            self.save()
        mel.bind("<<ComboboxSelected>>", changed)
        vol = self.volume(grid, b["volume"], vol_changed, length=100)
        vol.grid(row=r + 1, column=1, padx=(16, 8))
        play = ttk.Button(grid, text="Dinle", bootstyle="success-outline",
                          command=lambda: self.ring((0, key, 0), test=True))
        play.grid(row=r + 1, column=2)
        self.bell_widgets.append((mel, warn, key))
        return [name, mel, warn, vol, play]

    def page_bells(self, p):
        self.bell_widgets = []
        c = self.card(p, "Zil melodileri")
        c.pack(fill="x")
        grid = ttk.Frame(c)
        grid.pack(fill="x")
        for i, (key, _) in enumerate(BELLS):
            self.bell_row(grid, i * 3, key)
        son = self.bell_row(grid, 10, "son")
        for w in son:
            w.grid_remove()

        def toggle_son():
            shown = son[0].winfo_manager()
            for w in son:
                w.grid_remove() if shown else w.grid()
            btn.configure(text="Son zil ayarını göster" if shown else "Son zil ayarını gizle")
        btn = ttk.Button(grid, text="Son zil ayarını göster", bootstyle="secondary-link", command=toggle_son)
        btn.grid(row=9, column=0, columnspan=3, sticky="w", pady=(16, 0))
        self.hint(c, "Son zil, günün son dersi bitince teneffüs zili yerine çalar.").pack(anchor="w", pady=(10, 0))
        self.refresh_lists()
        bar = ttk.Frame(p)
        bar.pack(fill="x", pady=(20, 0))
        for text, cmd in (("Melodi ekle…", lambda: self.add_file(MELODI, self.refresh_lists)),
                          ("Klasörü aç", lambda: open_folder(MELODI))):
            ttk.Button(bar, text=text, bootstyle="secondary-outline", command=cmd).pack(side="left", padx=(0, 8))

    def refresh_lists(self):
        mels = audio_files(MELODI)
        for mel, warn, key in self.bell_widgets:
            mel.configure(values=mels)
            name = self.cfg["bells"][key]["melody"]
            warn.configure(text="" if name in mels else "Ses dosyası yok: %s" % (name or "(seçilmedi)"))
            if name in mels:  # boş uyarı satırı yer kaplamasın
                warn.grid_remove()
            elif mel.winfo_manager():  # gizli Son zil satırının uyarısı da gizli kalsın
                warn.grid()

    def page_music(self, p):
        c = self.card(p, "Teneffüs müziği")
        c.pack(fill="x")
        on = tk.BooleanVar(value=self.cfg["music"]["on"])
        ttk.Checkbutton(c, text="Teneffüslerde Müzik klasöründen rastgele çal", variable=on, bootstyle="success-round-toggle",
                        command=lambda: (self.cfg["music"].update(on=on.get()), self.save())).pack(anchor="w")
        row = ttk.Frame(c)
        row.pack(fill="x", pady=(12, 0))
        ttk.Label(row, text="Ses").pack(side="left", padx=(0, 10))

        def vol(v):
            self.cfg["music"]["volume"] = v
            self.save()
        self.volume(row, self.cfg["music"]["volume"], vol, length=140).pack(side="left")
        row = ttk.Frame(c)
        row.pack(fill="x", pady=(12, 0))
        ttk.Button(row, text="Şimdi çal", bootstyle="success-outline",
                   command=lambda: self.play_music("test")).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Müzik ekle…", bootstyle="secondary-outline",
                   command=lambda: self.add_file(MUZIK)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Klasörü aç", bootstyle="secondary-outline",
                   command=lambda: open_folder(MUZIK)).pack(side="left")
        self.hint(c, "Müzik, sonraki zilden 30 saniye önce yavaşça susar.").pack(anchor="w", pady=(10, 0))

        m = self.card(p, "Marşlar")
        m.pack(fill="x", pady=(24, 0))
        grid = ttk.Frame(m)
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1, uniform="m")
        for i, name in enumerate(audio_files(MARS)):
            label = march_label(name)
            style = "danger" if "siren" in label.lower() else "primary"
            ttk.Button(grid, text=label, bootstyle=style, padding=(10, 12),
                       command=lambda n=name, l=label: self.play_march(n, l)).grid(row=i // 2, column=i % 2, padx=(0, 8), pady=(0, 8), sticky="ew")
        row = ttk.Frame(m)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Ses").pack(side="left", padx=(0, 10))
        self.volume(row, self.cfg["march_volume"], lambda v: self.set_cfg("march_volume", v), length=140).pack(side="left")
        ttk.Button(row, text="Klasörü aç", bootstyle="secondary-outline",
                   command=lambda: open_folder(MARS)).pack(side="right")
        self.hint(m, "Marş çalarken gelen zil marşı kesmez; marş bitince çalar. Klasöre eklenen marşlar, "
                     "Zilli yeniden açılınca düğme olur.").pack(anchor="w", pady=(10, 0))

    def page_settings(self, p):
        c = self.card(p, "Görünüm")
        c.pack(fill="x")
        row = ttk.Frame(c)
        row.pack(fill="x")
        ttk.Label(row, text="Tema").pack(side="left", padx=(0, 10))
        names = dict(THEMES)
        th = ttk.Combobox(row, values=[n for _, n in THEMES], state="readonly", width=18)
        th.set(names.get(self.root.style.theme_use(), THEMES[0][1]))
        th.pack(side="left")

        def theme_changed(_):
            key = THEMES[th.current()][0]
            self.root.style.theme_use(key)
            self.apply_theme()
            self.set_cfg("theme", key)
        th.bind("<<ComboboxSelected>>", theme_changed)
        self.hint(c, "Yüksek kontrast, projeksiyon ve eski ekranlarda daha kolay okunur.").pack(anchor="w", pady=(8, 0))

        s = self.card(p, "Başlangıç")
        s.pack(fill="x", pady=(24, 0))
        auto = tk.BooleanVar(value=get_autostart())

        def auto_changed():
            try:
                set_autostart(auto.get())
            except OSError as ex:
                auto.set(not auto.get())
                messagebox.showerror(APP, "Ayarlanamadı: %s" % ex)
        ttk.Checkbutton(s, text="Bilgisayar açılınca Zilli otomatik başlasın", variable=auto,
                        bootstyle="success-round-toggle", command=auto_changed).pack(anchor="w")
        self.hint(s, "Zilli oturum açılınca başlar. Otomatik oturum açma (Windows: netplwiz) önerilmez: "
                     "bilgisayarı açan herkes o hesaba girer.").pack(anchor="w", pady=(8, 0))
        ttk.Label(s, text="Güvenlik: Otomatik oturum açacaksanız yalnızca zil için ayrı, yönetici olmayan bir hesap "
                          "kullanın; o hesapta e-posta, tarayıcı şifresi veya okul dosyası bulunmasın. Oturum açılınca "
                          "ekranı kilitleyin (Windows+L): Zilli kilitliyken de zil çalar.",
                  bootstyle="warning", wraplength=480).pack(anchor="w", pady=(8, 0))

        d = self.card(p, "Veri klasörü")
        d.pack(fill="x", pady=(24, 0))
        ttk.Button(d, text="Aç", bootstyle="secondary-outline", command=lambda: open_folder(DATA)).pack(side="right")
        ttk.Label(d, text=DATA, wraplength=420).pack(side="left")

    # --- işler ---
    def ring(self, ev, test=False):
        _, kind, n = ev
        b = self.cfg["bells"][kind]
        items = [(os.path.join(MELODI, b["melody"]), b["volume"])]
        if not test:
            self.music_hold = False
            self.add_log("%d. ders, %s" % (n, BELL_NAMES[kind].lower()) + ("" if self.cfg["bells_on"] else " (ziller kapalı)"))
            if not self.cfg["bells_on"]:
                return
        if self.player.kind == "march":  # marşı kesme, bitince çal
            self.player.error = missing_error(items)
            self.player.queue += [i for i in items if os.path.isfile(i[0])]
        else:
            self.player.play(items, "test" if test else "bell")
        if self.player.error:
            if test:
                messagebox.showerror(APP, self.player.error, parent=self.root)
            else:  # zamanlı zilde pencere açma (ders sırasında birikmesin); kayda ve üst bilgiye yaz
                self.add_log(self.player.error)

    def play_manual(self, items, kind):
        """Elle çalınan ses (marş, müzik): dosya yoksa veya açılamazsa hata penceresi."""
        self.player.play(items, kind)
        if self.player.error:
            messagebox.showerror(APP, self.player.error, parent=self.root)

    def play_music(self, kind):
        songs = audio_files(MUZIK)
        if not songs:
            if kind == "test":
                messagebox.showerror(APP, "Ses dosyası yok: Müzik klasörü boş.\n'Müzik ekle…' ile şarkı ekleyin.",
                                     parent=self.root)
            return
        item = [(os.path.join(MUZIK, random.choice(songs)), self.cfg["music"]["volume"])]
        if kind == "test":
            self.play_manual(item, kind)
        else:
            self.player.play(item, kind)

    def play_march(self, name, label):
        self.add_log(label)
        files = [name] + MARCH_CHAINS.get(name, [])
        self.play_manual([(os.path.join(MARS, f), self.cfg["march_volume"]) for f in files], "march")

    def stop(self):
        self.player.stop()
        self.music_hold = True

    def tick(self):
        try:
            if self.tick_once() == "quit":
                return
        except Exception as ex:  # tek bir hata zil döngüsünü durdurmasın
            msg = "Hata: %s" % ex
            if msg != self.last_error:
                self.last_error = msg
                self.add_log(msg)
        self.root.after(250, self.tick)

    def tick_once(self):
        while not self.commands.empty():
            c = self.commands.get_nowait()
            if isinstance(c, tuple):  # ("menu", x, y): SNI sağ tık
                self.tray_menu(c[1], c[2])
            elif c == "show":
                self.show_window()
            elif c == "stop":
                self.stop()
            elif c == "quit":
                self.show_window()
                if messagebox.askyesno(APP, "Program kapanırsa ziller ÇALMAZ.\nYine de kapatılsın mı?", parent=self.root):
                    self.exit_app()
                    return "quit"
        now = datetime.datetime.now()
        sec = now.hour * 3600 + now.minute * 60 + now.second
        if now.date() != self.date:  # ilk açılış veya gece yarısı
            self.date, self.last = now.date(), sec
            self.events = events_for(self.cfg, self.date)
            self.sched_key = None
            self.draw_timeline()
        ev = due_event(self.events, self.last, sec)
        self.last = sec
        if ev:
            self.ring(ev)

        self.player.poll()
        brk = in_break(self.events, sec)
        if self.player.kind == "music" and not brk:
            self.player.stop(fade_ms=3000)
        elif brk and self.cfg["music"]["on"] and self.player.kind is None and not self.music_hold:
            self.play_music("music")
        self.update_view(now, sec)

    def update_view(self, now, sec):
        self.clock.set(now.strftime("%H:%M"), now.strftime(":%S"))
        self.set_text(self.date_lbl, "%s, %d %s %d" % (GUNLER[now.weekday()], now.day, AYLAR[now.month - 1], now.year))

        # çalan ses: adı ve süresi; boştaysa durdur düğmesi sakin
        val = 0
        playing = bool(self.player.title)
        if playing:
            pos, d = max(0, pygame.mixer.music.get_pos()) / 1000.0, self.player.duration
            self.set_text(self.play_lbl, "Çalıyor: %s   %s" % (self.player.title, "%s / %s" % (mmss(pos), mmss(d)) if d else mmss(pos)))
            val = min(1000, int(1000 * pos / d)) if d else 0
        else:
            self.set_text(self.play_lbl, self.player.error)
        style = "danger" if self.player.error and not playing else "default"
        if self.shown.get("play_style") != style:
            self.shown["play_style"] = style
            self.play_lbl.configure(bootstyle=style)
        btn = "danger" if playing else "secondary-outline"
        if self.shown.get("stop_style") != btn:
            self.shown["stop_style"] = btn
            self.stop_btn.configure(bootstyle=btn)
        if val != self.bar_val:
            self.bar_val = val
            self.play_bar.configure(value=val)

        day = self.cfg["days"][day_key(now.date())]
        self.set_text(self.now_lbl, now_text(day["on"], day["lessons"], sec))
        if self.shown.get("now_min") != sec // 30:  # çizgi 30 sn'de bir kayar
            self.shown["now_min"] = sec // 30
            self.move_now(now)

        nxt = [e for e in self.events if e[0] > sec]
        if nxt:
            t, kind, n = nxt[0]
            self.set_text(self.next_name, BELL_NAMES[kind])
            self.countdown.set(countdown_text(t - sec), " kaldı")
            self.set_text(self.next_at, "Saat %s, %d. ders" % (fmt_hhmm(t), n))
        else:
            self.set_text(self.next_name, "Bugün başka zil yok")
            self.countdown.set("")
            self.set_text(self.next_at, "")

        key = (len(nxt), self.root.style.theme_use())
        if key != self.sched_key:  # sonraki zil listesi yalnızca zil geçince veya tema değişince yenilenir
            self.sched_key = key
            later = nxt[1:4]
            self.set_text(self.later_title, "Sonra" if later else "")
            for i, (t_lbl, d_lbl) in enumerate(self.later):
                if i < len(later):
                    t, kind, n = later[i]
                    self.set_text(t_lbl, fmt_hhmm(t))
                    self.set_text(d_lbl, "%s, %d. ders" % (BELL_NAMES[kind], n))
                else:
                    self.set_text(t_lbl, "")
                    self.set_text(d_lbl, "")

    def on_close(self):
        mini = "Sistem tepsisine küçült" if self.tray else "Görev çubuğuna küçült"
        d = MessageDialog("Zilli küçültülürse arka planda çalışmaya ve zilleri çalmaya devam eder.\n"
                          "Kapatılırsa ziller ÇALMAZ.", title=APP, parent=self.root, icon=Icon.question,
                          buttons=["İptal:secondary", "Kapat:danger", mini + ":success"], default=mini, localize=False)
        d.show()
        if d.result == mini:
            self.hide()
        elif d.result == "Kapat":
            self.exit_app()

    def exit_app(self):
        self.player.stop()
        if self.tray:
            self.tray.stop()
        self.root.destroy()


def bind_lock(port=SINGLE_PORT):
    """Tek kopya kilidi (iki kopya zilleri iki kez çalmasın): dinleyen soket, başka kopya çalışıyorsa None."""
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name != "nt":
        # Linux kapanan bağlantının portunu ~60 sn TIME_WAIT'te tutar; hemen yeniden açılış "zaten çalışıyor"
        # sanılmasın. Dinleyen bir kopya varsa bind yine başarısız olur. Windows'ta bu seçenek çalışan
        # dinleyicinin portunu ele geçirmeye izin verir, orada kullanılmaz.
        lock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        lock.bind(("127.0.0.1", port))
        lock.listen(2)
        return lock
    except OSError:
        lock.close()
        return None


def main():
    lock = bind_lock()
    if lock is None:
        try:  # zaten çalışıyor: açık pencereyi öne getir
            socket.create_connection(("127.0.0.1", SINGLE_PORT), timeout=2).sendall(b"show")
        except OSError:
            tk.Tk().withdraw()
            messagebox.showwarning(APP, "Zilli zaten çalışıyor.")
        return
    os.makedirs(DATA, exist_ok=True)
    cfg, err = load_config()
    try:
        ensure_data(cfg)
        save_config(cfg)
    except OSError:
        pass
    if os.environ.get("APPIMAGE") and not cfg["autostart_asked"]:  # AppImage'ı kuran yok; ilk açılışta kendini ekler
        cfg["autostart_asked"] = True
        try:
            set_autostart(True)
            save_config(cfg)
        except OSError:
            pass
    load_fonts()  # pencere açılmadan: Tk yazı tiplerini ilk kullanımda arar
    root = ttk.Window(themename="flatly")  # pencere hazır olsun; hemen Zilli temasına geçilir
    register_themes(root.style)
    root.style.theme_use(cfg["theme"] if cfg["theme"] in THEME_COLORS else "acik")
    app = App(root, cfg)
    root.update_idletasks()
    root.place_window_center()  # kayıtlı/varsayılan konum ekran dışında kalmasın
    threading.Thread(target=app.listen, args=(lock,), daemon=True).start()
    if err:
        messagebox.showwarning(APP, err)
    if "--min" in sys.argv:
        app.hide()
    root.mainloop()


if __name__ == "__main__":
    main()

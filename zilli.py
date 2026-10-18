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
    # Tcl yolu ANSI'ye çevirir; kullanıcı adındaki Türkçe harfler (ş, ı...) bozulursa init.tcl bulunamaz.
    # Kısa (8.3) yol her zaman ASCII'dir.
    import ctypes
    for _var in ("TCL_LIBRARY", "TK_LIBRARY"):
        _p = os.environ.get(_var, "")
        if _p and not _p.isascii():
            _buf = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.kernel32.GetShortPathNameW(_p, _buf, 1024):
                os.environ[_var] = _buf.value

import tkinter as tk  # noqa: E402
from tkinter import filedialog, font as tkfont, messagebox  # noqa: E402

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402
import ttkbootstrap as ttk  # noqa: E402
from ttkbootstrap.style import Colors  # noqa: E402
from ttkbootstrap.dialogs import MessageDialog  # noqa: E402
from ttkbootstrap.icons import Icon  # noqa: E402

APP, VERSION = "Zilli", "1.0.0"
BASE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "assets")
# Windows'ta program kullanıcı klasörüne kurulur (yazılabilir); Linux'ta AppImage/deb salt okunur, veriler ~/Zilli'de.
DATA = os.environ.get("ZILLI_DATA") or (BASE if os.name == "nt" else os.path.expanduser("~/Zilli"))
CONFIG_PATH = os.path.join(DATA, "zilli.json")
FOLDERS = ("Melodiler", "Marşlar", "Müzik")
MELODI, MARS, MUZIK = (os.path.join(DATA, d) for d in FOLDERS)
AUDIO_EXT = (".mp3", ".wav", ".ogg", ".flac", ".mid", ".midi")
DAYS = [("haftaici", "Hafta İçi"), ("cumartesi", "Cumartesi"), ("pazar", "Pazar")]
DAY_TOGGLE = {"haftaici": "Hafta içi zil çalsın", "cumartesi": "Cumartesileri zil çalsın",
              "pazar": "Pazarları zil çalsın"}
# sıra: öğrenci zili (dersten önce), öğretmen zili (ders başı), teneffüs zili (ders sonu; ayar anahtarı "cikis")
BELLS = [("ogrenci", "Öğrenci Zili"), ("ogretmen", "Öğretmen Zili"), ("cikis", "Teneffüs Zili")]
BELL_NAMES = dict(BELLS + [("son", "Son Zil")])
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
    "theme": "flatly",
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
    "marches": {"istiklalmarsi.mp3": "İstiklal Marşı", "saygidurusu.mp3": "Saygı Duruşu + İstiklal Marşı",
                "siren.mp3": "Siren"},
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
SOUNDS_VERSION = 2  # programla gelen ses seti değişince artır: eksik dosyalar veri klasörüne bir kez kopyalanır


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


# Supper Zill'den kalan numaralı dosya adları → okunur adlar
MARCH_CHAINS = {"saygidurusu.mp3": ["istiklalmarsi.mp3"]}  # saygı duruşunun ardından marş hemen çalar
RENAMES = {"Marşlar": {"0.mp3": "istiklalmarsi.mp3", "1.mp3": "saygidurusu.mp3", "2.mp3": "siren.mp3"}}


OLD_DEFAULT_MELODIES = {"ogretmen": "Melodi 5.wav", "ogrenci": "Melodi 6.wav", "cikis": "Melodi 1.wav"}


def migrate_names(cfg, data):
    """Eski adlı dosyaları yeniden adlandırır, ayarlardaki adları günceller. Yeni adlısı zaten varsa eski
    dosya silinmez, düğme listesinde görünmesin diye Eski/ alt klasörüne taşınır."""
    for folder, names in RENAMES.items():
        for old, new in names.items():
            o, n = os.path.join(data, folder, old), os.path.join(data, folder, new)
            if not os.path.exists(o):
                continue
            if os.path.exists(n):
                os.makedirs(os.path.join(data, folder, "Eski"), exist_ok=True)
                n = os.path.join(data, folder, "Eski", old)
            os.replace(o, n)
    cfg.pop("anons_on", None)  # anons özelliği kaldırıldı
    for b in cfg["bells"].values():
        b.pop("anons", None)
    # eski varsayılan melodiler hiç değiştirilmemişse MEB zillerine geç
    if all(cfg["bells"][k]["melody"] == v for k, v in OLD_DEFAULT_MELODIES.items()):
        for k in OLD_DEFAULT_MELODIES:
            new = DEFAULT_CONFIG["bells"][k]["melody"]
            if os.path.exists(os.path.join(data, "Melodiler", new)):
                cfg["bells"][k]["melody"] = new


def check_config(cfg):
    """Elle bozulmuş ayarları açılışta yakalar (yoksa zil döngüsü çalışırken patlardı); hatada istisna atar."""
    for key, _ in DAYS:
        day = cfg["days"][key]
        day["on"] = bool(day["on"])
        day["lessons"] = validate_lessons([(str(s), str(e)) for s, e in day["lessons"]])
    cfg["teacher_offset"] = max(0, int(cfg["teacher_offset"]))
    for key in ("ogrenci", "ogretmen", "cikis", "son"):
        b = cfg["bells"][key]
        b["melody"], b["volume"] = str(b["melody"]), max(0, min(100, int(b["volume"])))
    cfg["music"]["volume"] = max(0, min(100, int(cfg["music"]["volume"])))
    cfg["march_volume"] = max(0, min(100, int(cfg["march_volume"])))
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
        from jeepney import HeaderFields, MessageType, new_error, new_method_return
        while True:
            try:
                msg = self.conn.receive()
            except Exception:  # bağlantı kapandı
                return
            if msg.header.message_type != MessageType.method_call:
                continue
            member = msg.header.fields.get(HeaderFields.member)
            if member in ("Activate", "SecondaryActivate"):
                self.send("show")
                reply = new_method_return(msg)
            elif member == "ContextMenu":
                self.send(("menu",) + tuple(msg.body))
                reply = new_method_return(msg)
            elif member == "Scroll":
                reply = new_method_return(msg)
            elif member == "GetAll":
                reply = new_method_return(msg, "a{sv}", (self.props,))
            elif member == "Get" and msg.body[1] in self.props:
                reply = new_method_return(msg, "v", (self.props[msg.body[1]],))
            elif member == "Introspect":
                reply = new_method_return(msg, "s", (SNI_INTROSPECT,))
            else:
                reply = new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod")
            try:
                self.conn.send(reply)
            except Exception:
                return

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
        ttk.Label(self.tip, text=self.text, bootstyle="inverse-success", padding=(10, 4)).pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def pick_font():
    have = set(tkfont.families())
    for f in ("Segoe UI", "Ubuntu", "Noto Sans", "Cantarell", "DejaVu Sans"):
        if f in have:
            return f
    return "Helvetica"


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
            tkfont.nametofont(name).configure(family=self.F, size=10)

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

        side = ttk.Frame(root, bootstyle="primary", padding=(0, 18))
        side.pack(side="left", fill="y")
        self.side_title = ttk.Label(side, text=" Zilli", image=self.logo, compound="left", font=(self.F, 24, "bold"),
                                    bootstyle="inverse-primary")
        self.side_title.pack(padx=14)
        self.side_sub = ttk.Label(side, text="Okul Zil Sistemi", bootstyle="inverse-primary")
        self.side_sub.pack(padx=14, pady=(0, 22))
        self.page_var = tk.StringVar(value="pano")
        self.pages, self.nav, self.nav_titles = {}, [], []
        main = self.main = ttk.Frame(root, padding=(22, 16))
        main.pack(side="left", fill="both", expand=True)
        self.build_header(main)
        body = ttk.Frame(main)
        body.pack(fill="both", expand=True, pady=(14, 0))
        for key, title, short, builder in (("pano", "Pano", "Pano", self.page_dashboard),
                                           ("saat", "Zil Saatleri", "Saatler", self.page_schedule),
                                           ("melodi", "Melodiler", "Melodi", self.page_bells),
                                           ("muzik", "Müzik ve Marşlar", "Müzik", self.page_music),
                                           ("ayar", "Ayarlar", "Ayarlar", self.page_settings)):
            page = ttk.Frame(body)
            builder(page)
            self.pages[key] = page
            # düz tk düğmesi: renkleri temadan biz veririz (style_nav)
            b = tk.Radiobutton(side, text="   " + title, value=key, variable=self.page_var, command=self.show_page,
                               indicatoron=False, anchor="w", relief="flat", bd=0, highlightthickness=0,
                               padx=18, pady=10, width=20, font=(self.F, 11), cursor="hand2", autostyle=False)
            b.pack(fill="x")
            self.nav.append(b)
            self.nav_titles.append((title, short))
        ver = self.ver = ttk.Label(side, text="Sürüm " + VERSION, bootstyle="inverse-primary", cursor="hand2")
        ver.pack(side="bottom", anchor="w", padx=18)
        Bubble(ver, "Gökay")
        root.bind("<Configure>", self.on_resize)
        self.style_nav()
        self.show_page()
        self.start_tray()
        root.bind("<Unmap>", self.on_unmap)
        root.report_callback_exception = lambda exc, val, tb: self.add_log("Hata: %s" % val)  # Windows'ta konsol yok
        self.tick()

    def on_resize(self, e):
        """Dar pencerede kenar çubuğu kısa yazılara geçer, saat küçülür."""
        if e.widget is not self.root:
            return
        compact = e.width < 820
        if compact == self.compact:
            return
        self.compact = compact
        self.side_title.configure(text="" if compact else " Zilli")
        self.side_sub.configure(text="" if compact else "Okul Zil Sistemi")
        for b, (title, short) in zip(self.nav, self.nav_titles):
            b.configure(text=(" " + short) if compact else ("   " + title), width=8 if compact else 20,
                        padx=10 if compact else 18)
        self.ver.configure(text=VERSION if compact else "Sürüm " + VERSION)
        self.main.configure(padding=(12, 10) if compact else (22, 16))
        self.clock.configure(font=(self.F, 26 if compact else 34, "bold"))
        self.next_lbl.configure(wraplength=180 if compact else 0)
        self.play_lbl.configure(wraplength=180 if compact else 0)
        self.info.pack_configure(padx=10 if compact else 18)

    # --- yardımcılar ---
    def save(self):
        try:
            save_config(self.cfg)
        except OSError as ex:
            messagebox.showerror(APP, "Ayarlar kaydedilemedi: %s" % ex)
        self.events = events_for(self.cfg, self.date) if self.date else []
        self.sched_key = None

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

    def style_nav(self):
        c = self.root.style.colors
        self.root.style.configure("info.Horizontal.TProgressbar", thickness=4)
        for b in self.nav:
            b.configure(bg=c.primary, fg=c.selectfg, activebackground=Colors.update_hsv(c.primary, vd=0.06),
                        activeforeground=c.selectfg, selectcolor=Colors.update_hsv(c.primary, vd=0.14))

    def show_page(self):
        for p in self.pages.values():
            p.pack_forget()
        self.pages[self.page_var.get()].pack(fill="both", expand=True)

    def card(self, parent, title):
        f = ttk.Labelframe(parent, text="  %s  " % title, padding=14, bootstyle="secondary")
        return f

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
        self.clock = ttk.Label(h, font=(self.F, 34, "bold"))
        self.clock.pack(side="left")
        info = self.info = ttk.Frame(h)
        info.pack(side="left", padx=18)
        self.date_lbl = ttk.Label(info, font=(self.F, 11), bootstyle="secondary")
        self.date_lbl.pack(anchor="w")
        self.next_lbl = ttk.Label(info, font=(self.F, 12, "bold"))
        self.next_lbl.pack(anchor="w")
        self.play_lbl = ttk.Label(info, bootstyle="info", font=(self.F, 10))
        self.play_lbl.pack(anchor="w")
        right = ttk.Frame(h)
        right.pack(side="right")
        ttk.Button(right, text="■  Sesi Durdur", bootstyle="danger", padding=(16, 10), command=self.stop).pack(fill="x")
        self.bells_var = tk.BooleanVar(value=self.cfg["bells_on"])
        ttk.Checkbutton(right, text="Ziller aktif", variable=self.bells_var, bootstyle="success-round-toggle",
                        command=lambda: self.set_cfg("bells_on", self.bells_var.get())).pack(anchor="e", pady=(8, 0))
        # çalarken dolan ince çubuk; boşken ayırıcı çizgi gibi görünür
        self.play_bar = ttk.Progressbar(main, maximum=1000, bootstyle="info")
        self.play_bar.pack(fill="x", pady=(12, 0))
        self.bar_val = 0

    # --- sayfalar ---
    def page_dashboard(self, p):
        top = ttk.Frame(p)
        top.pack(fill="x")
        c1 = self.card(top, "Şu an")
        c1.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.period_lbl = ttk.Label(c1, font=(self.F, 18, "bold"))
        self.period_lbl.pack(anchor="w")
        self.period_bar = ttk.Progressbar(c1, maximum=1000, bootstyle="success-striped")
        self.period_bar.pack(fill="x", pady=(10, 4))
        self.period_info = ttk.Label(c1, bootstyle="secondary")
        self.period_info.pack(anchor="w")
        c2 = self.card(top, "Sonraki zil")
        c2.pack(side="left", fill="both", expand=True)
        self.count_lbl = ttk.Label(c2, font=(self.F, 18, "bold"), bootstyle="info")
        self.count_lbl.pack(anchor="w")
        self.count_info = ttk.Label(c2, bootstyle="secondary")
        self.count_info.pack(anchor="w", pady=(12, 0))

        low = ttk.Frame(p)
        low.pack(fill="both", expand=True, pady=(14, 0))
        c3 = self.card(low, "Bugünün zilleri")
        c3.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.today = ttk.Treeview(c3, columns=("t", "n", "k"), show="headings", height=8, bootstyle="primary")
        for col, title, w in (("t", "Saat", 60), ("n", "Ders", 60), ("k", "Zil", 110)):
            self.today.heading(col, text=title, anchor="w")
            self.today.column(col, width=w, minwidth=40, anchor="w")
        self.today.pack(fill="both", expand=True)
        c4 = self.card(low, "Son olaylar")
        c4.pack(side="left", fill="both", expand=True)
        self.log = ttk.Treeview(c4, columns=("t", "m"), show="headings", height=8)
        self.log.heading("t", text="Saat", anchor="w")
        self.log.heading("m", text="Olay", anchor="w")
        self.log.column("t", width=60, minwidth=40, anchor="w")
        self.log.column("m", width=160, minwidth=60, anchor="w")
        self.log.pack(fill="both", expand=True)

    def page_schedule(self, p):
        top = ttk.Frame(p)
        top.pack(fill="x")
        self.day_var = tk.StringVar(value="haftaici")
        for key, name in DAYS:
            ttk.Radiobutton(top, text=name, value=key, variable=self.day_var, bootstyle="primary-outline-toolbutton",
                            padding=(10, 6), command=self.show_day).pack(side="left")
        off = ttk.Combobox(top, values=[n for _, n in OFFSETS], state="readonly", width=14)
        off.set(dict(OFFSETS).get(self.cfg["teacher_offset"], OFFSETS[0][1]))
        off.pack(side="right")
        ttk.Label(top, text="Öğrenci zili:").pack(side="right", padx=(12, 6))
        off.bind("<<ComboboxSelected>>", lambda _: self.set_cfg("teacher_offset", OFFSETS[off.current()][0]))
        holder = ttk.Frame(p)
        holder.pack(fill="both", expand=True, pady=(10, 0))
        self.day_frames = {}
        for key, name in DAYS:
            self.day_frames[key] = self.day_editor(holder, key, name)
        self.show_day()

    def show_day(self):
        for f in self.day_frames.values():
            f.pack_forget()
        self.day_frames[self.day_var.get()].pack(fill="both", expand=True)

    def day_editor(self, holder, key, name):
        day = self.cfg["days"][key]
        f = self.card(holder, name + " ders saatleri (SS:DD, boş satırlar atlanır)")
        on = tk.BooleanVar(value=day["on"])
        ttk.Checkbutton(f, text=DAY_TOGGLE[key], variable=on,
                        bootstyle="success-round-toggle").grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 4))
        rows = []
        for c in (0, 4):
            ttk.Label(f, text="Giriş", bootstyle="secondary").grid(row=1, column=c + 1)
            ttk.Label(f, text="Çıkış", bootstyle="secondary").grid(row=1, column=c + 2)
        for i in range(MAX_LESSONS):
            r, c = i % 8 + 2, i // 8 * 4
            s, e = day["lessons"][i] if i < len(day["lessons"]) else ("", "")
            sv, ev = tk.StringVar(value=s), tk.StringVar(value=e)
            ttk.Label(f, text="%d. ders" % (i + 1)).grid(row=r, column=c, sticky="w", padx=(30 if c else 0, 8), pady=1)
            ttk.Entry(f, textvariable=sv, width=7, justify="center").grid(row=r, column=c + 1, padx=3, pady=1)
            ttk.Entry(f, textvariable=ev, width=7, justify="center").grid(row=r, column=c + 2, padx=3, pady=1)
            rows.append((sv, ev))

        def save():
            try:
                lessons = validate_lessons([(s.get(), e.get()) for s, e in rows])
            except ValueError as ex:
                messagebox.showerror(APP, str(ex))
                return
            self.cfg["days"][key] = {"on": on.get(), "lessons": lessons}
            self.save()
            for i, (sv, ev) in enumerate(rows):  # kaydedilen düzeni göster (boşluklar kapanır)
                sv.set(lessons[i][0] if i < len(lessons) else "")
                ev.set(lessons[i][1] if i < len(lessons) else "")
            messagebox.showinfo(APP, "%s ders saatleri kaydedildi." % name)
        ttk.Button(f, text="Kaydet", bootstyle="success", padding=(22, 6), command=save).grid(
            row=0, column=5, columnspan=3, sticky="e", pady=(0, 4))
        return f

    def bell_card(self, parent, key, title):
        b = self.cfg["bells"][key]
        c = self.card(parent, title)
        mel = ttk.Combobox(c, state="readonly", width=22)
        mel.set(b["melody"])
        mel.grid(row=0, column=0, padx=(0, 12))
        warn = ttk.Label(c, text="", bootstyle="danger")
        warn.grid(row=1, column=0, columnspan=3, sticky="w")

        def changed(_=None):
            b["melody"] = mel.get()
            self.save()
            self.refresh_lists()

        def vol_changed(v):
            b["volume"] = v
            self.save()
        mel.bind("<<ComboboxSelected>>", changed)
        self.volume(c, b["volume"], vol_changed, length=90).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(c, text="▶  Dinle", bootstyle="info-outline",
                   command=lambda: self.ring((0, key, 0), test=True)).grid(row=0, column=2)
        self.bell_widgets.append((mel, warn, key))
        return c

    def page_bells(self, p):
        self.bell_widgets = []
        for key, name in BELLS:
            self.bell_card(p, key, name).pack(fill="x", pady=(0, 8))
        son = self.bell_card(p, "son", "Son Zil · günün son dersi bitince çalar")

        def toggle_son():
            if son.winfo_manager():
                son.pack_forget()
                btn.configure(text="▸  Son Zil")
            else:
                son.pack(fill="x", pady=(0, 8), after=btn)
                btn.configure(text="▾  Son Zil")
        btn = ttk.Button(p, text="▸  Son Zil", bootstyle="secondary-link", command=toggle_son)
        btn.pack(anchor="w")
        self.refresh_lists()
        bar = ttk.Frame(p)
        bar.pack(fill="x", pady=(8, 0))
        for text, cmd in (("Melodi ekle…", lambda: self.add_file(MELODI, self.refresh_lists)),
                          ("Klasörü aç", lambda: open_folder(MELODI))):
            ttk.Button(bar, text=text, bootstyle="secondary-outline", command=cmd).pack(side="left", padx=(0, 6))

    def refresh_lists(self):
        mels = audio_files(MELODI)
        for mel, warn, key in self.bell_widgets:
            mel.configure(values=mels)
            name = self.cfg["bells"][key]["melody"]
            warn.configure(text="" if name in mels else "Ses dosyası yok: %s" % (name or "(seçilmedi)"))

    def page_music(self, p):
        c = self.card(p, "Teneffüs müziği")
        c.pack(fill="x")
        on = tk.BooleanVar(value=self.cfg["music"]["on"])
        ttk.Checkbutton(c, text="Teneffüslerde Müzik klasöründen rastgele çal", variable=on, bootstyle="round-toggle",
                        command=lambda: (self.cfg["music"].update(on=on.get()), self.save())).pack(anchor="w")
        row = ttk.Frame(c)
        row.pack(fill="x", pady=(12, 0))
        ttk.Label(row, text="Ses").pack(side="left", padx=(0, 8))

        def vol(v):
            self.cfg["music"]["volume"] = v
            self.save()
        self.volume(row, self.cfg["music"]["volume"], vol, length=120).pack(side="left")
        row = ttk.Frame(c)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="▶  Hemen çal", bootstyle="info",
                   command=lambda: self.play_music("test")).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Müzik ekle…", bootstyle="secondary-outline",
                   command=lambda: self.add_file(MUZIK)).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Klasörü aç", bootstyle="secondary-outline",
                   command=lambda: open_folder(MUZIK)).pack(side="left")
        ttk.Label(c, text="Müzik, sonraki zilden 30 saniye önce yavaşça susar.", bootstyle="secondary",
                  wraplength=460).pack(anchor="w", pady=(8, 0))

        m = self.card(p, "Marşlar")
        m.pack(fill="x", pady=(12, 0))
        grid = ttk.Frame(m)
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1, uniform="m")
        for i, name in enumerate(audio_files(MARS)):
            label = self.cfg["marches"].get(name, os.path.splitext(name)[0])
            style = "danger" if "siren" in label.lower() else "primary"
            ttk.Button(grid, text="▶  " + label, bootstyle=style, padding=(10, 10),
                       command=lambda n=name, l=label: self.play_march(n, l)).grid(row=i // 2, column=i % 2, padx=3, pady=3, sticky="ew")
        row = ttk.Frame(m)
        row.pack(fill="x", pady=(12, 0))
        ttk.Label(row, text="Ses").pack(side="left", padx=(0, 8))
        self.volume(row, self.cfg["march_volume"], lambda v: self.set_cfg("march_volume", v), length=120).pack(side="left")
        ttk.Button(row, text="Klasörü aç", bootstyle="secondary-outline",
                   command=lambda: open_folder(MARS)).pack(side="right")
        ttk.Label(m, text="Gelen zil marşı kesmez, marş bitince çalar. Yeni marşlar yeniden açılınca görünür.",
                  bootstyle="secondary", wraplength=460).pack(anchor="w", pady=(8, 0))

    def page_settings(self, p):
        c = self.card(p, "Görünüm")
        c.pack(fill="x")
        ttk.Label(c, text="Tema").pack(side="left", padx=(0, 10))
        themes = sorted(self.root.style.theme_names())
        th = ttk.Combobox(c, values=themes, state="readonly", width=18)
        th.set(self.root.style.theme_use())
        th.pack(side="left")

        def theme_changed(_):
            self.root.style.theme_use(th.get())
            self.style_nav()
            self.set_cfg("theme", th.get())
        th.bind("<<ComboboxSelected>>", theme_changed)
        ttk.Label(c, text="Koyu: darkly, superhero, cyborg, solar, vapor", bootstyle="secondary",
                  wraplength=220).pack(side="left", padx=12)

        s = self.card(p, "Başlangıç")
        s.pack(fill="x", pady=(12, 0))
        auto = tk.BooleanVar(value=get_autostart())

        def auto_changed():
            try:
                set_autostart(auto.get())
            except OSError as ex:
                auto.set(not auto.get())
                messagebox.showerror(APP, "Ayarlanamadı: %s" % ex)
        ttk.Checkbutton(s, text="Bilgisayar açılınca Zilli otomatik başlasın", variable=auto,
                        bootstyle="success-round-toggle", command=auto_changed).pack(anchor="w")
        ttk.Label(s, text="Zilli oturum açılınca başlar. Otomatik oturum açma (Windows: netplwiz) önerilmez: "
                          "bilgisayarı açan herkes o hesaba girer.",
                  bootstyle="secondary", wraplength=460).pack(anchor="w", pady=(8, 0))
        ttk.Label(s, text="⚠ Güvenlik: Otomatik oturum açacaksanız yalnızca zil için ayrı, yönetici olmayan bir hesap "
                          "kullanın; o hesapta e-posta, tarayıcı şifresi veya okul dosyası bulunmasın. Oturum açılınca "
                          "ekranı kilitleyin (Windows+L): Zilli kilitliyken de zil çalar.",
                  bootstyle="warning", wraplength=460).pack(anchor="w", pady=(6, 0))

        d = self.card(p, "Veri klasörü")
        d.pack(fill="x", pady=(12, 0))
        ttk.Button(d, text="Aç", bootstyle="secondary-outline", command=lambda: open_folder(DATA)).pack(side="right")
        ttk.Label(d, text=DATA, wraplength=400).pack(side="left")

    # --- işler ---
    def ring(self, ev, test=False):
        _, kind, n = ev
        b = self.cfg["bells"][kind]
        items = [(os.path.join(MELODI, b["melody"]), b["volume"])]
        if not test:
            self.music_hold = False
            self.add_log("%d. ders %s" % (n, BELL_NAMES[kind]) + ("" if self.cfg["bells_on"] else " (ziller kapalı)"))
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
        self.set_text(self.clock, now.strftime("%H:%M:%S"))
        self.set_text(self.date_lbl, "%s, %d %s %d" % (GUNLER[now.weekday()], now.day, AYLAR[now.month - 1], now.year))
        nxt = [e for e in self.events if e[0] > sec]
        if nxt:
            t, kind, n = nxt[0]
            left = t - sec
            self.set_text(self.next_lbl, "Sonraki: %s · %d. ders %s" % (fmt_hhmm(t), n, BELL_NAMES[kind]))
            self.set_text(self.count_lbl, "%d dk %02d sn" % (left // 60, left % 60) if left < 3600
                          else "%d sa %02d dk" % (left // 3600, left % 3600 // 60))
            self.set_text(self.count_info, "%s · %d. ders %s" % (fmt_hhmm(t), n, BELL_NAMES[kind]))
        else:
            for w in (self.next_lbl, self.count_lbl):
                self.set_text(w, "Bugün başka zil yok")
            self.set_text(self.count_info, "")
        val = 0
        if self.player.title:
            pos, d = max(0, pygame.mixer.music.get_pos()) / 1000.0, self.player.duration
            self.set_text(self.play_lbl, "♪  %s   %s" % (self.player.title, "%s / %s" % (mmss(pos), mmss(d)) if d else mmss(pos)))
            val = min(1000, int(1000 * pos / d)) if d else 0
        else:
            self.set_text(self.play_lbl, self.player.error)
        style = "danger" if self.player.error and not self.player.title else "info"
        if self.shown.get("play_style") != style:
            self.shown["play_style"] = style
            self.play_lbl.configure(bootstyle=style)
        if val != self.bar_val:
            self.bar_val = val
            self.play_bar.configure(value=val)

        day = self.cfg["days"][day_key(now.date())]
        label, s, e = current_period(day["lessons"], sec) if day["on"] else ("Bugün zil yok", None, None)
        self.set_text(self.period_lbl, label)
        if s is None:
            self.period_bar.configure(value=0)
            self.set_text(self.period_info, "")
        else:
            self.period_bar.configure(value=1000 * (sec - s) // (e - s))
            self.set_text(self.period_info, "%s – %s · %d dk kaldı" % (fmt_hhmm(s), fmt_hhmm(e), (e - sec + 59) // 60))

        key = (len(nxt), self.root.style.theme_use())
        if key != self.sched_key:  # tablo yalnızca zil geçince veya tema değişince yenilenir
            self.sched_key = key
            colors = self.root.style.colors
            self.today.tag_configure("past", foreground=colors.secondary)
            self.today.tag_configure("next", foreground=colors.selectfg, background=colors.primary)
            self.today.delete(*self.today.get_children())
            for i, (t, kind, n) in enumerate(self.events):
                tag = "past" if t <= sec else "next" if nxt and (t, kind, n) == nxt[0] else ""
                self.today.insert("", "end", values=(fmt_hhmm(t), "%d. ders" % n, BELL_NAMES[kind]), tags=(tag,))

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


def main():
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", SINGLE_PORT))  # aynı anda iki kopya zilleri iki kez çalmasın
        lock.listen(2)
    except OSError:
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
        migrate_names(cfg, DATA)
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
    try:
        root = ttk.Window(themename=cfg["theme"])
    except tk.TclError:  # bilinmeyen tema adı
        root = ttk.Window(themename="flatly")
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

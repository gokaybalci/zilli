# Zil mantığı testleri. Çalıştırma: python test_zilli.py
import datetime

from zilli import (DEFAULT_CONFIG, LATE_LIMIT, current_period, day_key, due_event, events_for, fmt_hhmm,
                   in_break, merge, parse_hhmm, validate_lessons)

assert parse_hhmm("08:30") == 30600 and parse_hhmm(" 8:05 ") == 29100
for bad in ("24:00", "8.30", "08:60", "abc", ""):
    try:
        parse_hhmm(bad)
        raise AssertionError(bad)
    except ValueError:
        pass
assert fmt_hhmm(30600) == "08:30" and fmt_hhmm(86400 + 60) == "00:01" and fmt_hhmm(-60) == "23:59"
assert day_key(datetime.date(2026, 10, 16)) == "haftaici"  # Cuma
assert day_key(datetime.date(2026, 10, 17)) == "cumartesi" and day_key(datetime.date(2026, 10, 18)) == "pazar"

assert validate_lessons([("08:30", "09:10"), ("", ""), ("9:20", "10:00")]) == [["08:30", "09:10"], ["09:20", "10:00"]]
for rows, msg in (([("09:10", "08:30")], "1. ders"), ([("08:30", "09:10"), ("09:00", "09:40")], "2. ders"),
                  ([("08:30", "")], "1. ders")):
    try:
        validate_lessons(rows)
        raise AssertionError(rows)
    except ValueError as ex:
        assert str(ex).startswith(msg), ex

cfg = merge(dict(DEFAULT_CONFIG), {"days": {"haftaici": {"on": True, "lessons": [["08:30", "09:10"], ["09:20", "10:00"]]}}})
ev = events_for(cfg, datetime.date(2026, 10, 16))
assert ev == [(30540, "ogrenci", 1), (30600, "ogretmen", 1), (33000, "cikis", 1),
              (33540, "ogrenci", 2), (33600, "ogretmen", 2), (36000, "son", 2)], ev  # son zil ayrı
assert events_for(cfg, datetime.date(2026, 10, 18)) == []  # pazar kapalı

assert due_event(ev, 30599, 30600)[1] == "ogretmen"
assert due_event(ev, 30500, 30600)[1] == "ogretmen"  # iki zil kaçtıysa yalnız sonuncusu
assert due_event(ev, 30000, 30600 + LATE_LIMIT) is None  # çok eski: çalma
assert due_event(ev, 30600, 30601) is None

assert not in_break(ev, 32000) and in_break(ev, 33100) and not in_break(ev, 33530)
assert not in_break(ev, 36100)  # son dersten sonra müzik yok

lessons = cfg["days"]["haftaici"]["lessons"]
assert current_period(lessons, 30000) == ("Okul başlamadı", None, None)
assert current_period(lessons, 31000) == ("1. ders", 30600, 33000)
assert current_period(lessons, 33100) == ("Teneffüs", 33000, 33600)
assert current_period(lessons, 36000) == ("Okul bitti", None, None)
assert current_period([], 36000)[0] == "Bugün ders yok"
import copy, os, tempfile

# ses süresi başlıktan okunur (ilerleme çubuğu); örnek dosyalar burada üretilir, sounds/ kullanıcıya ait
from zilli import audio_duration, mmss
FRAME = b"\xff\xfb\x90\x00"  # MPEG1 katman 3, 128 kbps, 44100 Hz, stereo
with tempfile.TemporaryDirectory() as d:
    cbr = os.path.join(d, "sabit.mp3")  # ID3 etiketi + 128000 bayt ses = 8 sn
    open(cbr, "wb").write(b"ID3\x03\x00\x00\x00\x00\x00\x0a" + b"\0" * 10 + FRAME + b"\0" * (128000 - 4))
    assert abs(audio_duration(cbr) - 8.0) < 0.01, audio_duration(cbr)
    vbr = os.path.join(d, "degisken.mp3")  # Xing başlığı: 1000 çerçeve x 1152 örnek / 44100
    open(vbr, "wb").write(FRAME + b"\0" * 32 + b"Xing" + (1).to_bytes(4, "big") + (1000).to_bytes(4, "big") + b"\0" * 5000)
    assert abs(audio_duration(vbr) - 1000 * 1152 / 44100.0) < 0.01, audio_duration(vbr)
    import wave as wavemod
    w = wavemod.open(os.path.join(d, "a.wav"), "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\0\0" * 12000)
    w.close()
    assert audio_duration(os.path.join(d, "a.wav")) == 1.5
with tempfile.TemporaryDirectory() as d:
    flac = os.path.join(d, "a.flac")  # 44100 Hz, 441000 örnek = 10 sn
    v = (44100 << 44) | 441000
    open(flac, "wb").write(b"fLaC" + b"\x80\x00\x00\x22" + b"\0" * 10 + v.to_bytes(8, "big") + b"\0" * 16)
    assert audio_duration(flac) == 10.0
    ogg = os.path.join(d, "a.ogg")  # vorbis 44100 Hz, son sayfa granule 882000 = 20 sn
    open(ogg, "wb").write(b"OggS\x00\x02" + b"\0" * 22 + b"\x01vorbis" + b"\0" * 5 + (44100).to_bytes(4, "little")
                          + b"\0" * 100 + b"OggS\x00\x04" + (882000).to_bytes(8, "little") + b"\0" * 20)
    assert audio_duration(ogg) == 20.0
    open(os.path.join(d, "bozuk.mp3"), "wb").write(b"cop")
    assert audio_duration(os.path.join(d, "bozuk.mp3")) is None and audio_duration(os.path.join(d, "yok.wav")) is None
assert mmss(65.4) == "1:05" and mmss(0) == "0:00"
# elle bozulmuş ayarlar açılışta yakalanır; eksik ses dosyası adıyla bildirilir
from zilli import check_config, missing_error
c = copy.deepcopy(DEFAULT_CONFIG)
c["bells"]["cikis"]["volume"] = "250"
assert check_config(c)["bells"]["cikis"]["volume"] == 100
for bad in ({"days": {"haftaici": {"on": True, "lessons": [["25:99", "26:00"]]}}},
            {"days": {"pazar": {"on": True, "lessons": "08:30"}}}, {"teacher_offset": "çok"}):
    try:
        check_config(merge(copy.deepcopy(DEFAULT_CONFIG), bad))
        raise AssertionError(bad)
    except (ValueError, TypeError, KeyError, AttributeError):
        pass
with tempfile.TemporaryDirectory() as d:
    ok = os.path.join(d, "var.mp3")
    open(ok, "wb").write(b"x")
    assert missing_error([(ok, 100)]) == ""
    assert missing_error([(ok, 100), (os.path.join(d, "yok.mp3"), 100), (d + os.sep, 100)]) == \
        "Ses dosyası yok: yok.mp3, (seçilmedi)"
# tek kopya kilidi: çalışan kopya ikinciyi engeller; "show" bağlantısından hemen sonra yeniden açılış engellenmez
import socket, threading
from zilli import bind_lock
port = 47391  # gerçek Zilli'nin portuyla (47392) çakışmasın
first = bind_lock(port)
assert first is not None and bind_lock(port) is None  # ikinci kopya açılamaz

def answer():  # App.listen gibi: oku ve önce sunucu kapatsın (Linux'ta port TIME_WAIT'e düşer)
    conn, _ = first.accept()
    conn.recv(16)
    conn.close()
t = threading.Thread(target=answer)
t.start()
socket.create_connection(("127.0.0.1", port), timeout=2).sendall(b"show")
t.join(5)
first.close()  # Zilli kapandı
again = bind_lock(port)
assert again is not None, "yeniden açılış 'zaten çalışıyor' sanıldı"
again.close()
# öğrenci zili teneffüs bitmeden çalmasın: teneffüs, öğrenci zili süresinden uzun olmalı
from zilli import break_error
two = [["08:30", "09:10"], ["09:12", "09:52"]]  # 2 dk teneffüs
assert break_error(two, 60) == "" and break_error(two, 0) == "" and break_error(two[:1], 180) == ""
assert break_error(two, 180).startswith("2. dersten önceki teneffüs 2 dk; öğrenci zili dersten 3 dk önce")
assert break_error(two, 120) != ""  # eşitse iki zil aynı saniyeye düşer
assert "45 sn" in break_error([["08:30", "09:10"], ["09:10", "09:50"]], 45)
assert break_error(DEFAULT_CONFIG["days"]["haftaici"]["lessons"], 180) == ""  # varsayılan saatler her seçenekle geçerli
# bozuk ayar dosyası silinmez, .bozuk olarak kenara alınır ve varsayılanlarla açılır
import json, zilli
with tempfile.TemporaryDirectory() as d:
    zilli.CONFIG_PATH = path = os.path.join(d, "zilli.json")
    cfg, err = zilli.load_config()  # dosya yok: varsayılanlar, uyarı yok
    assert cfg == DEFAULT_CONFIG and cfg is not DEFAULT_CONFIG and err is None
    for broken in ('{"days": {"haftaici": {"on": true', json.dumps({"days": {"haftaici": {"lessons": [["25:99", "26:00"]]}}})):
        open(path, "w", encoding="utf-8").write(broken)
        cfg, err = zilli.load_config()
        assert err and "zilli.json.bozuk" in err, err
        assert not os.path.exists(path) and open(path + ".bozuk", encoding="utf-8").read() == broken  # içerik korunur
        assert cfg == DEFAULT_CONFIG
        cfg["days"]["haftaici"]["lessons"].clear()  # dönen kopya değiştirilince varsayılanlar bozulmasın
        assert DEFAULT_CONFIG["days"]["haftaici"]["lessons"]
    good = {"bells_on": False, "days": {"pazar": {"on": True, "lessons": [["10:00", "10:40"]]}}}
    open(path, "w", encoding="utf-8").write(json.dumps(good))
    os.remove(path + ".bozuk")
    cfg, err = zilli.load_config()  # sağlam dosya olduğu gibi okunur, kenara alınmaz
    assert err is None and not os.path.exists(path + ".bozuk")
    assert cfg["bells_on"] is False and cfg["days"]["pazar"] == {"on": True, "lessons": [["10:00", "10:40"]]}
    assert cfg["days"]["haftaici"] == DEFAULT_CONFIG["days"]["haftaici"]  # eksik alanlar varsayılandan
# Linux tepsisi: bozuk D-Bus çağrısı hata yanıtı alır, iş parçacığını öldürmez (jeepney yalnız Linux'ta)
try:
    import jeepney
except ImportError:
    jeepney = None
if jeepney:
    from jeepney import DBusAddress, MessageType, new_method_call
    sent = []
    tray = zilli.SniTray(sent.append, os.path.join(zilli.ASSETS, "zilli.png"))
    item = DBusAddress("/StatusNotifierItem", bus_name="org.kde.StatusNotifierItem-1-1")
    props = item.with_interface("org.freedesktop.DBus.Properties")
    sni = item.with_interface("org.kde.StatusNotifierItem")
    bad_get = tray.handle(new_method_call(props, "Get", "s", ("Title",)))  # özellik adı eksik
    assert bad_get.header.message_type == MessageType.error
    bad_menu = tray.handle(new_method_call(sni, "ContextMenu", "i", (5,)))  # y eksik
    assert bad_menu.header.message_type == MessageType.error and sent == []
    title = tray.handle(new_method_call(props, "Get", "ss", ("org.kde.StatusNotifierItem", "Title")))
    assert title.header.message_type == MessageType.method_return and title.body == (("s", "Zilli"),)
    tray.handle(new_method_call(sni, "ContextMenu", "ii", (10, 20)))
    assert sent == [("menu", 10, 20)]
# marş düğmesi yazıları ayarlardan değil sabitten gelir (eski zilli.json'daki "marches" etkilemez)
from zilli import march_label
assert "marches" not in DEFAULT_CONFIG
assert march_label("saygidurusu.mp3") == "Saygı Duruşu + İstiklal Marşı" and march_label("Okul Marşı.mp3") == "Okul Marşı"
assert march_label("istiklalmarsiorkestra.mp3") == "İstiklal Marşı (Enstrümental)"
# düğmeler klasör sırasıyla 2 sütun: enstrümental, İstiklal Marşı'nın hemen yanında
assert sorted(["siren.mp3", "saygidurusu.mp3", "istiklalmarsiorkestra.mp3", "istiklalmarsi.mp3"], key=str.lower)[:2] == \
    ["istiklalmarsi.mp3", "istiklalmarsiorkestra.mp3"]
assert sorted(zilli.BELL_NAMES) == sorted(DEFAULT_CONFIG["bells"])  # check_config her zili BELL_NAMES'ten denetler
# arayüz yardımcıları: panodaki büyük satır, gün çizelgesi aralığı, geri sayım
from zilli import now_text, timeline_span, countdown_text, THEME_COLORS, THEME_EXTRA, THEMES
assert now_text(True, lessons, 31000) == "1. ders, 34 dakika kaldı"   # 08:36:40, ders 09:10'da biter
assert now_text(True, lessons, 33100) == "Teneffüs, 9 dakika kaldı"
assert now_text(True, lessons, 30000) == "Okul başlamadı" and now_text(False, lessons, 31000) == "Bugün zil yok"
assert timeline_span(ev) == (ev[0][0] - 600, ev[-1][0] + 600) and timeline_span([]) is None
assert countdown_text(5) == "0:05" and countdown_text(24 * 60 + 4) == "24:04" and countdown_text(3725) == "1:02:05"
# her temada aynı renk rolleri; eski Bootstrap tema adı Açık'a döner
roles = set(THEME_COLORS["acik"][1])
assert all(set(c) == roles for _, c in THEME_COLORS.values()) and len(roles) == 16
assert set(THEME_EXTRA) == set(THEME_COLORS) == {k for k, _ in THEMES}
assert all(set(x) == set(THEME_EXTRA["acik"]) for x in THEME_EXTRA.values())
assert check_config(merge(copy.deepcopy(DEFAULT_CONFIG), {"theme": "flatly"}))["theme"] == "acik"
assert check_config(merge(copy.deepcopy(DEFAULT_CONFIG), {"theme": "gece"}))["theme"] == "gece"
print("test_zilli OK")

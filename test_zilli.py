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
# eski dosya adları okunur adlara taşınır, ayarlar güncellenir
import copy, os, tempfile
from zilli import migrate_names
with tempfile.TemporaryDirectory() as d:
    for f, data in (("Marşlar/0.mp3", b"a"), ("Marşlar/1.mp3", b"b"), ("Marşlar/saygidurusu.mp3", b"farkli"),
                    ("Melodiler/MEB Öğrenci Zili.mp3", b"m"), ("Melodiler/MEB Çıkış Zili.mp3", b"m"),
                    ("Melodiler/MEB Teneffüs Zili.mp3", b"m")):
        os.makedirs(os.path.join(d, os.path.dirname(f)), exist_ok=True)
        open(os.path.join(d, f), "wb").write(data)
    c = copy.deepcopy(DEFAULT_CONFIG)
    c["anons_on"] = True  # eski sürümden kalan anons ayarları temizlenir
    for k, v in (("ogretmen", "Melodi 5.wav"), ("ogrenci", "Melodi 6.wav"), ("cikis", "Melodi 1.wav")):
        c["bells"][k].update(melody=v, anons="1.mp3")  # eski sürümün varsayılanları
    migrate_names(c, d)
    assert sorted(os.listdir(os.path.join(d, "Marşlar"))) == ["Eski", "istiklalmarsi.mp3", "saygidurusu.mp3"]
    assert os.listdir(os.path.join(d, "Marşlar", "Eski")) == ["1.mp3"]  # yenisi varsa silinmez, kenara alınır
    assert "anons_on" not in c and all("anons" not in b for b in c["bells"].values())
    assert [c["bells"][k]["melody"] for k in ("ogrenci", "ogretmen", "cikis")] == [
        "MEB Öğrenci Zili.mp3", "MEB Çıkış Zili.mp3", "MEB Teneffüs Zili.mp3"]
    c["bells"]["cikis"]["melody"] = "Melodi 3.wav"  # kullanıcı seçimi korunur
    migrate_names(c, d)
    assert c["bells"]["cikis"]["melody"] == "Melodi 3.wav"

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
print("test_zilli OK")

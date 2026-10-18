#!/bin/bash
# Zilli Windows kurulumu: dist/Zilli-Kurulum-<sürüm>.exe
# Linux'ta wine ile derler: resmi 32 bit Python 3.7.9 (3.8+ Windows 7'de KB2533623 olmadan modül yükleyemez:
# "DLL load failed ... The parameter is incorrect"), PyInstaller 5.13.2
# (Windows 7 destekli) ve Inno Setup 6.2.2. Windows'ta derlemek için aynı adımlar wine olmadan da çalışır.
set -euo pipefail
cd "$(dirname "$0")/../.."           # zilli/
SOUNDS=${SOUNDS:-sounds}
export ZILLI_VERSION=$(sed -n 's/^APP, VERSION = "Zilli", "\(.*\)"/\1/p' zilli.py)
export WINEPREFIX="$PWD/build/wine" WINEDEBUG=-all
mkdir -p build/dl build/win dist
# dl <dosya> <adres> <sha256>: indirilen (veya önbellekteki) dosya doğrulanmadan kullanılmaz.
# Python: python.org MD5'iyle karşılaştırıldı; Inno: GitHub özeti; çalışma zamanı: anaconda.org özeti.
dl() {
    [ -f "build/dl/$1" ] || curl -fsSL -o "build/dl/$1" "$2"
    echo "$3  build/dl/$1" | sha256sum -c --quiet
}
dl python-3.7.9.exe https://www.python.org/ftp/python/3.7.9/python-3.7.9.exe \
    769bb7c74ad1df6d7d74071cc16a984ff6182e4016e11b8949b93db487977220
dl innosetup-6.2.2.exe https://github.com/jrsoftware/issrc/releases/download/is-6_2_2/innosetup-6.2.2.exe \
    8117d10d00a2ad33a1390978ea3872861c330e087914410a6377b22c4c5b8563
# Microsoft Universal C Runtime (imzalı, uygulama yanına dağıtılabilir). Windows 7'de KB2999226 yoksa
# python38.dll açılmaz ("api-ms-win-crt-runtime-l1-1-0.dll eksik"); program klasörüne konunca gerek kalmaz.
dl vs2015_runtime-win32.conda https://api.anaconda.org/download/anaconda/vs2015_runtime/14.16.27012/win-32/vs2015_runtime-14.16.27012-hf0eaf9b_3.conda \
    47cef3e07fb63dc6570f29fa9058bfaae858372f5f9b345d9b3fd31db5b1331b
if [ ! -f build/dl/ucrt/ucrtbase.dll ]; then
    rm -rf build/dl/ucrt-x && mkdir -p build/dl/ucrt-x build/dl/ucrt
    python3 -I -c "import sys,zipfile;zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" build/dl/vs2015_runtime-win32.conda build/dl/ucrt-x
    zstd -dq build/dl/ucrt-x/pkg-*.tar.zst -o build/dl/ucrt-x/pkg.tar
    tar xf build/dl/ucrt-x/pkg.tar -C build/dl/ucrt-x
    cp build/dl/ucrt-x/ucrtbase.dll build/dl/ucrt-x/[Aa][Pp][Ii]-[Mm][Ss]-*.dll build/dl/ucrt/
    rm -rf build/dl/ucrt-x
fi

PY='C:\py37\python.exe'
if [ ! -f "$WINEPREFIX/drive_c/py37/python.exe" ]; then
    wineboot -i >/dev/null 2>&1
    wine build/dl/python-3.7.9.exe /quiet InstallAllUsers=0 TargetDir='C:\py37' Include_test=0 Include_doc=0 \
        Include_launcher=0 Include_tcltk=1 PrependPath=0 Shortcuts=0 AssociateFiles=0
fi
wine "$PY" -m pip install -q --disable-pip-version-check --require-hashes --only-binary :all: \
    -r packaging/windows/requirements.lock
[ -f "$WINEPREFIX/drive_c/inno/ISCC.exe" ] || wine build/dl/innosetup-6.2.2.exe /VERYSILENT /SUPPRESSMSGBOXES /DIR='C:\inno' /NOICONS

rm -rf build/win/Zilli build/win/sounds
wine "$PY" -m PyInstaller --noconfirm --clean --log-level WARN --windowed --onedir --name Zilli --hidden-import pystray._win32 \
    --icon "$(winepath -w assets/zilli.ico)" --add-data "$(winepath -w assets);assets" --distpath build/win --workpath build/win/work --specpath build/win zilli.py
cp build/dl/ucrt/*.dll build/win/Zilli/
# güncellemede önceki sürümün program dosyaları yenileriyle karışmasın (ör. python38.dll kalıntısı);
# ayarlar ve ses klasörleri silinmez
{ echo '[InstallDelete]'
  echo 'Type: files; Name: "{app}\*.dll"'
  echo 'Type: files; Name: "{app}\*.pyd"'
  echo 'Type: files; Name: "{app}\base_library.zip"'
  for d in build/win/Zilli/*/; do echo "Type: filesandordirs; Name: \"{app}\\$(basename "$d")\""; done
} > build/win/installdelete.iss
mkdir -p build/win/sounds
for d in Melodiler Marşlar; do [ -d "$SOUNDS/$d" ] && cp -r "$SOUNDS/$d" build/win/sounds/; done
# wine'ın kendi DLL'leri pakete girmiş olmasın: gerçek Windows'ta çalışmazlar
if grep -rl "Wine builtin DLL" build/win/Zilli --include='*.dll' --include='*.pyd'; then
    echo "HATA: pakette wine DLL'i var" >&2; exit 1
fi
(cd packaging/windows && wine 'C:\inno\ISCC.exe' /Q zilli.iss)
ls -la dist/

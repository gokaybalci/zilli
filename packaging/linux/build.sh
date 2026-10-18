#!/bin/bash
# Zilli Linux paketleri: dist/Zilli-x86_64.AppImage ve dist/zilli_<sürüm>_amd64.deb
# Python 3.8 Ubuntu 18.04 kapsayıcısında kaynaktan derlenir (glibc 2.27: 2018 sonrası tüm dağıtımlar)
# ve Tk 8.6 (Xft, düzgün yazı tipleri) ile birlikte paketlenir. Gerekenler: docker, curl.
set -euo pipefail
cd "$(dirname "$0")/../.."           # zilli/
SOUNDS=${SOUNDS:-sounds}             # Melodiler/Marşlar klasörlerinin olduğu yer
VERSION=$(sed -n 's/^APP, VERSION = "Zilli", "\(.*\)"/\1/p' zilli.py)
PYVER=3.8.20
mkdir -p dist build

docker run --rm -v "$PWD:/src" -v "$(realpath "$SOUNDS"):/sounds:ro" -e VERSION="$VERSION" -e PYVER=$PYVER \
    -e HOST_UID="$(id -u):$(id -g)" ubuntu:18.04 bash -euo pipefail -c '
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq build-essential curl ca-certificates tk-dev libssl-dev zlib1g-dev libffi-dev \
    libbz2-dev liblzma-dev patchelf >/dev/null

B=/build/opt/zilli
P=$B/python
cd /tmp && curl -sSL https://www.python.org/ftp/python/$PYVER/Python-$PYVER.tgz | tar xz && cd Python-$PYVER
./configure -q --prefix=$P --enable-shared --without-ensurepip >/dev/null
make -j"$(nproc)" >/dev/null 2>&1 && make install >/dev/null 2>&1
export LD_LIBRARY_PATH=$P/lib
$P/bin/python3 -c "import tkinter, ssl, lzma, bz2, zlib, ctypes"   # gerekli modüller derlendi mi
curl -sSL https://bootstrap.pypa.io/pip/3.8/get-pip.py | $P/bin/python3 - -q --no-warn-script-location
$P/bin/python3 -m pip install -q --no-warn-script-location -r /src/requirements.txt

# Tcl/Tk ve Xft paketin içine: hedef sistemde tk kurulu olmasa da çalışsın
L=/usr/lib/x86_64-linux-gnu
cp -L $L/libtcl8.6.so $L/libtk8.6.so $L/libXft.so.2 $L/libXss.so.1 $P/lib/
cp -r /usr/share/tcltk/tcl8.6 /usr/share/tcltk/tk8.6 $P/lib/
# kitaplıklar birbirini kendi klasörlerinde bulsun (LD_LIBRARY_PATH alt süreçlere sızmasın diye kullanılmaz)
patchelf --set-rpath "\$ORIGIN/../lib" $P/bin/python3.8
for f in $P/lib/*.so*; do patchelf --set-rpath "\$ORIGIN" "$f"; done
for f in $P/lib/python3.8/lib-dynload/*.so; do patchelf --set-rpath "\$ORIGIN/../.." "$f"; done

# gereksizleri at, .pyc önceden derle (/opt salt okunur; yoksa her açılış yavaşlar)
cd $P/lib/python3.8
rm -rf test idlelib turtledemo lib2to3 tkinter/test unittest/test ctypes/test distutils/tests config-3.8-*
rm -rf site-packages/pip* site-packages/setuptools* site-packages/wheel* site-packages/pygame/{examples,docs,tests}
rm -rf $P/include $P/share $P/lib/pkgconfig $P/lib/libpython3.8.a
find $P -name "*.so*" -exec strip --strip-unneeded {} + 2>/dev/null || true
$P/bin/python3 -m compileall -q -j0 $P/lib/python3.8 >/dev/null || true

mkdir -p $B/app
cp -r /src/zilli.py /src/assets $B/app/
mkdir -p $B/app/sounds   # Müzik pakete konmaz (telifli şarkılar)
for d in Melodiler Marşlar; do [ -d "/sounds/$d" ] && cp -r "/sounds/$d" $B/app/sounds/; done
$P/bin/python3 -m compileall -q $B/app
cat > $B/zilli <<"EOF"
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export TCL_LIBRARY="$HERE/python/lib/tcl8.6" TK_LIBRARY="$HERE/python/lib/tk8.6"
# Ubuntu Tcl modül yolu /usr/share altına sabit; paketteki msgcat vb. için
export TCL8_6_TM_PATH="$HERE/python/lib/tcl8.6/tcl8"
exec "$HERE/python/bin/python3.8" -s -E "$HERE/app/zilli.py" "$@"
EOF
chmod 755 $B/zilli
(cd /build/opt/zilli/app && LD_LIBRARY_PATH= ../python/bin/python3.8 -E /src/test_zilli.py)

# .deb
D=/build
mkdir -p $D/DEBIAN $D/usr/bin $D/usr/share/applications $D/usr/share/icons/hicolor/256x256/apps \
    $D/usr/share/icons/hicolor/scalable/apps $D/etc/xdg/autostart
ln -sf /opt/zilli/zilli $D/usr/bin/zilli
cp /src/assets/zilli.png $D/usr/share/icons/hicolor/256x256/apps/
cp /src/assets/zilli.svg $D/usr/share/icons/hicolor/scalable/apps/
DESK="[Desktop Entry]\nType=Application\nName=Zilli\nComment=Okul zil programı\nIcon=zilli\nTerminal=false\nCategories=Education;\n"
printf "${DESK}Exec=zilli\n" > $D/usr/share/applications/zilli.desktop
printf "${DESK}Exec=zilli --min\n" > $D/etc/xdg/autostart/zilli.desktop
echo /etc/xdg/autostart/zilli.desktop > $D/DEBIAN/conffiles
cat > $D/DEBIAN/control <<EOF
Package: zilli
Version: $VERSION
Section: education
Priority: optional
Architecture: amd64
Depends: libc6 (>= 2.27), libx11-6, libxext6, libxrender1, libfontconfig1, libfreetype6
Installed-Size: $(du -sk $D/opt | cut -f1)
Maintainer: Gökay
Description: Okul zil programı
 Ders saatlerine göre öğrenci, öğretmen ve teneffüs zillerini çalar;
 teneffüs müziği ve İstiklal Marşı desteği vardır.
EOF
dpkg-deb --root-owner-group -Zxz --build $D /src/dist/zilli_${VERSION}_amd64.deb >/dev/null

rm -rf /src/build/AppDir && mkdir -p /src/build/AppDir
cp -a $B/. /src/build/AppDir/
chown -R $HOST_UID /src/dist /src/build
'

# AppImage
A=build/AppDir
mv $A/zilli $A/AppRun
cp assets/zilli.png $A/zilli.png
printf '[Desktop Entry]\nType=Application\nName=Zilli\nComment=Okul zil programı\nIcon=zilli\nExec=zilli\nTerminal=false\nCategories=Education;\n' > $A/zilli.desktop
TOOL=build/appimagetool-x86_64.AppImage
[ -x $TOOL ] || { curl -sSL -o $TOOL https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage; chmod +x $TOOL; }
APPIMAGE_EXTRACT_AND_RUN=1 ARCH=x86_64 $TOOL -n "$PWD/$A" "$PWD/dist/Zilli-x86_64.AppImage" >/dev/null
ls -la dist/

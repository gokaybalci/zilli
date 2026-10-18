#!/bin/bash
# requirements.txt değişince çalıştırın: paketlerin kuracağı tekerlekleri (wheel) indirip sha256 ile kilitler.
# Derlemeler "pip install --require-hashes" ile yalnız bu dosyalardaki tekerlekleri kabul eder.
set -euo pipefail
cd "$(dirname "$0")"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

lock() {  # lock <çıktı> <pip download seçenekleri...> -- <gereksinimler...>
    local out=$1; shift
    local opts=() reqs=()
    while [ "$1" != "--" ]; do opts+=("$1"); shift; done; shift
    reqs=("$@")
    rm -rf "$T/w" && mkdir -p "$T/w"
    python3 -m pip download -q --disable-pip-version-check --only-binary=:all: --implementation cp \
        "${opts[@]}" -d "$T/w" "${reqs[@]}"
    python3 -I - "$T/w" > "$out" <<'EOF'
import hashlib, os, re, sys
print("# packaging/lock.sh üretti, elle düzenlemeyin")
for f in sorted(os.listdir(sys.argv[1]), key=str.lower):
    name, ver = f.split("-")[:2]
    h = hashlib.sha256(open(os.path.join(sys.argv[1], f), "rb").read()).hexdigest()
    print("%s==%s --hash=sha256:%s" % (re.sub(r"[-_.]+", "-", name).lower(), ver, h))
EOF
    echo "$out: $(grep -c == "$out") paket"
}

REQS=$(grep -v '^#' ../requirements.txt | sed 's/;.*//' | grep -v '^jeepney')
# Linux: Ubuntu 18.04'te derlenen CPython 3.8, manylinux2014 (glibc 2.17) tekerlekleri
lock linux/requirements.lock --python-version 3.8 --abi cp38 \
    --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 -- $REQS jeepney==0.8.0
# Windows: 32 bit CPython 3.7. pip ortam koşullarını ("sys_platform", "python_version") bu makineye göre
# değerlendirdiği için PyInstaller'ın Windows'a ve 3.7'ye özel bağımlılıkları elle eklenir (3.7'yi destekleyen
# son sürümler), Linux'a özel python-xlib çıkarılır.
lock windows/requirements.lock --python-version 3.7 --abi cp37m --platform win32 -- \
    $REQS pyinstaller==5.13.2 pefile==2023.2.7 pywin32-ctypes==0.2.3 \
    importlib-metadata==6.7.0 zipp==3.15.0 typing-extensions==4.7.1
sed -i '/^python-xlib==/d' windows/requirements.lock

#!/bin/sh
# Build the .deb and .rpm into dist/ from the wheel already in dist/ (run `python -m build` first). Needs nfpm.
set -eu
cd "$(dirname "$0")/.."

VERSION=$(python3 -c "import re,pathlib; print(re.search(r'__version__ = \"(.+?)\"', pathlib.Path('obelisk/__init__.py').read_text()).group(1))")
export VERSION

stage=build/pkgroot
rm -rf "$stage"
mkdir -p "$stage/usr/share/obelisk"
python3 -m zipfile -e "dist/obelisk_ffb-$VERSION-py3-none-any.whl" "$stage/usr/share/obelisk"
rm -rf "$stage"/usr/share/obelisk/obelisk_ffb-*.dist-info

# The packaged launcher is on PATH, so the menu entry needs no absolute path.
sed 's|^Exec=.*|Exec=obelisk|' obelisk/data/io.github.vsimcraft.obelisk.desktop > "$stage/io.github.vsimcraft.obelisk.desktop"

for format in deb rpm; do
    nfpm package --config packaging/nfpm.yaml --packager "$format" --target dist/
done

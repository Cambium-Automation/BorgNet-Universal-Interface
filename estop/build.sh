#!/bin/bash
set -euo pipefail

OUTPUT="${1:?Pass a build output directory}"
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$OUTPUT"
BUILD="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/borgnet-estop.XXXXXX")"
trap '/bin/rm -rf "$BUILD"' EXIT
APP="$BUILD/BorgNet E-Stop.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$SOURCE/stop.py" "$APP/Contents/Resources/stop.py"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>BorgNetEStop</string>
<key>CFBundleIdentifier</key><string>org.borgnet.estop</string>
<key>CFBundleName</key><string>BorgNet E-Stop</string>
<key>CFBundleIconFile</key><string>EStop.icns</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
ICONSET="$BUILD/EStop.iconset"
mkdir -p "$ICONSET"
xcrun swift "$SOURCE/icon.swift" "$BUILD/icon-1024.png"
for POINTS in 16 32 128 256 512; do
  PIXELS="$POINTS"
  /usr/bin/sips -s format png -z "$PIXELS" "$PIXELS" "$BUILD/icon-1024.png" \
    --out "$ICONSET/icon_${POINTS}x${POINTS}.png" >/dev/null
  DOUBLE=$((POINTS * 2))
  /usr/bin/sips -s format png -z "$DOUBLE" "$DOUBLE" "$BUILD/icon-1024.png" \
    --out "$ICONSET/icon_${POINTS}x${POINTS}@2x.png" >/dev/null
done
xcrun iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/EStop.icns"
HASH="$(/usr/bin/shasum -a 256 "$APP/Contents/Resources/stop.py" | /usr/bin/awk '{print $1}')"
/usr/bin/sed "s/__HELPER_SHA256__/$HASH/g" "$SOURCE/main.swift" > "$BUILD/estop-compiled.swift"
SDK="$(xcrun --sdk macosx --show-sdk-path)"
xcrun swiftc -sdk "$SDK" -target "$(uname -m)-apple-macosx13.0" -O \
  -framework Cocoa -framework CryptoKit "$BUILD/estop-compiled.swift" \
  -o "$APP/Contents/MacOS/BorgNetEStop"
xattr -cr "$APP"
codesign --force --sign - --timestamp=none "$APP"
codesign --verify --deep --strict "$APP"
/usr/bin/python3 - "$BUILD" <<'PY'
import hashlib,pathlib,sys
root=pathlib.Path(sys.argv[1]); app=root/'BorgNet E-Stop.app'
files=sorted(p for p in app.rglob('*') if p.is_file())
manifest=root/'BorgNet-E-Stop.sha256'
manifest.write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}\n' for p in files))
print(f'Built {app}')
print(f'Manifest has {len(files)} files')
print(f'Manifest SHA-256 {hashlib.sha256(manifest.read_bytes()).hexdigest()}')
PY
(
  cd "$BUILD"
  /usr/bin/shasum -a 256 -c BorgNet-E-Stop.sha256 >/dev/null
  /usr/bin/ditto -c -k --keepParent 'BorgNet E-Stop.app' "$OUTPUT/BorgNet-E-Stop.zip"
)
/bin/cp "$BUILD/BorgNet-E-Stop.sha256" "$OUTPUT/BorgNet-E-Stop.sha256"
MANIFEST_HASH="$(/usr/bin/shasum -a 256 "$OUTPUT/BorgNet-E-Stop.sha256" | /usr/bin/awk '{print $1}')"
ARCHIVE_HASH="$(/usr/bin/shasum -a 256 "$OUTPUT/BorgNet-E-Stop.zip" | /usr/bin/awk '{print $1}')"
/usr/bin/sed -e "s/__MANIFEST_SHA256__/$MANIFEST_HASH/g" \
  -e "s/__ARCHIVE_SHA256__/$ARCHIVE_HASH/g" \
  "$SOURCE/install-protected.sh.in" > "$OUTPUT/Install BorgNet E-Stop.sh"
/bin/chmod 755 "$OUTPUT/Install BorgNet E-Stop.sh"
echo "Archive SHA-256 $ARCHIVE_HASH"
echo "Installer SHA-256 $(/usr/bin/shasum -a 256 "$OUTPUT/Install BorgNet E-Stop.sh" | /usr/bin/awk '{print $1}')"

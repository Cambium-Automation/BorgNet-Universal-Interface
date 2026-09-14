#!/bin/bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${1:-$SOURCE_DIR/../dist}"
mkdir -p "$BUILD_DIR"
APP="$BUILD_DIR/BorgNet Universal Interface.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>BorgNet</string>
<key>CFBundleIdentifier</key><string>org.borgnet.universalinterface</string>
<key>CFBundleName</key><string>BorgNet Universal Interface</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.1.0</string>
<key>CFBundleVersion</key><string>2</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PLIST
cp "$SOURCE_DIR/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
SDK="$(xcrun --sdk macosx --show-sdk-path)"
xcrun swiftc -sdk "$SDK" -target "$(uname -m)-apple-macosx13.0" -O \
  -framework Cocoa -framework WebKit "$SOURCE_DIR/main.swift" -o "$APP/Contents/MacOS/BorgNet"
# Finder metadata on freshly built bundles can invalidate signing in synced folders.
xattr -cr "$APP"
codesign --force --sign - --timestamp=none "$APP"
codesign --verify --deep --strict "$APP"
printf 'Built: %s\nStart borgnet serve before opening this app.\n' "$APP"

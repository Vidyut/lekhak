#!/usr/bin/env bash
# Builds a minimal Lekhak.app into ~/Applications (no sudo, no codesigning).
#
#   bash scripts/install_macos.sh          # build + install
#   bash scripts/install_macos.sh --remove # delete the app
#
# The bundle's launcher resolves, in order: this checkout's .venv, a
# `lekhak` command on PATH, then python3 with the checkout on PYTHONPATH.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
app="$HOME/Applications/Lekhak.app"

if [[ "${1:-}" == "--remove" ]]; then
  rm -rf "$app"
  echo "removed $app"
  exit 0
fi

mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"

cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>            <string>Lekhak</string>
  <key>CFBundleDisplayName</key>     <string>Lekhak</string>
  <key>CFBundleIdentifier</key>      <string>net.vidyut.lekhak</string>
  <key>CFBundleVersion</key>         <string>0.1.0</string>
  <key>CFBundleShortVersionString</key> <string>0.1.0</string>
  <key>CFBundleExecutable</key>      <string>Lekhak</string>
  <key>CFBundlePackageType</key>     <string>APPL</string>
  <key>LSMinimumSystemVersion</key>  <string>12.0</string>
  <key>NSHighResolutionCapable</key> <true/>
</dict>
</plist>
PLIST

cat > "$app/Contents/MacOS/Lekhak" <<LAUNCHER
#!/bin/bash
repo="$repo"
if [[ -x "\$repo/.venv/bin/python" ]]; then
  exec "\$repo/.venv/bin/python" -m lekhak
elif command -v lekhak >/dev/null 2>&1; then
  exec "\$(command -v lekhak)"
else
  PYTHONPATH="\$repo/src\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m lekhak
fi
LAUNCHER
chmod +x "$app/Contents/MacOS/Lekhak"

# Icon: render the SVG via this checkout's PySide6 and assemble an .icns.
if command -v iconutil >/dev/null 2>&1 && [[ -x "$repo/.venv/bin/python" ]]; then
  if "$repo/.venv/bin/python" "$repo/scripts/render_icons.py" \
       --icns "$app/Contents/Resources/lekhak.icns" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c \
      "Add :CFBundleIconFile string lekhak" "$app/Contents/Info.plist" 2>/dev/null \
      || true
    echo "icon installed"
  else
    echo "note: icon render failed; app keeps the generic icon"
  fi
else
  echo "note: iconutil or .venv missing; app keeps the generic icon"
fi

echo "installed $app"
echo "open '$app'   # or find Lekhak in Launchpad / Spotlight"

#!/bin/zsh
# SPDX-License-Identifier: MIT
set -eu
cd -- "${0:A:h}"
WIZARD_ROOT="$PWD"
export PATH="/Library/Frameworks/Python.framework/Versions/Current/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
WIZARD_PYTHON="$(command -v python3 || true)"
if [[ -z "$WIZARD_PYTHON" ]]; then
  print '找不到 Python 3，請先安裝 Python 3。'; read '?按 Return 關閉。'; exit 1
fi
WIZARD_CACHE="$WIZARD_ROOT/03-精靈快取"
WIZARD_APP="$WIZARD_CACHE/APK分身精靈.app"
WIZARD_SOURCE="$WIZARD_ROOT/CloneWizard.swift"
mkdir -p "$WIZARD_APP/Contents/MacOS"
WIZARD_HASH="$(/usr/bin/shasum -a 256 "$WIZARD_SOURCE" | /usr/bin/cut -d ' ' -f 1)"
if [[ ! -x "$WIZARD_APP/Contents/MacOS/CloneWizard" || ! -f "$WIZARD_CACHE/source.sha256" || "$(< "$WIZARD_CACHE/source.sha256")" != "$WIZARD_HASH" ]]; then
  print '首次啟動正在編譯 macOS 視窗，之後會直接開啟。'
  (
  WIZARD_BUILD_TEMP="$WIZARD_CACHE/編譯暫存"
  if ! mkdir "$WIZARD_BUILD_TEMP"; then print '另一個視窗編譯正在執行，請等它完成。'; exit 1; fi
  trap 'rm -rf -- "$WIZARD_BUILD_TEMP"' EXIT
  mkdir -p "$WIZARD_BUILD_TEMP/modules" "$WIZARD_BUILD_TEMP/tmp"
  export TMPDIR="$WIZARD_BUILD_TEMP/tmp/"
  export CLANG_MODULE_CACHE_PATH="$WIZARD_BUILD_TEMP/modules"
  export SWIFT_MODULE_CACHE_PATH="$WIZARD_BUILD_TEMP/modules"
  WIZARD_SWIFT="$(/usr/bin/xcrun --find swiftc)"
  WIZARD_COMPILER_DIR="${WIZARD_SWIFT:h}"
  WIZARD_SDK="$(/usr/bin/xcrun --show-sdk-path)"
  WIZARD_ARCH="$(/usr/bin/uname -m)"
  # Use the frontend directly for compatibility with Unicode TMPDIR. The frontend
  # and linker accept it; their object and module cache stay in this folder.
  "$WIZARD_COMPILER_DIR/swift-frontend" -frontend -c "$WIZARD_SOURCE" -target "$WIZARD_ARCH-apple-macosx14.0" -enable-objc-interop -sdk "$WIZARD_SDK" -swift-version 5 -module-name CloneWizard -module-cache-path "$WIZARD_BUILD_TEMP/modules" -o "$WIZARD_BUILD_TEMP/CloneWizard.o"
  "$WIZARD_COMPILER_DIR/clang" "$WIZARD_BUILD_TEMP/CloneWizard.o" --sysroot "$WIZARD_SDK" --target="$WIZARD_ARCH-apple-macosx14.0" -L "$WIZARD_COMPILER_DIR/../lib/swift/macosx" -L "$WIZARD_SDK/usr/lib/swift" -rpath /usr/lib/swift -framework AppKit -o "$WIZARD_APP/Contents/MacOS/CloneWizard"
  cat > "$WIZARD_APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>CFBundleExecutable</key><string>CloneWizard</string><key>CFBundleIdentifier</key><string>local.apkclonewizard</string><key>CFBundleName</key><string>APK分身精靈</string><key>CFBundlePackageType</key><string>APPL</string><key>NSHighResolutionCapable</key><true/></dict></plist>
PLIST
  /usr/bin/codesign --force --sign - "$WIZARD_APP"
  print -r -- "$WIZARD_HASH" > "$WIZARD_CACHE/source.sha256"
  rm -rf -- "$WIZARD_BUILD_TEMP"
  trap - EXIT
  )
fi
if [[ "${1:-}" == '--compile-only' ]]; then exit 0; fi
if [[ "${1:-}" == '--self-test' ]]; then
  (
    trap 'rm -f -- "$WIZARD_ROOT/拖入 中文 空格.apk"' EXIT
    "$WIZARD_APP/Contents/MacOS/CloneWizard" "$WIZARD_ROOT" "$WIZARD_PYTHON" --self-test
  )
  exit 0
fi
/usr/bin/open "$WIZARD_APP" --args "$WIZARD_ROOT" "$WIZARD_PYTHON"

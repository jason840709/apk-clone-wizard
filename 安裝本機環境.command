#!/bin/zsh
# SPDX-License-Identifier: MIT
set -eu
setopt pipefail
cd -- "${0:A:h}"
WIZARD_ROOT="$PWD"
WIZARD_ENV="$WIZARD_ROOT/.local-env"
WIZARD_RUNTIME="$WIZARD_ENV/runtime"
WIZARD_LOCK="$WIZARD_ROOT/environment.lock.json"
WIZARD_ARCH="$(/usr/bin/uname -m)"
WIZARD_MODE="${1:-install}"
case "$WIZARD_MODE" in install|--check|--download-only) ;; *) print -u2 '用法：安裝本機環境.command [--check|--download-only]'; exit 2;; esac
[[ "$(/usr/bin/uname -s)" == Darwin ]] || { print -u2 '此安裝入口只支援 macOS。'; exit 1; }
case "$WIZARD_ARCH" in arm64|x86_64) ;; *) print -u2 '不支援這個 CPU 架構。'; exit 1;; esac
lock_value() { /usr/bin/plutil -extract "$1" raw -o - "$WIZARD_LOCK"; }
WIZARD_SDK_VERSION="$(lock_value android_build_tools_version)"
WIZARD_LICENSE_HASH="$(lock_value android.license_sha256)"
WIZARD_LICENSE="$WIZARD_ROOT/tool-licenses/android-sdk-license.txt"
WIZARD_ACTUAL_LICENSE="$(/usr/bin/shasum -a 256 "$WIZARD_LICENSE")"
[[ "${WIZARD_ACTUAL_LICENSE%% *}" == "$WIZARD_LICENSE_HASH" ]] || { print -u2 'SDK 授權文件校驗失敗，請重新下載專案。'; exit 1; }

check_runtime() {
  [[ -f "$WIZARD_RUNTIME/installed.lock.json" && -f "$WIZARD_RUNTIME/platform.txt" ]] || return 1
  /usr/bin/cmp -s "$WIZARD_LOCK" "$WIZARD_RUNTIME/installed.lock.json" || return 1
  [[ "$(< "$WIZARD_RUNTIME/platform.txt")" == "$WIZARD_ARCH" ]] || return 1
  [[ -x "$WIZARD_RUNTIME/python/bin/python3" && -x "$WIZARD_RUNTIME/jdk/Contents/Home/bin/java" && -x "$WIZARD_RUNTIME/jdk/Contents/Home/bin/keytool" ]] || return 1
  local bt="$WIZARD_RUNTIME/android-sdk/build-tools/$WIZARD_SDK_VERSION"
  [[ -x "$bt/aapt2" && -x "$bt/zipalign" && -f "$bt/lib/apksigner.jar" && -f "$bt/NOTICE.txt" ]] || return 1
  [[ -f "$WIZARD_RUNTIME/sdk-accepted.sha256" && "$(< "$WIZARD_RUNTIME/sdk-accepted.sha256")" == "$WIZARD_LICENSE_HASH" ]] || return 1
  local actual="$(/usr/bin/shasum -a 256 "$WIZARD_RUNTIME/apktool.jar")"
  [[ "${actual%% *}" == "$(lock_value apktool.sha256)" ]] || return 1
  "$WIZARD_RUNTIME/python/bin/python3" -c 'import sys; assert sys.version_info >= (3,10)' || return 1
  "$WIZARD_RUNTIME/jdk/Contents/Home/bin/java" -version || return 1
}
if [[ "$WIZARD_MODE" == --check ]]; then
  if check_runtime; then print '本機環境檢查通過。'; exit 0; fi
  print -u2 '本機環境尚未安裝、版本不同或不完整，請雙擊「安裝本機環境.command」。'; exit 1
fi
if [[ "$WIZARD_MODE" == install ]] && check_runtime; then
  print '資料夾內的環境已安裝並通過檢查；不需重複下載。'; exit 0
fi
print 'APK 分身精靈：資料夾內環境安裝'
print 'Python、Eclipse Temurin JDK、Apktool、Android Build Tools 的著作權與授權屬各自原作者及權利人，不是本專案作者的著作。'
print '來源及授權見 THIRD_PARTY_NOTICES.md；套件附帶的 LICENSE／NOTICE 會保留。'
print "下載與安裝位置：$WIZARD_ENV"
print '不使用 sudo、Homebrew 或系統安裝程式，不修改 shell 設定檔及系統 PATH。'
if [[ "$WIZARD_MODE" == install ]]; then
  print '安裝 Android SDK Build Tools 前，請閱讀 Google 的 SDK 授權條款：'
  print 'https://developer.android.com/studio/terms'
  if [[ -t 0 ]]; then /usr/bin/less "$WIZARD_LICENSE"; else /bin/cat "$WIZARD_LICENSE"; fi
  read -r "WIZARD_CONSENT?若同意上述 SDK 條款並開始安裝，請輸入「我同意」；其他輸入取消：" || WIZARD_CONSENT=''
  if [[ "$WIZARD_CONSENT" != '我同意' ]]; then print '尚未同意 SDK 條款，已取消，沒有安裝環境。'; exit 1; fi
fi
/bin/mkdir -p "$WIZARD_ENV/downloads"
if ! /bin/mkdir "$WIZARD_ENV/install.lock"; then print -u2 '另一個安裝正在執行。若先前被強制中止，確認沒有安裝程序後再刪除 .local-env/install.lock。'; exit 1; fi
WIZARD_STAGE=''
WIZARD_OLD=''
cleanup() {
  local result=$?
  [[ -z "$WIZARD_STAGE" ]] || /bin/rm -rf -- "$WIZARD_STAGE"
  if [[ -n "$WIZARD_OLD" && -d "$WIZARD_OLD" && ! -d "$WIZARD_RUNTIME" ]]; then /bin/mv "$WIZARD_OLD" "$WIZARD_RUNTIME"; fi
  /bin/rmdir "$WIZARD_ENV/install.lock" 2>/dev/null || true
  return "$result"
}
trap cleanup EXIT
trap 'exit 130' INT TERM
fetch() {
  local key="$1" filename="$2"
  local url="$(lock_value "$key.url")" expected="$(lock_value "$key.sha256")"
  local target="$WIZARD_ENV/downloads/$filename"
  case "$url" in https://github.com/astral-sh/python-build-standalone/releases/download/*|https://github.com/adoptium/temurin21-binaries/releases/download/*|https://github.com/iBotPeaches/Apktool/releases/download/*|https://dl.google.com/android/repository/*) ;; *) print -u2 '下載網址不是支援的官方 HTTPS 發行來源。'; exit 1;; esac
  local actual=''
  if [[ -f "$target" ]]; then actual="$(/usr/bin/shasum -a 256 "$target")"; fi
  if [[ "${actual%% *}" != "$expected" ]]; then
    print "正在下載 $filename…"
    /usr/bin/curl --fail --location --proto '=https' --proto-redir '=https' --retry 3 --connect-timeout 30 --max-time 1800 --output "$target.part" "$url"
    actual="$(/usr/bin/shasum -a 256 "$target.part")"
    [[ "${actual%% *}" == "$expected" ]] || { /bin/rm -f "$target.part"; print -u2 "$filename SHA-256 不符，停止安裝。"; exit 1; }
    /bin/mv "$target.part" "$target"
  fi
  print "$filename SHA-256 校驗通過。"
}
fetch "architectures.$WIZARD_ARCH.python" "python-$WIZARD_ARCH.tar.gz"
fetch "architectures.$WIZARD_ARCH.jdk" "jdk-$WIZARD_ARCH.tar.gz"
fetch apktool apktool.jar
fetch android android-build-tools.zip
if [[ "$WIZARD_MODE" == --download-only ]]; then print '下載與校驗完成；未解壓安裝、未接受 SDK 條款。'; exit 0; fi
WIZARD_STAGE="$(/usr/bin/mktemp -d "$WIZARD_ENV/stage.XXXXXX")"
/bin/mkdir -p "$WIZARD_STAGE/jdk-extract" "$WIZARD_STAGE/android-extract" "$WIZARD_STAGE/android-sdk/build-tools"
/usr/bin/tar -xzf "$WIZARD_ENV/downloads/python-$WIZARD_ARCH.tar.gz" -C "$WIZARD_STAGE"
/usr/bin/tar -xzf "$WIZARD_ENV/downloads/jdk-$WIZARD_ARCH.tar.gz" -C "$WIZARD_STAGE/jdk-extract"
WIZARD_JDKS=("$WIZARD_STAGE"/jdk-extract/*(N/))
[[ ${#WIZARD_JDKS} == 1 && -d "$WIZARD_JDKS[1]/Contents/Home" ]] || { print -u2 'JDK 套件結構不符。'; exit 1; }
/bin/mv "$WIZARD_JDKS[1]" "$WIZARD_STAGE/jdk"
/usr/bin/unzip -q "$WIZARD_ENV/downloads/android-build-tools.zip" -d "$WIZARD_STAGE/android-extract"
[[ -d "$WIZARD_STAGE/android-extract/android-16" ]] || { print -u2 'Android 套件結構不符。'; exit 1; }
/bin/mv "$WIZARD_STAGE/android-extract/android-16" "$WIZARD_STAGE/android-sdk/build-tools/$WIZARD_SDK_VERSION"
/bin/cp "$WIZARD_ENV/downloads/apktool.jar" "$WIZARD_STAGE/apktool.jar"
/bin/cp -R "$WIZARD_ROOT/tool-licenses" "$WIZARD_STAGE/licenses"
/bin/cp "$WIZARD_LOCK" "$WIZARD_STAGE/installed.lock.json"
print -r -- "$WIZARD_ARCH" > "$WIZARD_STAGE/platform.txt"
print -r -- "$WIZARD_LICENSE_HASH" > "$WIZARD_STAGE/sdk-accepted.sha256"
/bin/rmdir "$WIZARD_STAGE/jdk-extract" "$WIZARD_STAGE/android-extract"
"$WIZARD_STAGE/python/bin/python3" -c 'import ssl,sys; assert sys.version_info >= (3,10)'
"$WIZARD_STAGE/jdk/Contents/Home/bin/java" -version
"$WIZARD_STAGE/jdk/Contents/Home/bin/java" -jar "$WIZARD_STAGE/apktool.jar" --version
[[ -x "$WIZARD_STAGE/android-sdk/build-tools/$WIZARD_SDK_VERSION/aapt2" && -x "$WIZARD_STAGE/android-sdk/build-tools/$WIZARD_SDK_VERSION/zipalign" ]] || exit 1
if [[ -d "$WIZARD_RUNTIME" ]]; then WIZARD_OLD="$WIZARD_ENV/previous-runtime"; [[ ! -e "$WIZARD_OLD" ]] || { print -u2 '存在先前環境備份，請先檢查 .local-env/previous-runtime。'; exit 1; }; /bin/mv "$WIZARD_RUNTIME" "$WIZARD_OLD"; fi
/bin/mv "$WIZARD_STAGE" "$WIZARD_RUNTIME"
WIZARD_STAGE=''
[[ -z "$WIZARD_OLD" ]] || /bin/rm -rf -- "$WIZARD_OLD"
WIZARD_OLD=''
print '安裝完成。雙擊「啟動APK分身精靈.command」即可使用本機環境。'
if ! /usr/bin/xcode-select -p >/dev/null 2>&1; then
  print '未偵測到 Apple Command Line Tools，原生視窗暫時無法編譯。Apple 工具無法由本腳本在專案內安裝。'
  print '你仍可雙擊「啟動終端分身精靈.command」，使用已安裝的本機 Python 與 Android 工具。'
fi
if [[ -t 0 ]]; then read -r '?按 Return 關閉。'; fi

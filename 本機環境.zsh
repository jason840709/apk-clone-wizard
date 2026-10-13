# SPDX-License-Identifier: MIT
# Source this file only from a launcher; no system or shell profile changes.
WIZARD_ENV="$WIZARD_ROOT/.local-env/runtime"
if [[ -f "$WIZARD_ENV/platform.txt" && "$(< "$WIZARD_ENV/platform.txt")" != "$(/usr/bin/uname -m)" ]]; then
  print -u2 '這份本機環境是另一種 CPU 架構，請重新執行「安裝本機環境.command」。'
  return 1
fi
if [[ -x "$WIZARD_ENV/python/bin/python3" ]]; then
  export PATH="$WIZARD_ENV/python/bin:$PATH"
fi
if [[ -x "$WIZARD_ENV/jdk/Contents/Home/bin/java" ]]; then
  export JAVA_HOME="$WIZARD_ENV/jdk/Contents/Home"
  export PATH="$JAVA_HOME/bin:$PATH"
fi
if [[ -d "$WIZARD_ENV/android-sdk" ]]; then export ANDROID_SDK_ROOT="$WIZARD_ENV/android-sdk"; fi
if [[ -f "$WIZARD_ENV/apktool.jar" ]]; then export APKTOOL_PATH="$WIZARD_ENV/apktool.jar"; fi
# Keep Apktool's reusable framework cache under this project.
export APKTOOL_FRAMEWORK_DIR="$WIZARD_ROOT/.local-env/apktool-framework"

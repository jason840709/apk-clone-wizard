#!/bin/zsh
# SPDX-License-Identifier: MIT
set -eu
cd -- "${0:A:h}"
WIZARD_ROOT="$PWD"
source "$WIZARD_ROOT/本機環境.zsh"
WIZARD_PYTHON="$(command -v python3 || true)"
if [[ -z "$WIZARD_PYTHON" ]] || ! "$WIZARD_PYTHON" -c 'import sys; assert sys.version_info >= (3,10)' >/dev/null 2>&1; then
  print '請先雙擊「安裝本機環境.command」。'; exit 1
fi
"$WIZARD_PYTHON" "$WIZARD_ROOT/分身精靈 [終端機運行].py"

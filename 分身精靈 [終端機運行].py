#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Terminal entry uses the same saved identity and validation as the native UI."""
from pathlib import Path
from clone_bridge import build

def main():
    try:
        raw=input("把原始 APK 拖進來，再按 Return： ").strip()
        if len(raw)>1 and raw[0]==raw[-1] and raw[0] in (chr(39),chr(34)):raw=raw[1:-1]
        # Terminal drag escaping is data; never invoke a shell to expand it.
        raw=raw.replace(chr(92)+" "," ")
        count=int(input("分身數量 [5]： ").strip() or "5")
        start=int(input("起始編號 [1]： ").strip() or "1")
        custom=input("要逐個自訂名稱嗎？[y/N]： ").strip().lower()=="y"
        names=[input("分身"+str(n)+"名稱： ").strip() for n in range(start,start+count)] if custom else []
        saved=input("分身設定或上次輸出資料夾（留空自動沿用）： ").strip().strip(chr(34)).strip(chr(39))
        profile=Path(saved).expanduser() if saved else None
        if profile and profile.is_dir():profile=profile/'clone-summary.json'
        out=build(Path(raw),count,start_number=start,names=names,profile_file=profile)
        print("完成，檔案放在："+str(out))
        return 0
    except (ValueError,RuntimeError,OSError) as error:
        print("未完成："+str(error));return 1
    except (KeyboardInterrupt,EOFError):
        print("已取消。");return 130

if __name__=='__main__':raise SystemExit(main())

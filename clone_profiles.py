# SPDX-License-Identifier: MIT
"""Persistent clone slots. Names never participate in package or signing identity."""
import json, re, os
from pathlib import Path
PACKAGE = re.compile(r"[A-Za-z]\w*(?:\.[A-Za-z]\w*)+")
MAX_CODE = 2100000000

def validate_profile(value):
    if value.get("schema") != 1 or not PACKAGE.fullmatch(value.get("source_package", "")):
        raise ValueError("分身設定檔格式不正確。")
    signer = value.get("signer_sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", signer): raise ValueError("分身設定缺少有效簽章身分。")
    signing = value.get("signing", {})
    if not all(isinstance(signing.get(k), str) and signing[k] for k in ("keystore", "password_file", "alias")):
        raise ValueError("分身設定缺少原簽章位置，不能改用新簽章。")
    slots = value.get("slots")
    if not isinstance(slots, dict): raise ValueError("分身設定缺少編號對應。")
    packages = set()
    for key, slot in slots.items():
        if not key.isdigit() or str(int(key)) != key or not 1 <= int(key) <= 99:
            raise ValueError("分身設定的編號必須介於1到99。")
        package = slot.get("package", "")
        if not PACKAGE.fullmatch(package) or package in packages:
            raise ValueError("分身設定有重複或無效的套件識別。")
        packages.add(package)
        code = slot.get("last_version_code")
        if type(code) is not int or not 1 <= code <= MAX_CODE: raise ValueError("分身版本代碼無效。")
        clean_name(slot.get("name", ""))
    return value

def clean_name(name):
    if not isinstance(name, str): raise ValueError("分身名稱必須是文字。")
    name = name.strip()
    if not name or any(ord(c)<32 or 127<=ord(c)<160 for c in name):
        raise ValueError("分身名稱不可空白或含換行／控制字元。")
    return name

def rows_for(base, count, start=1, names=None, profile=None):
    if type(count) is not int or type(start) is not int or not 1<=count<=99 or not 1<=start<=99 or start+count-1>99:
        raise ValueError("分身編號範圍必須介於1到99。")
    names = [] if names is None else names
    if not isinstance(names, list) or names and len(names)!=count: raise ValueError("指定名稱時，名稱行數必須與分身數量相同。")
    if type(base["code"]) is not int or base["code"]<1: raise ValueError("原APK版本代碼無效。")
    if profile is not None: validate_profile(profile)
    slots = profile["slots"] if profile else {}
    prefix = profile["source_package"] if profile else base["package"]
    result=[]
    for pos,n in enumerate(range(start,start+count)):
        old = slots.get(str(n), {})
        name = clean_name(names[pos] if names else old.get("name", base["name"]+str(n)))
        code = max(base["code"]+n, old.get("last_version_code",0)+1)
        if code>MAX_CODE: raise ValueError("分身版本代碼超出Android範圍。")
        package=old.get("package",prefix+"clone"+str(n))
        if not PACKAGE.fullmatch(package): raise ValueError("分身套件識別無效。")
        result.append(dict(number=n,name=name,package=package,version_code=code,version_name=base["version"]))
    return result

def updated_profile(profile, rows):
    result=json.loads(json.dumps(profile))
    for row in rows:
        result["slots"][str(row["number"])]=dict(package=row["package"],name=row["name"],last_version_code=row["version_code"])
    return validate_profile(result)

def save_profile(path, value):
    validate_profile(value)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    # Ordinary exclusive creation plus rename. No hardlink lock or link/unlink protocol.
    import secrets
    temp=path.with_name(path.name+".tmp-"+secrets.token_hex(6))
    try:
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w") as f:
            json.dump(value,f,ensure_ascii=False,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()


def merge_profiles(current, incoming):
    validate_profile(current);validate_profile(incoming)
    if current["source_package"]!=incoming["source_package"] or current["signer_sha256"]!=incoming["signer_sha256"]:
        raise ValueError("上次分身設定與目前保存的來源或簽章不同，已停止；不會覆蓋原更新身分。")
    result=json.loads(json.dumps(current))
    for number, slot in incoming["slots"].items():
        old=result["slots"].get(number)
        if old and old["package"]!=slot["package"]:
            raise ValueError("同一編號對到不同分身，已停止；不能改寫原身分。")
        if not old or slot["last_version_code"]>old["last_version_code"]:
            result["slots"][number]=dict(slot)
    return validate_profile(result)

#!/usr/bin/env python3
"""
APK 分身精靈 (APK Clone Wizard)

這是 apk_clone_maker.py 的互動式外殼。
它不會取代 apk_clone_maker.py，只是幫你用問答的方式組出參數，
最後仍然是呼叫同一個資料夾底下的 apk_clone_maker.py 去實際執行分身作業。

使用方式（macOS）：
  1. 打開「終端機」App
  2. 把這個檔案從 Finder 拖進終端機視窗，會自動貼上一長串路徑
  3. 按 Enter

如果拖進去按 Enter 出現 "Permission denied"，
先在終端機執行一次（把路徑換成你自己的）：
  chmod +x "這個檔案的路徑"
再重新拖一次即可。
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ------------------------------------------------------------------
# 基本設定：所有東西都以「這個腳本所在的資料夾」為準，
# 這樣不管你把整包工具放在哪裡、改了外層資料夾名稱，都還是找得到彼此。
# ------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
MAKER = HERE / "apk_clone_maker.py"
BUNDLED_APKTOOL = HERE / "apktool-cli-2.11.1.jar"


def print_banner():
    print("\n" + "=" * 62)
    print("  APK 分身精靈")
    print("  對 apk_clone_maker.py 的互動式包裝")
    print("=" * 62)
    print("  這個工具只整理你的操作步驟，實際分身作業一律交給")
    print("  同資料夾內的 apk_clone_maker.py 執行。")
    print("=" * 62 + "\n")


def ask(prompt: str, default: str | None = None) -> str:
    """簡單的文字輸入，允許直接按 Enter 使用預設值。"""
    suffix = f"（直接按 Enter 使用預設值: {default}）" if default is not None else ""
    while True:
        raw = input(f"{prompt}{suffix}\n> ").strip()
        if raw:
            return raw
        if default is not None:
            return default
        print("這一項不能留白，請重新輸入。\n")


def ask_yes_no(prompt: str, default_yes: bool = True) -> bool:
    hint = "(Y/n)" if default_yes else "(y/N)"
    raw = input(f"{prompt} {hint}\n> ").strip().lower()
    if not raw:
        return default_yes
    return raw.startswith("y")


def clean_dragged_path(raw: str) -> str:
    """
    處理從 Finder 拖曳檔案/資料夾到終端機時常見的格式問題：
    - 前後可能帶著多餘的空白
    - 路徑可能被終端機自動加上反斜線跳脫（例如「我的 APK」變成「我的\\ APK」）
    - 路徑前後可能被自動加上一組引號
    """
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1]
    text = text.replace("\\ ", " ")
    return text.strip()


def ask_path(prompt: str, must_exist: bool = True, is_dir: bool = False) -> Path:
    while True:
        raw = input(f"{prompt}\n> ")
        cleaned = clean_dragged_path(raw)
        if not cleaned:
            print("路徑不能是空的，請重新輸入（可以直接拖曳檔案/資料夾進來）。\n")
            continue
        p = Path(cleaned).expanduser()
        try:
            p = p.resolve()
        except Exception:
            pass
        if must_exist and not p.exists():
            print(f"找不到這個路徑：{p}\n請確認拖曳的檔案/資料夾是否正確，或手動貼上完整路徑。\n")
            continue
        if must_exist and is_dir and not p.is_dir():
            print(f"這個路徑不是資料夾：{p}\n")
            continue
        if must_exist and not is_dir and p.is_dir():
            print(f"這個路徑是資料夾，但這裡需要一個檔案：{p}\n")
            continue
        return p


# ------------------------------------------------------------------
# 環境檢查
# ------------------------------------------------------------------

def find_build_tool_via_sdk(sdk_root: Path, tool_name: str) -> Path | None:
    bt = sdk_root / "build-tools"
    if not bt.is_dir():
        return None
    candidates = []
    for version_dir in bt.iterdir():
        candidate = version_dir / tool_name
        if candidate.exists():
            candidates.append(candidate)
    if not candidates:
        return None
    # 版本號字串排序即可取得「看起來最新」的一個，實際使用時
    # apk_clone_maker.py 自己也會再挑一次，這裡只是先讓使用者看到有沒有裝。
    return sorted(candidates)[-1]


def check_environment() -> dict:
    """
    檢查跑分身作業需要的東西是否存在，回傳一份檢查結果，
    並且把結果印出來讓使用者一眼看懂「還缺什麼」。
    不會在這裡直接中斷程式——由呼叫端決定要不要繼續。
    """
    print("正在檢查環境...\n")
    result = {
        "maker_script_found": MAKER.exists(),
        "java_found": shutil.which("java") is not None,
        "sdk_root": None,
        "zipalign_found": False,
        "apksigner_found": False,
        "aapt2_found": False,
        "apktool_source": None,
    }

    print(f"  {'✓' if result['maker_script_found'] else '✗'} apk_clone_maker.py"
          f"（{'找到' if result['maker_script_found'] else '找不到，請確認這支精靈腳本和 apk_clone_maker.py 放在同一個資料夾'}）")

    print(f"  {'✓' if result['java_found'] else '✗'} Java"
          f"（{'已安裝' if result['java_found'] else '未偵測到，需要安裝 JDK 才能執行 apktool'}）")

    sdk_env = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    default_mac_sdk = Path.home() / "Library" / "Android" / "sdk"
    sdk_root = None
    if sdk_env and Path(sdk_env).expanduser().is_dir():
        sdk_root = Path(sdk_env).expanduser().resolve()
    elif default_mac_sdk.is_dir():
        sdk_root = default_mac_sdk.resolve()

    if sdk_root:
        result["sdk_root"] = str(sdk_root)
        zipalign = find_build_tool_via_sdk(sdk_root, "zipalign")
        apksigner = find_build_tool_via_sdk(sdk_root, "apksigner")
        aapt2 = find_build_tool_via_sdk(sdk_root, "aapt2")
        result["zipalign_found"] = zipalign is not None
        result["apksigner_found"] = apksigner is not None
        result["aapt2_found"] = aapt2 is not None
        print(f"  ✓ 找到 Android SDK：{sdk_root}")
        print(f"    {'✓' if result['zipalign_found'] else '✗'} zipalign")
        print(f"    {'✓' if result['apksigner_found'] else '✗'} apksigner")
        print(f"    {'✓' if result['aapt2_found'] else '✗'} aapt2（沒有也可以跑，只是少一項驗證）")
    else:
        print("  ✗ 找不到 Android SDK")
        print(f"    已檢查環境變數 ANDROID_SDK_ROOT / ANDROID_HOME，")
        print(f"    以及預設位置 {default_mac_sdk}")

    if shutil.which("apktool"):
        result["apktool_source"] = "系統已安裝的 apktool"
        print("  ✓ 系統已安裝 apktool（將優先使用這一份）")
    elif BUNDLED_APKTOOL.exists():
        result["apktool_source"] = f"隨附的 {BUNDLED_APKTOOL.name}"
        print(f"  ✓ 使用隨附的 {BUNDLED_APKTOOL.name}")
    else:
        print("  ✗ 找不到 apktool（系統未安裝，資料夾內也沒有 apktool-cli-2.11.1.jar）")

    print()
    return result


def environment_is_workable(env: dict) -> bool:
    if not env["maker_script_found"]:
        return False
    if not env["java_found"]:
        return False
    if not env["apktool_source"]:
        return False
    if not (env["zipalign_found"] and env["apksigner_found"]):
        return False
    return True


# ------------------------------------------------------------------
# 功能一：檢查環境（獨立選項，方便使用者隨時重新檢查）
# ------------------------------------------------------------------

def menu_check_environment():
    env = check_environment()
    if environment_is_workable(env):
        print("環境看起來已經齊全，可以嘗試建立分身。")
    else:
        print("環境還缺東西，請先按照使用說明書把缺少的部分裝好，再回來重新檢查。")
    input("\n按 Enter 回到主選單...")


# ------------------------------------------------------------------
# 功能二：建立分身（互動問答 -> 組參數 -> 呼叫 apk_clone_maker.py）
# ------------------------------------------------------------------

def menu_create_clones():
    env = check_environment()
    if not env["maker_script_found"]:
        print("找不到 apk_clone_maker.py，無法繼續。請確認這支精靈腳本沒有被單獨移動。")
        input("\n按 Enter 回到主選單...")
        return
    if not environment_is_workable(env):
        proceed = ask_yes_no(
            "環境檢查顯示可能缺少必要工具（見上方 ✗ 項目）。仍要嘗試繼續嗎？"
            "\n（apk_clone_maker.py 執行時若真的缺東西，會自行報錯並停止，不會做出半成品）",
            default_yes=False,
        )
        if not proceed:
            input("\n已取消。按 Enter 回到主選單...")
            return

    print("\n接下來會問幾個問題，用來組出建立分身所需要的參數。")
    print("每一題如果不確定，多半可以直接按 Enter 使用預設值。\n")

    apk_path = ask_path("第 1 步：請把要做分身的 APK 檔案拖進來", must_exist=True, is_dir=False)

    output_dir_raw = ask("第 2 步：分身完成後要輸出到哪個資料夾？（可以是還不存在的新資料夾名稱）",
                          default="分身輸出")
    output_dir = Path(output_dir_raw).expanduser()
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir

    count_raw = ask("第 3 步：要做幾份分身？（例如輸入 4，會建立編號 1~4 共 4 份）", default="4")
    try:
        count = int(count_raw)
        if count < 1:
            raise ValueError
    except ValueError:
        print("輸入不是有效的正整數，改用預設值 4。")
        count = 4
    numbers = ",".join(str(i) for i in range(1, count + 1))

    name_template = ask(
        "第 4 步：每個分身在手機桌面上顯示的名稱樣板？"
        "\n（用 {n} 代表分身編號，例如「相簿{n}」會產生 相簿1、相簿2...）",
        default="{base_name}{n}",
    )

    package_template = ask(
        "第 5 步：每個分身的 Android package 名稱樣板？"
        "\n（用 {n} 代表編號，{old_package} 代表原本的 package。"
        "\n 不確定就直接按 Enter，用預設規則自動加 .clone1 / .clone2 這種後綴）",
        default="{old_package}.clone{n}",
    )

    use_advanced = ask_yes_no(
        "第 6 步：需要設定版本號樣板、簽名金鑰等進階選項嗎？"
        "\n（一般情況下直接選「否」，讓工具自動處理即可）",
        default_yes=False,
    )

    keystore_path = None
    ks_alias = None
    ks_pass = None
    key_pass = None
    version_name_template = None
    version_code_base = None

    if use_advanced:
        has_keystore = ask_yes_no(
            "是否已經有先前用過的簽名金鑰檔（.jks）？"
            "\n（如果這是第一次幫這個 APP 做分身，選「否」，工具會自動幫你產生一把新的並提醒你保存）",
            default_yes=False,
        )
        if has_keystore:
            keystore_path = ask_path("請把 .jks 金鑰檔拖進來", must_exist=True, is_dir=False)
            ks_alias = ask("金鑰的 alias 名稱是？", default="apkclone")
            ks_pass = ask("金鑰庫密碼（keystore password）是？", default="android")
            key_pass = ask("金鑰密碼（key password，很多情況下和上面相同）是？", default=ks_pass)

        set_version = ask_yes_no("要自訂版本號（versionName）樣板嗎？", default_yes=False)
        if set_version:
            version_name_template = ask(
                "版本號樣板？（用 {n} 代表編號、{base_version_name} 代表原始版本號）",
                default="{base_version_name}-clone{n}",
            )
            vcb_raw = ask("第一個分身的 versionCode 數字？（直接按 Enter 讓工具自動用原版本號 +1 起算）",
                          default="")
            if vcb_raw.strip():
                try:
                    version_code_base = int(vcb_raw)
                except ValueError:
                    print("這不是有效的整數，已略過此設定，改用自動計算。")

    # ---- 組出等同於手動輸入的完整指令 ----
    cmd = [
        sys.executable, str(MAKER),
        "--apk", str(apk_path),
        "--output-dir", str(output_dir),
        "--numbers", numbers,
        "--name-template", name_template,
        "--package-template", package_template,
    ]
    if version_name_template:
        cmd += ["--version-name-template", version_name_template]
    if version_code_base is not None:
        cmd += ["--version-code-base", str(version_code_base)]
    if env.get("sdk_root"):
        cmd += ["--android-sdk", env["sdk_root"]]
    if env.get("apktool_source", "").startswith("隨附的") and BUNDLED_APKTOOL.exists():
        cmd += ["--apktool", str(BUNDLED_APKTOOL)]
    if keystore_path:
        cmd += ["--keystore", str(keystore_path), "--ks-alias", ks_alias,
                "--ks-pass", ks_pass, "--key-pass", key_pass]

    print("\n" + "-" * 62)
    print("即將執行下列指令（等同於你手動在終端機打這一長串）：")
    print("-" * 62)
    print(" \\\n  ".join(cmd))
    print("-" * 62)

    if not ask_yes_no("\n確認要開始執行嗎？", default_yes=True):
        print("已取消，沒有做任何變更。")
        input("\n按 Enter 回到主選單...")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    print("\n開始執行 apk_clone_maker.py，過程可能需要幾分鐘，請耐心等候...\n")
    process = subprocess.run(cmd)

    print()
    if process.returncode == 0:
        print("完成！請到輸出資料夾查看結果：")
        print(f"  {output_dir}")
        summary_path = output_dir / "clone-summary.json"
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                print(f"\n原始 APK 的 package：{summary.get('base_package')}")
                print("本次產出：")
                for clone in summary.get("clones", []):
                    spec = clone.get("spec", {})
                    warn_count = len(clone.get("warnings", []))
                    warn_note = f"（有 {warn_count} 項警告，建議查看同名 .report.json）" if warn_count else ""
                    print(f"  - {spec.get('app_name')}：{spec.get('output_apk')} {warn_note}")
            except Exception:
                pass
    else:
        print("執行過程中發生錯誤（結束代碼非 0）。")
        print("請往上捲動查看 apk_clone_maker.py 印出的詳細錯誤訊息，")
        print("通常會直接告訴你是哪一個環節、哪一個工具出了問題。")

    input("\n按 Enter 回到主選單...")


# ------------------------------------------------------------------
# 功能三：查看使用說明.md 內容（直接印在終端機裡，不用另外開檔案）
# ------------------------------------------------------------------

def menu_show_readme():
    candidates = [HERE / "macOS使用說明.md", HERE / "使用說明.md", HERE / "README.md"]
    found = next((p for p in candidates if p.exists()), None)
    if not found:
        print("在這個資料夾底下找不到說明文件（.md 檔）。")
    else:
        print(f"\n===== {found.name} =====\n")
        print(found.read_text(encoding="utf-8"))
        print(f"\n===== ({found.name} 結束) =====")
    input("\n按 Enter 回到主選單...")


# ------------------------------------------------------------------
# 主選單
# ------------------------------------------------------------------

def main():
    print_banner()
    while True:
        print("請選擇要做的事：")
        print("  1. 檢查環境（確認 Java / Android SDK / apktool 是否就緒）")
        print("  2. 建立分身（互動問答，跑完就會產生 APK）")
        print("  3. 查看使用說明")
        print("  4. 離開")
        choice = input("\n請輸入數字 1-4\n> ").strip()
        print()

        if choice == "1":
            menu_check_environment()
        elif choice == "2":
            menu_create_clones()
        elif choice == "3":
            menu_show_readme()
        elif choice == "4":
            print("\n再見！")
            break
        else:
            print("\n請輸入 1 到 4 之間的數字。\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n（使用者中斷，已結束）")
        sys.exit(130)

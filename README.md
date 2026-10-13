# APK 分身精靈 · APK Clone Wizard

以 macOS 原生視窗或 Python 命令列，將你有權修改的 Android APK 製作成可獨立安裝的分身。支援 1–99 個分身、名稱與套件編號、版本代碼遞增、重新打包、ZIP 對齊、簽章與輸出校驗。

本儲存庫提供程式原始碼，不包含任何原始／分身 APK、第三方工具二進位檔、簽章金鑰或個人電腦設定。

## 資料夾內安裝環境

下載本專案後，先雙擊 **「安裝本機環境.command」**，再雙擊 **「啟動APK分身精靈.command」**。若 macOS 提示檔案沒有執行權限，可在終端機執行：

```sh
chmod +x ./*.command
./安裝本機環境.command
```

安裝器支援 macOS 14 以上的 Apple Silicon 與 Intel Mac，會依 CPU 架構從上游官方發行來源下載 Python、Eclipse Temurin JDK、Apktool 與 Android SDK Build Tools，並驗證 `environment.lock.json` 固定的 SHA-256。Python／JDK 版本及下載來源可在該檔查閱。

所有下載、工具、授權紀錄與快取都放在專案的 `.local-env/` 內，不使用 sudo、Homebrew、系統安裝程式，不修改 shell 設定檔或系統 PATH。啟動入口只在自己的程序套用本機路徑，不影響其他軟體。移動整個專案資料夾後仍會使用相對位置；不同 CPU 架構需重新安裝。

**下載的工具與其相依元件之著作權屬各自原作者及權利人，不是本專案作者的著作，也不會因本專案的授權而改變。** 詳細來源與條款見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)；下載套件原附的 LICENSE／NOTICE 會保留。發布到 GitHub 的是下載腳本與固定版本資料，沒有把工具二進位檔或你的安裝快取上傳。

Android SDK Build Tools 依 [Google SDK 授權條款](https://developer.android.com/studio/terms) 使用。安裝器會展示官方索引中的完整授權文字，要求你輸入「我同意」才安裝；不同意就取消。此動作只表示你對 Google 條款的同意，不是把 Google 工具授權改成屬於本專案。

原生視窗首次編譯需要已安裝的 **Apple Xcode Command Line Tools**。這是系統層級的 Apple 工具，無法由本腳本在專案內安裝；腳本不會自動安裝它。沒有 Apple 編譯工具時，仍可雙擊 **「啟動終端分身精靈.command」**，使用資料夾內的 Python 與 APK 工具，無需安裝 Apple 編譯環境。

若下載中斷，重新執行會驗證並重用已完成的下載。完整環境會先在專案內的暫存資料夾準備，再替換舊環境；下載或驗證失敗不會先刪除舊環境。`tools.local.json` 的既有手動設定不會被安裝器覆蓋。

```sh
./安裝本機環境.command --check         # 檢查目前環境，不下載
./安裝本機環境.command --download-only # 只下載並校驗，不接受 SDK 條款或安裝
```

要移除環境，只需刪除 `.local-env/`；這不會刪除 `06-精靈私有簽章/` 中的金鑰，請另行安全備份金鑰。首次下載約數百 MB，解壓後需約 1 GB 可用空間。

若你已有自己的工具，也可複製 `tools.example.json` 為 `tools.local.json`，填入自己的 SDK、Apktool 與 `java_home` 路徑，或設定 `ANDROID_SDK_ROOT`、`APKTOOL_PATH`。相對路徑以專案資料夾為準，本機設定檔會被 Git 忽略。Python 不需要安裝第三方 pip 套件。

## 使用

把 APK 拖入視窗或按「選擇 APK…」，輸入數量，再按「製作分身」。首次啟動會編譯視窗。每次建置輸出到新的 `01-輸出/` 子資料夾，可另選輸出位置。

例如 `com.example.gallery`、名稱「相簿」、版本代碼 43、版本名稱 2.0，製作兩個分身後：

| 名稱 | 套件 | 版本代碼 | 版本名稱 |
| --- | --- | --- | --- |
| 相簿1 | com.example.galleryclone1 | 44 | 2.0 |
| 相簿2 | com.example.galleryclone2 | 45 | 2.0 |

原生視窗會在 `06-精靈私有簽章/` 建立本機專用金鑰與隨機密碼，之後沿用。更新既有分身必須保留同一組金鑰、相同套件名稱，以及較高版本代碼。請在本機安全備份金鑰，勿上傳 GitHub。

發布版採用一般 APK 命名與本機簽章流程，移除了原始個人環境的特定 App 相容簽章分支。不能用發布版生成的金鑰更新以原私人金鑰簽署的舊分身。

命令列可用互動式入口：

```sh
./啟動終端分身精靈.command
```

或直接使用引擎（此入口的預設套件格式是 `.clone1`，與原生視窗的 `clone1` 不同；要更新請固定模板）：

```sh
./.local-env/runtime/python/bin/python3 apk_clone_maker.py \
  --apk /path/to/authorized.apk \
  --output-dir ./01-輸出/example \
  --numbers 1,2 \
  --apktool ./.local-env/runtime/apktool.jar \
  --android-sdk ./.local-env/runtime/android-sdk
```

舊版命令列入口使用測試簽章密碼，部分工具參數與命令會顯示在終端機；處理正式私有簽章請優先使用原生視窗的密碼檔流程，不要分享命令列記錄。

## 限制與授權

重新簽章會改變 APK 的簽章身分。JNI 套件綁定、簽章檢查、Play Integrity、加密程式或伺服器套件白名單可能導致分身無法運作。完成建置與靜態檢查不代表手機上的所有功能正常。

只能處理你擁有或已取得修改授權的 APK。本工具的程式授權不包含輸入 App 的程式、圖片、商標或其他資產；備註作者也不能替代必要授權。

第三方工具來源及授權範圍見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本專案程式的授權範圍見 [LICENSING.md](LICENSING.md)。

## 驗證

```sh
./.local-env/runtime/python/bin/python3 -B test_bridge.py
./.local-env/runtime/python/bin/python3 -B test_local_environment.py
./.local-env/runtime/python/bin/python3 -B test_installer.py
./啟動APK分身精靈.command --compile-only
./啟動APK分身精靈.command --self-test
```

測試使用合成資料，不需要第三方 App 或個人金鑰。`--self-test` 驗證拖入接受／拒絕邏輯，並非 Finder 真實拖曳操作。實際手機安裝與運行需使用者自行確認。

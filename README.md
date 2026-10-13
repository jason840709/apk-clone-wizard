# APK 分身精靈 · APK Clone Wizard

以 macOS 原生視窗或 Python 命令列，將你有權修改的 Android APK 製作成可獨立安裝的分身。支援 1–99 個分身、名稱與套件編號、版本代碼遞增、重新打包、ZIP 對齊、簽章與輸出校驗。

本儲存庫提供程式原始碼，不包含任何原始／分身 APK、第三方工具二進位檔、簽章金鑰或個人電腦設定。

## 安裝

- 原生視窗：macOS 14 或更新版本，Xcode Command Line Tools（`xcode-select --install`）。
- Python 3.10 或更新版本；不需要安裝第三方 Python 套件。
- Java JDK（可選用 [Eclipse Temurin](https://adoptium.net/)）。
- [Apktool](https://apktool.org/docs/2.x/install/)；原始版本使用 2.11.1，更新版本請自行驗證相容性。
- [Android SDK Build Tools](https://developer.android.com/tools/releases/build-tools)，需有 `aapt2`、`zipalign` 及 `lib/apksigner.jar`。

工具請從官方來源自行安裝，依官方授權條款使用。本專案不會自動下載或代為接受 SDK 條款。

```sh
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
export APKTOOL_PATH="/path/to/apktool_2.11.1.jar"
chmod +x ./啟動APK分身精靈.command
./啟動APK分身精靈.command
```

也可以複製 `tools.example.json` 為 `tools.local.json`，填入自己的路徑。此檔案會被 Git 忽略。若 `apktool` 已在 PATH，可不設定 `APKTOOL_PATH`；原生後端預設選用 SDK 中版本最高的 Build Tools，也可在設定檔固定版本。

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
python3 '分身精靈 [終端機運行].py'
```

或直接使用引擎（此入口的預設套件格式是 `.clone1`，與原生視窗的 `clone1` 不同；要更新請固定模板）：

```sh
python3 apk_clone_maker.py \
  --apk /path/to/authorized.apk \
  --output-dir ./01-輸出/example \
  --numbers 1,2 \
  --apktool /path/to/apktool_2.11.1.jar \
  --android-sdk "$ANDROID_SDK_ROOT"
```

舊版命令列入口使用測試簽章密碼，部分工具參數與命令會顯示在終端機；處理正式私有簽章請優先使用原生視窗的密碼檔流程，不要分享命令列記錄。

## 限制與授權

重新簽章會改變 APK 的簽章身分。JNI 套件綁定、簽章檢查、Play Integrity、加密程式或伺服器套件白名單可能導致分身無法運作。完成建置與靜態檢查不代表手機上的所有功能正常。

只能處理你擁有或已取得修改授權的 APK。本工具的程式授權不包含輸入 App 的程式、圖片、商標或其他資產；備註作者也不能替代必要授權。

第三方工具來源及授權範圍見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本專案程式的授權範圍見 [LICENSING.md](LICENSING.md)。

## 驗證

```sh
python3 -B test_bridge.py
./啟動APK分身精靈.command --compile-only
./啟動APK分身精靈.command --self-test
```

測試使用合成資料，不需要第三方 App 或個人金鑰。`--self-test` 驗證拖入接受／拒絕邏輯，並非 Finder 真實拖曳操作。實際手機安裝與運行需使用者自行確認。

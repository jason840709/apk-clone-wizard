# 第三方來源與授權

本儲存庫不隨附以下工具的原始碼、JAR、SDK 或 runtime；程式呼叫使用者透過「安裝本機環境.command」安裝到本機專案資料夾，或自行準備的工具。本專案沒有把這些工具改標為自己的著作。

| 工具／元件 | 開發者／來源 | 授權與使用方式 |
| --- | --- | --- |
| Apktool（原始環境 2.11.1） | [Ryszard Wiśniewski（brut.all）、Connor Tumbleson（iBotPeaches）及 contributors](https://github.com/iBotPeaches/Apktool) | Apache License 2.0；透過命令列反編譯與重建 APK。原始資料夾的 JAR 未納入發布。 |
| Apktool 內含的 smali／baksmali、資源處理等相依元件 | [Apktool 官方專案](https://github.com/iBotPeaches/Apktool)、[smali 專案](https://github.com/JesusFreke/smali) | 隨 Apktool 下載的元件依各自授權與上游通知；本儲存庫不再散布，不能把全部相依元件一概宣稱為 Apache 2.0。 |
| Android SDK Build Tools：aapt2、zipalign、apksigner | Google／Android Open Source Project；[Build Tools 文件](https://developer.android.com/tools/releases/build-tools) | 官方 SDK 發行包依 [Android SDK License Agreement](https://developer.android.com/studio/terms) 及各元件附帶授權／NOTICE；開源部分依各自授權。本儲存庫未散布 SDK。 |
| Python 與標準函式庫 | Python Software Foundation 與 contributors；[Python 授權](https://docs.python.org/3/license.html) | PSF License 與相應元件授權；使用者自行安裝。沒有第三方 pip 套件依賴。資料夾內安裝器使用 Astral 維護的 [python-build-standalone](https://github.com/astral-sh/python-build-standalone) 發行檔；建置專案為 MPL-2.0，實際 Python 與包含的函式庫各依其原始授權，不能全部標為 MPL 或 PSF。 |
| Java JDK、java、keytool | 使用者選用的 JDK 發行者；例如 [OpenJDK 法律資訊](https://openjdk.org/legal/) | OpenJDK 主要為 GPLv2 with Classpath Exception；其他 JDK 發行版依供應商條款。本儲存庫未散布 JDK。 |
| Swift、AppKit、UniformTypeIdentifiers、Xcode Command Line Tools | [Swift 專案](https://www.swift.org/about/)／Apple | Swift 開源部分依其 Apache 2.0 與 Runtime Library Exception；Apple SDK、framework 與開發工具依 Apple 條款。本儲存庫只包含呼叫 API 的 Swift 程式，未附帶 Apple 工具或 framework。 |

Apktool 授權可由 [官方 FAQ](https://apktool.org/docs/2.x/faq/) 與 [2.11.1 Maven metadata](https://central.sonatype.com/artifact/org.apktool/apktool-cli/2.11.1) 核對。安裝第三方工具時請保留供應商附帶的授權及 NOTICE。若未來改為隨附二進位工具，需另外整理實際發行包全部相依授權與必要通知；本文件不能取代那些義務。

任何使用者輸入的 App 都有自己的權利人與授權。本專案沒有隨附 QuickPic／快圖或其他 App 的 APK、反編譯內容、圖片、商標或簽章。不得因為可以修改 APK 就假定可以公開重新散布。

## 自動下載環境的權利歸屬

**安裝器下載的 Python、python-build-standalone 發行內容、Eclipse Temurin JDK、Apktool、Android Build Tools 及其相依元件，著作權均屬各自原作者及權利人，不是本專案作者的著作。** 本專案只提供下載、校驗及啟動整合，沒有取得或轉移那些工具的著作權，也不代表上游為本專案背書。

套件從固定的官方 HTTPS 發行來源下載到 `.local-env/downloads/`，解壓後在 `.local-env/runtime/` 使用。上游套件內的 LICENSE、legal 與 NOTICE 檔案會隨同保留；Google 官方索引的 SDK 授權文字另存於 `tool-licenses/android-sdk-license.txt`，安裝時要求使用者閱讀並明示同意。Python 發行檔的組件授權亦參見 [上游授權說明](https://github.com/astral-sh/python-build-standalone/blob/main/python-licenses.rst)。

`environment.lock.json` 記錄固定下載版本與 SHA-256。Python 的雜湊來自其 GitHub release asset digest；JDK 雜湊來自 [Adoptium 官方 API](https://api.adoptium.net/)。Android 發行檔先核對 [Google 官方索引](https://dl.google.com/android/repository/repository2-1.xml) 的 SHA-1，再記錄額外計算的 SHA-256。Apktool 2.11.1 的舊版 release API 沒有 asset digest，因此該 SHA-256 是從其官方 HTTPS 發行檔計算並固定的值，不冒稱是上游發布的獨立校驗碼。

`.local-env/` 完整排除於 Git；不會把使用者下載的第三方工具重新上傳。本次附上的 Google SDK 授權文字僅供閱讀原條款，來源為 Google 官方索引，權利屬 Google；它不是本專案的 MIT 文件。

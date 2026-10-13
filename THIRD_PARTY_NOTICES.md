# 第三方來源與授權

本儲存庫不隨附以下工具的原始碼、JAR、SDK 或 runtime；程式僅呼叫使用者自行安裝的工具。本專案沒有把這些工具改標為自己的著作。

| 工具／元件 | 開發者／來源 | 授權與使用方式 |
| --- | --- | --- |
| Apktool（原始環境 2.11.1） | [Ryszard Wiśniewski（brut.all）、Connor Tumbleson（iBotPeaches）及 contributors](https://github.com/iBotPeaches/Apktool) | Apache License 2.0；透過命令列反編譯與重建 APK。原始資料夾的 JAR 未納入發布。 |
| Apktool 內含的 smali／baksmali、資源處理等相依元件 | [Apktool 官方專案](https://github.com/iBotPeaches/Apktool)、[smali 專案](https://github.com/JesusFreke/smali) | 隨 Apktool 下載的元件依各自授權與上游通知；本儲存庫不再散布，不能把全部相依元件一概宣稱為 Apache 2.0。 |
| Android SDK Build Tools：aapt2、zipalign、apksigner | Google／Android Open Source Project；[Build Tools 文件](https://developer.android.com/tools/releases/build-tools) | 官方 SDK 發行包依 [Android SDK License Agreement](https://developer.android.com/studio/terms) 及各元件附帶授權／NOTICE；開源部分依各自授權。本儲存庫未散布 SDK。 |
| Python 與標準函式庫 | Python Software Foundation 與 contributors；[Python 授權](https://docs.python.org/3/license.html) | PSF License 與相應元件授權；使用者自行安裝。沒有第三方 pip 套件依賴。 |
| Java JDK、java、keytool | 使用者選用的 JDK 發行者；例如 [OpenJDK 法律資訊](https://openjdk.org/legal/) | OpenJDK 主要為 GPLv2 with Classpath Exception；其他 JDK 發行版依供應商條款。本儲存庫未散布 JDK。 |
| Swift、AppKit、UniformTypeIdentifiers、Xcode Command Line Tools | [Swift 專案](https://www.swift.org/about/)／Apple | Swift 開源部分依其 Apache 2.0 與 Runtime Library Exception；Apple SDK、framework 與開發工具依 Apple 條款。本儲存庫只包含呼叫 API 的 Swift 程式，未附帶 Apple 工具或 framework。 |

Apktool 授權可由 [官方 FAQ](https://apktool.org/docs/2.x/faq/) 與 [2.11.1 Maven metadata](https://central.sonatype.com/artifact/org.apktool/apktool-cli/2.11.1) 核對。安裝第三方工具時請保留供應商附帶的授權及 NOTICE。若未來改為隨附二進位工具，需另外整理實際發行包全部相依授權與必要通知；本文件不能取代那些義務。

任何使用者輸入的 App 都有自己的權利人與授權。本專案沒有隨附 QuickPic／快圖或其他 App 的 APK、反編譯內容、圖片、商標或簽章。不得因為可以修改 APK 就假定可以公開重新散布。

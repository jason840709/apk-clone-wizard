// SPDX-License-Identifier: MIT
import AppKit
import UniformTypeIdentifiers

final class APKDropView: NSBox {
    var received: ((URL) -> Void)?
    var rejected: ((String) -> Void)?
    var busy = false
    override init(frame: NSRect) {
        super.init(frame: frame)
        title = "拖入一個 APK"
        boxType = .custom
        borderColor = .separatorColor
        borderWidth = 1
        cornerRadius = 10
        fillColor = .controlBackgroundColor
        registerForDraggedTypes([.fileURL])
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    func accept(_ urls: [URL]) -> Bool {
        guard !busy else { rejected?("建置進行中，請等它完成再選檔。"); return false }
        guard urls.count == 1, let url = urls.first, url.isFileURL,
              url.pathExtension.lowercased() == "apk",
              FileManager.default.fileExists(atPath: url.path) else {
            rejected?("請拖入一個存在的 .apk 檔案。"); return false
        }
        received?(url); return true
    }
    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        guard !busy, let urls = sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL],
              urls.count == 1, urls[0].pathExtension.lowercased() == "apk" else { return [] }
        return .copy
    }
    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        let urls = sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL] ?? []
        return accept(urls)
    }
}

final class Wizard: NSObject, NSApplicationDelegate, NSWindowDelegate {
    let root: URL
    let python: String
    var window: NSWindow!
    let drop = APKDropView(frame: .zero)
    let input = NSTextField(labelWithString: "拖入一個 APK，或按右側選檔")
    let count = NSTextField(string: "5")
    let stepper = NSStepper()
    let location = NSTextField(labelWithString: "")
    let status = NSTextField(labelWithString: "選擇 APK 後，按「製作分身」。")
    let log = NSTextView()
    let progress = NSProgressIndicator()
    var choose: NSButton!
    var outputChoose: NSButton!
    var start: NSButton!
    var reveal: NSButton!
    var apk: URL?
    var outputParent: URL
    var resultFolder: URL?
    var process: Process?
    var busy = false
    init(root: URL, python: String) {
        self.root = root; self.python = python
        outputParent = root.appendingPathComponent("01-輸出")
        super.init()
    }
    func label(_ text: String, size: CGFloat = 13, bold: Bool = false) -> NSTextField {
        let value = NSTextField(labelWithString: text)
        value.font = bold ? .boldSystemFont(ofSize: size) : .systemFont(ofSize: size)
        value.lineBreakMode = .byWordWrapping
        value.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        return value
    }
    func button(_ title: String, _ action: Selector) -> NSButton {
        let value = NSButton(title: title, target: self, action: action)
        value.bezelStyle = .rounded; return value
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        let menu = NSMenu(); let item = NSMenuItem(); menu.addItem(item)
        let appMenu = NSMenu(); appMenu.addItem(withTitle: "結束 APK 分身精靈", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = appMenu; NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0,y: 0,width: 680,height: 620), styleMask: [.titled,.closable,.miniaturizable,.resizable], backing: .buffered, defer: false)
        window.title = "APK 分身精靈"; window.minSize = NSSize(width: 610,height: 600)
        window.delegate = self
        let content = window.contentView!
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false; content.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: content.leadingAnchor,constant: 26), stack.trailingAnchor.constraint(equalTo: content.trailingAnchor,constant: -26), stack.topAnchor.constraint(equalTo: content.topAnchor,constant: 24), stack.bottomAnchor.constraint(equalTo: content.bottomAnchor,constant: -24)])
        stack.addArrangedSubview(label("把一個 APK 製作成多個分身",size: 22,bold: true))
        stack.addArrangedSubview(label("分身編號從 1 開始，版本名稱沿用原 APK。請保存本機簽章以便更新。"))
        drop.translatesAutoresizingMaskIntoConstraints = false
        stack.addArrangedSubview(drop)
        drop.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        drop.heightAnchor.constraint(equalToConstant: 92).isActive = true
        input.lineBreakMode = .byTruncatingMiddle
        input.font = .systemFont(ofSize: 14)
        choose = button("選擇 APK…",#selector(selectAPK))
        let inside = NSStackView(views: [input,choose]); inside.orientation = .horizontal; inside.spacing = 12; inside.translatesAutoresizingMaskIntoConstraints = false
        drop.addSubview(inside)
        NSLayoutConstraint.activate([inside.leadingAnchor.constraint(equalTo: drop.leadingAnchor,constant: 18),inside.trailingAnchor.constraint(equalTo: drop.trailingAnchor,constant: -18),inside.centerYAnchor.constraint(equalTo: drop.centerYAnchor)])
        drop.received = { [weak self] url in self?.setAPK(url) }
        drop.rejected = { [weak self] text in self?.status.stringValue = text }
        count.widthAnchor.constraint(equalToConstant: 64).isActive = true
        count.alignment = .center
        let formatter = NumberFormatter(); formatter.allowsFloats = false; formatter.minimum = 1; formatter.maximum = 99; count.formatter = formatter
        stepper.minValue = 1; stepper.maxValue = 99; stepper.integerValue = 5
        stepper.target = self; stepper.action = #selector(stepped)
        let quantity = NSStackView(views: [label("分身數量"),count,stepper,label("1～99 個")]); quantity.orientation = .horizontal; quantity.spacing = 12
        stack.addArrangedSubview(quantity)
        location.stringValue = outputParent.path; location.lineBreakMode = .byTruncatingMiddle; location.textColor = .secondaryLabelColor
        outputChoose = button("選擇輸出位置…",#selector(selectOutput))
        let destination = NSStackView(views: [label("輸出位置"),outputChoose]); destination.orientation = .horizontal; destination.spacing = 12
        stack.addArrangedSubview(destination); stack.addArrangedSubview(location)
        start = button("製作分身",#selector(build)); start.keyEquivalent = "\r"
        reveal = button("開啟輸出資料夾",#selector(showOutput)); reveal.isEnabled = false
        progress.style = .spinning; progress.isDisplayedWhenStopped = false
        let controls = NSStackView(views: [start,reveal,progress]); controls.orientation = .horizontal; controls.spacing = 12
        stack.addArrangedSubview(controls)
        status.lineBreakMode = .byWordWrapping; stack.addArrangedSubview(status)
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.borderType = .bezelBorder; scroll.translatesAutoresizingMaskIntoConstraints = false
        log.isEditable = false; log.isSelectable = true; log.font = .monospacedSystemFont(ofSize: 11,weight: .regular); log.autoresizingMask = [.width]
        log.textContainer?.widthTracksTextView = true; log.isVerticallyResizable = true; scroll.documentView = log
        stack.addArrangedSubview(scroll)
        scroll.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        scroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 160).isActive = true
        stack.addArrangedSubview(label("每次輸出存入新資料夾。請保留私有簽章資料，供以後更新分身。",size: 11))
        window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }
    func setAPK(_ url: URL) {
        guard !busy else { return }
        apk = url; input.stringValue = url.lastPathComponent; input.toolTip = url.path
        status.stringValue = "已選擇 \(url.lastPathComponent)。"
    }
    @objc func selectAPK() {
        let panel = NSOpenPanel(); panel.allowedContentTypes = [UTType(filenameExtension: "apk") ?? .data]; panel.allowsMultipleSelection = false; panel.canChooseDirectories = false
        panel.beginSheetModal(for: window) { [weak self] result in if result == .OK, let url = panel.url { _ = self?.drop.accept([url]) } }
    }
    @objc func selectOutput() {
        let panel = NSOpenPanel(); panel.canChooseFiles = false; panel.canChooseDirectories = true; panel.canCreateDirectories = true
        panel.beginSheetModal(for: window) { [weak self] result in if result == .OK, let url = panel.url { self?.outputParent = url; self?.location.stringValue = url.path } }
    }
    @objc func stepped() { count.integerValue = stepper.integerValue }
    @objc func showOutput() { if let url = resultFolder { NSWorkspace.shared.open(url) } }
    func setBusy(_ value: Bool) {
        busy = value; drop.busy = value
        [choose,outputChoose,start].forEach { $0?.isEnabled = !value }
        count.isEnabled = !value; stepper.isEnabled = !value
        if value { progress.startAnimation(nil) } else { progress.stopAnimation(nil) }
    }
    func append(_ text: String) {
        log.textStorage?.append(NSAttributedString(string: text+"\n",attributes: [.font: NSFont.monospacedSystemFont(ofSize: 11,weight: .regular)]))
        log.scrollToEndOfDocument(nil)
    }
    func receive(_ data: Data) {
        guard let value = try? JSONSerialization.jsonObject(with: data) as? [String:Any], let kind = value["event"] as? String else { return }
        let message = value["message"] as? String ?? ""
        if kind == "started" || kind == "progress" { status.stringValue = message; append(message) }
        if kind == "done" { status.stringValue = message; append(message); if let path = value["output"] as? String { resultFolder = URL(fileURLWithPath:path); reveal.isEnabled = true; append("輸出："+path) } }
        if kind == "error" { status.stringValue = "建置失敗，請查看下方訊息。"; append(message) }
    }
    @objc func build() {
        guard !busy else { return }
        window.makeFirstResponder(nil)
        guard let url = apk else { status.stringValue = "請先選擇或拖入 APK。"; return }
        guard let number = Int(count.stringValue), (1...99).contains(number) else { status.stringValue = "分身數量必須是 1 到 99 的整數。"; return }
        stepper.integerValue = number; log.string = ""; reveal.isEnabled = false; resultFolder = nil
        setBusy(true); status.stringValue = "正在準備本機 Android 工具…"
        let task = Process(); task.executableURL = URL(fileURLWithPath: python)
        task.arguments = ["-B",root.appendingPathComponent("clone_bridge.py").path,"--apk",url.path,"--count",String(number),"--output-parent",outputParent.path]
        var environment = ProcessInfo.processInfo.environment; environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:"+(environment["PATH"] ?? "")
        task.environment = environment
        let pipe = Pipe(); task.standardOutput = pipe; task.standardError = pipe
        process = task
        do { try task.run() } catch { setBusy(false); status.stringValue = "無法啟動 Python。"; append(error.localizedDescription); process = nil; return }
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            var pending = Data()
            while true {
                let chunk = pipe.fileHandleForReading.availableData
                if chunk.isEmpty { break }
                pending.append(chunk)
                while let end = pending.firstIndex(of: 10) {
                    let line = Data(pending[..<end]); pending.removeSubrange(...end)
                    DispatchQueue.main.async { self?.receive(line) }
                }
            }
            task.waitUntilExit()
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.setBusy(false); self.process = nil
                if task.terminationStatus != 0 { self.status.stringValue = "建置失敗，請查看下方訊息。" }
                else if self.resultFolder == nil { self.status.stringValue = "未收到完整結果，請查看建置記錄。" }
            }
        }
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if busy { status.stringValue = "分身仍在建置，請等完成後再關閉。"; return false }
        return true
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply { busy ? .terminateCancel : .terminateNow }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let args = CommandLine.arguments
let bundledRoot = Bundle.main.bundleURL.deletingLastPathComponent().deletingLastPathComponent()
let root = args.count > 1 ? URL(fileURLWithPath: args[1]) : bundledRoot
let pythonCandidates = ["/Library/Frameworks/Python.framework/Versions/Current/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
let python = args.count > 2 ? args[2] : (pythonCandidates.first { FileManager.default.isExecutableFile(atPath: $0) } ?? "/usr/bin/python3")
let app = NSApplication.shared
if args.contains("--self-test") {
    let drop = APKDropView(frame: .zero)
    var delivered: URL?; drop.received = { delivered = $0 }
    let fixture = root.appendingPathComponent("拖入 中文 空格.apk")
    try Data().write(to: fixture)
    defer { try? FileManager.default.removeItem(at: fixture) }
    let ok = drop.accept([fixture]) && delivered == fixture && !drop.accept([fixture,fixture]) && !drop.accept([root])
    drop.busy = true
    let rejectsBusy = !drop.accept([fixture])
    print("{\"dragAcceptance\":\(ok),\"busyRejection\":\(rejectsBusy)}")
    exit(ok && rejectsBusy ? 0 : 1)
}
let delegate = Wizard(root: root,python: python)
app.delegate = delegate
app.run()
